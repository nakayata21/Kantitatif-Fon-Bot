#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LFM Ultra Advanced - Gerçek Zamanlı Tarama, Bildirim ve Eğitim Pipeline'ı
==========================================================================
Bu script şunları yapar:
1. Güncel piyasa verilerini çeker (BIST/NASDAQ/Kripto)
2. Teknik indikatörleri hesaplar
3. LFM Ultra Advanced modeli ile tarama yapar
4. En iyi hisseleri Telegram'a gönderir
5. Yeni verileri eğitim setine ekler ve modeli günceller
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
import warnings
warnings.filterwarnings('ignore')

# Yerel modüller
from data_fetcher import fetch_all_market_data
from indicators import calculate_all_indicators
from deep_learning_core import LFMPyTorchTrainerAdvanced
from telegram_autopilot import send_telegram_message
from database import get_training_data, save_training_data
from correlation_network import build_correlation_matrix

# ========================================================================= #
# YAPILANDIRMA
# ========================================================================= #

CONFIG = {
    'markets': ['BIST'],  # ['BIST', 'NASDAQ', 'CRYPTO']
    'min_volume': 1_000_000,  # Minimum günlük hacim (TL)
    'top_n_signals': 10,  # Telegram'da gönderilecek hisse sayısı
    'confidence_threshold': 0.6,  # Minimum güven eşiği
    'uncertainty_threshold': 0.15,  # Maksimum belirsizlik
    'model_path': 'lfm_ultra_checkpoint.pth',
    'training_data_path': 'training_data_all.json',
    'retrain_threshold': 50,  # Kaç yeni örnekten sonra yeniden eğitim
    'sequence_length': 10,
    'use_gnn': True,
    'use_tft': True,
    'enable_uncertainty': True
}


# ========================================================================= #
# VERİ HAZIRLAMA
# ========================================================================= #

def prepare_features(df):
    """
    Ham fiyat verisinden özellikler çıkarır.
    """
    if df is None or len(df) < 30:
        return None, None
    
    # Teknik indikatörleri hesapla
    df = calculate_all_indicators(df)
    
    # NaN değerleri temizle
    df = df.dropna()
    
    if len(df) < 30:
        return None, None
    
    # Özellik sütunlarını seç
    feature_cols = [
        'rsi', 'macd', 'macd_signal', 'bb_upper', 'bb_lower', 'bb_middle',
        'sma_20', 'sma_50', 'ema_12', 'ema_26', 'atr', 'adx',
        'obv', 'mfi', 'stoch_k', 'stoch_d', 'williams_r', 'cci',
        'price_change_pct', 'volume_change_pct', 'volatility'
    ]
    
    # Mevcut olmayan sütunları çıkar
    feature_cols = [col for col in feature_cols if col in df.columns]
    
    X = df[feature_cols].values
    
    # Hedef etiketleri oluştur (Çoklu görev)
    # Yön: Bugünkü kapanış > Dünkü kapanış
    y_direction = (df['close'] > df['close'].shift(1)).astype(int).values
    
    # Volatilite: Günlük değişim yüzdesinin büyüklüğü (3 sınıflı)
    daily_return = (df['close'] - df['close'].shift(1)) / df['close'].shift(1)
    volatility_abs = daily_return.abs().fillna(0)
    vol_quantiles = volatility_abs.quantile([0.33, 0.66]).values
    y_volatility = np.digitize(volatility_abs, vol_quantiles)
    
    # Hacim değişimi (3 sınıflı)
    volume_change = (df['volume'] - df['volume'].shift(1)) / df['volume'].shift(1)
    volume_change = volume_change.fillna(0)
    vol_change_quantiles = volume_change.quantile([0.33, 0.66]).values
    y_volume = np.digitize(volume_change, vol_change_quantiles)
    
    # İlk satırdaki NaN'leri temizle
    mask = ~np.isnan(y_direction) & ~np.isnan(y_volatility) & ~np.isnan(y_volume)
    mask = mask[1:]  # İlk değeri atla
    
    return {
        'X': X[1:][mask],
        'y_direction': y_direction[1:][mask].astype(int),
        'y_volatility': y_volatility[1:][mask].astype(int),
        'y_volume': y_volume[1:][mask].astype(int),
        'feature_cols': feature_cols,
        'symbol': df['symbol'].iloc[-1] if 'symbol' in df.columns else 'UNKNOWN',
        'date': df.index[-1]
    }


def load_or_create_model(feature_dim, feature_names):
    """
    Varolan modeli yükler veya yeni model oluşturur.
    """
    trainer = LFMPyTorchTrainerAdvanced(
        input_dim=feature_dim,
        feature_names=feature_names,
        epochs=30,
        lr=0.001,
        batch_size=64,
        seq_length=CONFIG['sequence_length'],
        use_gnn=CONFIG['use_gnn'],
        use_tft=CONFIG['use_tft'],
        enable_uncertainty=CONFIG['enable_uncertainty']
    )
    
    # Varolan modeli yükle
    if os.path.exists(CONFIG['model_path']):
        try:
            trainer.load_model(CONFIG['model_path'])
            print(f"✅ Model yüklendi: {CONFIG['model_path']}")
        except Exception as e:
            print(f"⚠️ Model yüklenemedi, yeni model başlatılıyor: {e}")
    
    return trainer


# ========================================================================= #
# TARAMA VE TAHMİN
# ========================================================================= #

def scan_market_with_deep_learning():
    """
    Tüm piyasayı tarar ve LFM Ultra Advanced ile en iyi hisseleri bulur.
    """
    print("\n" + "="*80)
    print("🔍 LFM ULTRA ADVANCED - PİYASA TARAMASI BAŞLIYOR")
    print("="*80)
    
    # Veri çek
    print("\n📊 Veri çekiliyor...")
    all_data = fetch_all_market_data(markets=CONFIG['markets'])
    
    if not all_data or len(all_data) == 0:
        print("❌ Veri çekilemedi!")
        return [], None
    
    print(f"✅ {len(all_data)} sembol için veri çekildi")
    
    # Özellikleri hazırla
    all_features = []
    symbols = []
    
    for symbol, df in all_data.items():
        result = prepare_features(df)
        if result is not None:
            all_features.append(result)
            symbols.append(symbol)
    
    if len(all_features) == 0:
        print("❌ Hiçbir sembol için özellik çıkarılamadı!")
        return [], None
    
    print(f"✅ {len(all_features)} sembol için özellikler hazırlandı")
    
    # Tüm veriyi birleştir
    X_all = np.vstack([f['X'][-1:] for f in all_features])  # Son satırı al (en güncel)
    feature_cols = all_features[0]['feature_cols']
    
    # Korrelasyon matrisini hesapla (GNN için)
    print("\n🕸️ Graf komşuluk matrisi hesaplanıyor...")
    adjacency_matrix = build_correlation_matrix(all_data, threshold=0.7)
    
    # Modeli yükle veya oluştur
    print("\n🤖 Model hazırlanıyor...")
    trainer = load_or_create_model(len(feature_cols), feature_cols)
    
    # Tahmin yap (belirsizlikle birlikte)
    print("\n🎯 Tahminler yapılıyor...")
    results = trainer.predict_with_uncertainty(
        X_all,
        adjacency_matrix=adjacency_matrix,
        num_samples=50
    )
    
    # Sonuçları işle
    predictions = []
    for i, symbol in enumerate(symbols):
        direction_prob = results['direction']['mean'][i, 1]  # Yükseliş olasılığı
        uncertainty = results['direction']['std'][i, 1]  # Belirsizlik
        
        # Filtreleme kriterleri
        if direction_prob >= CONFIG['confidence_threshold'] and \
           uncertainty <= CONFIG['uncertainty_threshold']:
            
            predictions.append({
                'symbol': symbol,
                'direction_prob': float(direction_prob),
                'uncertainty': float(uncertainty),
                'volatility_pred': float(results['volatility']['mean'][i, 0]),
                'volume_pred': float(results['volume']['mean'][i, 0]),
                'score': float(direction_prob * (1 - uncertainty))  # Kalite skoru
            })
    
    # Skor'a göre sırala
    predictions = sorted(predictions, key=lambda x: x['score'], reverse=True)
    
    print(f"\n✅ {len(predictions)} adet kaliteli sinyal bulundu")
    
    return predictions, trainer


# ========================================================================= #
# TELEGRAM BİLDİRİMİ
# ========================================================================= #

def format_telegram_message(predictions, market_status="Günlük"):
    """
    Tahminleri Telegram mesajı formatına dönüştürür.
    """
    top_picks = predictions[:CONFIG['top_n_signals']]
    
    message = f"""
🚀 *LFM ULTRA ADVANCED - {market_status} Tarama Sonuçları* 🚀

📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}
🤖 Model: GNN + TFT + Multi-Task Learning

🏆 *EN İYİ {len(top_picks)} HİSSE:*

"""
    
    for i, pick in enumerate(top_picks, 1):
        emoji = "🔥" if pick['score'] > 0.7 else "⭐"
        message += f"""
{i}. {emoji} *{pick['symbol']}*
   ├─ Yükseliş Olasılığı: %{pick['direction_prob']*100:.1f}
   ├─ Belirsizlik: %{pick['uncertainty']*100:.1f}
   ├─ Volatilite: {pick['volatility_pred']:.3f}
   ├─ Hacim Beklentisi: {pick['volume_pred']:.3f}
   └─ Kalite Skoru: {pick['score']:.3f}
"""
    
    message += f"""

⚠️ *UYARI:* Bu sinyaller sadece bilgilendirme amaçlıdır. 
Yatırım tavsiyesi değildir. Kendi araştırmanızı yapın!

📊 Detaylı analiz için web panelini ziyaret edin.
"""
    
    return message


def send_scan_results_to_telegram(predictions):
    """
    Tarama sonuçlarını Telegram'a gönderir.
    """
    if len(predictions) == 0:
        print("⚠️ Gönderilecek sinyal yok")
        return False
    
    message = format_telegram_message(predictions)
    
    try:
        success = send_telegram_message(message, parse_mode='Markdown')
        if success:
            print(f"✅ Telegram bildirimi gönderildi ({len(predictions)} sinyal)")
            return True
        else:
            print("❌ Telegram bildirimi başarısız")
            return False
    except Exception as e:
        print(f"❌ Telegram hatası: {e}")
        return False


# ========================================================================= #
# EĞİTİM VERİSİ TOPLAMA VE MODEL GÜNCELLEME
# ========================================================================= #

def collect_training_data(all_data):
    """
    Yeni verileri eğitim setine ekler.
    """
    print("\n📚 Eğitim verisi toplanıyor...")
    
    all_samples = []
    
    for symbol, df in all_data.items():
        result = prepare_features(df)
        if result is not None:
            # Her zaman adımını ayrı örnek olarak ekle
            for i in range(len(result['X'])):
                sample = {
                    'symbol': symbol,
                    'timestamp': str(result['date']),
                    'features': result['X'][i].tolist(),
                    'feature_names': result['feature_cols'],
                    'labels': {
                        'direction': int(result['y_direction'][i]),
                        'volatility': int(result['y_volatility'][i]),
                        'volume': int(result['y_volume'][i])
                    }
                }
                all_samples.append(sample)
    
    # Mevcut eğitim verisini yükle
    if os.path.exists(CONFIG['training_data_path']):
        with open(CONFIG['training_data_path'], 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    else:
        existing_data = []
    
    # Yeni verileri ekle
    existing_data.extend(all_samples)
    
    # Kaydet
    with open(CONFIG['training_data_path'], 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ {len(all_samples)} yeni örnek eğitim setine eklendi (Toplam: {len(existing_data)})")
    
    return len(all_samples), len(existing_data)


def retrain_model_if_needed(new_samples_count, trainer, all_data):
    """
    Yeterince yeni veri biriktiyse modeli yeniden eğitir.
    """
    if new_samples_count < CONFIG['retrain_threshold']:
        print(f"⏭️ Yeniden eğitim için yeterli veri yok ({new_samples_count}/{CONFIG['retrain_threshold']})")
        return trainer
    
    print(f"\n🔄 {new_samples_count} yeni örnek ile model güncelleniyor...")
    
    # Eğitim verisini hazırla
    with open(CONFIG['training_data_path'], 'r', encoding='utf-8') as f:
        training_data = json.load(f)
    
    # Son N örneği al (online learning için)
    recent_samples = training_data[-CONFIG['retrain_threshold']*5:]  # Son 250 örnek
    
    # Batch oluştur
    X_batch = np.array([sample['features'] for sample in recent_samples])
    y_dir_batch = np.array([sample['labels']['direction'] for sample in recent_samples])
    y_vol_batch = np.array([sample['labels']['volatility'] for sample in recent_samples])
    y_volu_batch = np.array([sample['labels']['volume'] for sample in recent_samples])
    
    # Korrelasyon matrisini yeniden hesapla
    adjacency_matrix = build_correlation_matrix(all_data, threshold=0.7)
    
    # Çevrimiçi öğrenme ile hızlı güncelleme
    trainer.partial_fit(
        X_batch,
        y_dir_batch,
        y_vol_batch,
        y_volu_batch,
        n_epochs=5,
        adjacency_matrix=adjacency_matrix
    )
    
    # Modeli kaydet
    trainer.save_model(CONFIG['model_path'])
    
    print("✅ Model başarıyla güncellendi ve kaydedildi")
    
    return trainer


# ========================================================================= #
# ANA PIPELINE
# ========================================================================= #

def run_scan_and_train_pipeline():
    """
    Ana pipeline: Tarama → Bildirim → Veri Toplama → Eğitim
    """
    print("\n" + "="*80)
    print("🚀 LFM ULTRA ADVANCED PIPELINE BAŞLIYOR")
    print(f"📅 Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    try:
        # 1. Tarama ve tahmin
        predictions, trainer = scan_market_with_deep_learning()
        
        if len(predictions) > 0:
            # 2. Telegram bildirimi
            send_scan_results_to_telegram(predictions)
            
            # 3. Scan sonuçlarını JSON'a kaydet
            with open('latest_scan_results.json', 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'predictions': predictions,
                    'total_scanned': len(predictions)
                }, f, indent=2, ensure_ascii=False)
        
        # 4. Veri çekme ve eğitim setine ekleme
        all_data = fetch_all_market_data(markets=CONFIG['markets'])
        new_count, total_count = collect_training_data(all_data)
        
        # 5. Model güncelleme (gerekirse)
        if trainer is not None:
            trainer = retrain_model_if_needed(new_count, trainer, all_data)
        
        print("\n" + "="*80)
        print("✅ PIPELINE BAŞARIYLA TAMAMLANDI")
        print("="*80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ PIPELINE HATASI: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_scan_and_train_pipeline()
    exit(0 if success else 1)
