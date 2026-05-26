"""
🚀 LFM ULTRA ADVANCED - BİRLEŞİK TARAMA VE EĞİTİM VERİSİ TOPLAMA

Bu script:
1. Belirtilen piyasayı tarar (BIST/NASDAQ/CRYPTO)
2. Sonuçları Telegram'a gönderir
3. Model eğitimi için gerekli verileri toplar ve kaydeder
4. İsteğe bağlı olarak modeli yeniden eğitir

Kullanım:
    python scan_and_train.py --market BIST --train True
    python scan_and_train.py --market NASDAQ --train False
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np

# Çevre değişkenlerini yükle
from dotenv import load_dotenv
load_dotenv()

# Sabitler ve temel modüller
from constants import DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER, DEFAULT_CRYPTO_SYMBOLS, TIMEFRAME_OPTIONS

# Telegram fonksiyonlarını içeri aktar (döngüsel bağımlılığı önlemek için)
def send_msg(chat_id, text, reply_markup=None):
    """Basit Telegram mesaj gönderme fonksiyonu"""
    import os
    import requests
    import json
    
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN bulunamadı")
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        r = requests.post(url, data=payload, timeout=12)
        if r.status_code != 200:
            print(f"⚠️ Telegram Mesaj Hatası: {r.status_code}")
    except Exception as e:
        print(f"❌ Mesaj Gönderilemedi: {e}")

ALLOWED_CHAT_IDS = [os.environ.get("TELEGRAM_CHAT_ID", "1070470722")]

# Diğer modüller
from scan_pipeline import prepare_symbol_dataframes, attach_divergence_to_last
from scoring import score_symbol
from indicators import calculate_price_targets
from utils import _safe_get
from reporting import format_telegram_message
from data_fetcher import get_cached_index_history, check_index_health

# Deep Learning modülü
try:
    from deep_learning_core import LFMPyTorchTrainerAdvanced
    HAS_DEEP_LEARNING = True
except ImportError:
    HAS_DEEP_LEARNING = False
    print("⚠️ deep_learning_core modülü bulunamadı. Klasik eğitim kullanılacak.")


def run_comprehensive_scan(
    symbols: List[str],
    market: str,
    tf_name: str = "Gunluk",
    delay_ms: int = 300,
    workers: int = 5,
    skip_nlp: bool = True  # NLP modelini atla (disk alanı tasarrufu)
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Kapsamlı tarama yapar ve tüm sonuçları döner.
    
    Returns:
        df: Tarama sonuç DataFrame'i
        training_data: Model eğitimi için hazırlanmış veri listesi
    """
    from tvDatafeed import TvDatafeed
    import concurrent.futures
    from threading import Lock
    
    print(f"🔍 {market} taraması başlıyor... ({len(symbols)} sembol)")
    
    tv = TvDatafeed()
    tf = TIMEFRAME_OPTIONS.get(tf_name, TIMEFRAME_OPTIONS["Gunluk"])
    tv_exchange = "BINANCE" if market == "CRYPTO" else market
    
    # Endeks sağlığını kontrol et
    index_healthy = check_index_health(tv, market, tf_name)
    global_index_df = get_cached_index_history(market, tf_name, bars=tf["bars"])
    
    results = []
    training_data = []
    lock = Lock()
    
    def process_symbol(symbol: str) -> Dict:
        try:
            prep = prepare_symbol_dataframes(
                tv, symbol, tv_exchange, tf,
                global_index_df=global_index_df,
                delay_ms=delay_ms,
                worker_id=0
            )
            
            if not prep.get("ok"):
                return None
            
            vb = prep["vb"]
            vc = prep["vc"]
            last = prep["last"]
            prev = prep["prev"]
            conf_last = prep["conf_last"]
            
            # Uyumsuzluk analizi
            attach_divergence_to_last(last, prep["base_raw"])
            
            # Skorlama
            s = score_symbol(last, prev, conf_last, market, index_healthy)
            
            # Hedef fiyatlar
            targets = calculate_price_targets(vb)
            
            # Sonuçları hazırla
            result = {
                "symbol": symbol,
                "market": market,
                "close": round(float(last["close"]), 2),
                "change_pct": s.get("Günlük %", 0),
                "signal": s["Sinyal"],
                "action": s["Aksiyon"],
                "quality_score": s["Kalite"],
                "trend_score": s["Trend Skor"],
                "momentum_score": s["Momentum Skor"],
                "dip_score": s["Dip Skor"],
                "breakout_score": s["Breakout Skor"],
                "rsi": round(float(last["rsi"]), 1),
                "adx": round(float(last["adx"]), 1),
                "macd_hist": round(float(last["macd_hist"]), 4),
                "atr_pct": round(float(last["atr_pct"]), 2),
                "vol_spike": round(float(_safe_get(last, "vol_spike", 0)), 2),
                "decision": s["Decision"],
                "risk_reward": s.get("R/R", 0),
                "bayesian_prob": s.get("Bayesian Prob", 0.5),
                "physics_score": s.get("Fizik Skor", 0),
                "timestamp": datetime.now().isoformat()
            }
            
            # Eğitim verisi için özellikleri topla
            feature_cols = [col for col in vb.columns 
                          if col not in ['open', 'high', 'low', 'close', 'volume']
                          and vb[col].dtype in [np.float64, np.int64, float, int]]
            
            if len(feature_cols) >= 5:
                features = vb[feature_cols].iloc[-1].to_dict()
                features['symbol'] = symbol
                features['market'] = market
                features['timestamp'] = datetime.now().isoformat()
                
                # Etiket: Gelecek yön (şimdilik mevcut günün kapanış > açılış)
                features['label_direction'] = 1 if last['close'] > last['open'] else 0
                
                # Volatilite: ATR yüzdesine göre
                atr_val = last.get('atr_pct', 0)
                if atr_val < 1.5:
                    features['label_volatility'] = 0
                elif atr_val < 3.0:
                    features['label_volatility'] = 1
                else:
                    features['label_volatility'] = 2
                
                # Hacim değişimi
                vol_ratio = last.get('volume', 0) / (vb['volume'].rolling(20).mean().iloc[-1] + 1e-9)
                if vol_ratio < 0.8:
                    features['label_volume'] = 0
                elif vol_ratio < 1.5:
                    features['label_volume'] = 1
                else:
                    features['label_volume'] = 2
                
                with lock:
                    training_data.append(features)
            
            return result
            
        except Exception as e:
            print(f"⚠️ {symbol} hatası: {e}")
            return None
    
    # Paralel işlem
    max_workers = min(workers, len(symbols))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_symbol, sym): sym for sym in symbols}
        
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            result = future.result()
            if result:
                results.append(result)
            
            if (i + 1) % 20 == 0:
                print(f"   İlerleme: {i+1}/{len(symbols)}")
    
    # DataFrame'e çevir
    if results:
        df = pd.DataFrame(results)
        df = df.sort_values("quality_score", ascending=False)
    else:
        df = pd.DataFrame()
    
    print(f"✅ Tarama tamamlandı: {len(results)} sembol işlendi")
    print(f"📦 Eğitim verisi: {len(training_data)} örnek")
    
    return df, training_data


def save_training_data(training_data: List[Dict], market: str):
    """Eğitim verisini JSON ve CSV olarak kaydeder."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON formatında kaydet
    json_path = f"training_data_{market}_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(training_data, f, ensure_ascii=False, indent=2)
    
    # CSV formatında kaydet
    if training_data:
        df = pd.DataFrame(training_data)
        csv_path = f"training_data_{market}_{timestamp}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"✅ Eğitim verisi kaydedildi: {json_path}, {csv_path}")
    
    # En son veriyi güncelle (incremental learning için)
    all_data_path = "training_data_all.json"
    if os.path.exists(all_data_path):
        try:
            with open(all_data_path, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except:
            all_data = []
    else:
        all_data = []
    
    all_data.extend(training_data)
    
    # Son 10000 örneği sakla (çok büyümesin)
    if len(all_data) > 10000:
        all_data = all_data[-10000:]
    
    with open(all_data_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    print(f"📚 Toplam eğitim verisi: {len(all_data)} örnek")


def train_model_with_new_data(market: str = "BIST", use_deep_learning: bool = True):
    """
    Yeni toplanan verilerle modeli eğitir veya günceller.
    """
    print("\n🧠 Model eğitimi başlıyor...")
    
    all_data_path = "training_data_all.json"
    if not os.path.exists(all_data_path):
        print("❌ Eğitim verisi bulunamadı! Önce tarama yapın.")
        return
    
    with open(all_data_path, "r", encoding="utf-8") as f:
        all_data = json.load(f)
    
    if len(all_data) < 100:
        print(f"⚠️ Yetersiz veri ({len(all_data)} örnek). En az 100 örnek gerekli.")
        return
    
    # DataFrame'e çevir
    df = pd.DataFrame(all_data)
    
    # Özellik sütunlarını belirle
    exclude_cols = ['symbol', 'market', 'timestamp', 'label_direction', 'label_volatility', 'label_volume']
    feature_cols = [col for col in df.columns if col not in exclude_cols]
    
    X = df[feature_cols].values
    y_dir = df['label_direction'].values
    y_vol = df['label_volatility'].values
    y_volm = df['label_volume'].values
    
    # NaN değerleri temizle
    mask = ~np.isnan(X).any(axis=1)
    X = X[mask]
    y_dir = y_dir[mask]
    y_vol = y_vol[mask]
    y_volm = y_volm[mask]
    
    print(f"📊 Eğitim verisi: {len(X)} örnek, {X.shape[1]} özellik")
    
    # Train/Test split
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_dir_train, y_dir_test = y_dir[:split_idx], y_dir[split_idx:]
    
    if use_deep_learning and HAS_DEEP_LEARNING:
        # Derin öğrenme modeli
        print("🤖 LFM Ultra Advanced (PyTorch) kullanılıyor...")
        
        trainer = LFMPyTorchTrainerAdvanced(
            input_dim=X_train.shape[1],
            use_gnn=True,
            use_tft=True,
            enable_uncertainty=True,
            epochs=30,
            lr=0.001,
            batch_size=64,
            seq_length=10
        )
        
        # Çoklu görev eğitimi
        trainer.fit(
            X_train, y_dir_train, y_vol_train=y_vol[:split_idx], y_volume_train=y_volm[:split_idx],
            X_val=X_test,
            y_direction_val=y_dir_test,
            y_volatility_val=y_vol[split_idx:],
            y_volume_val=y_volm[split_idx:]
        )
        
        # Modeli kaydet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_path = f"lfm_ultra_checkpoint_{timestamp}.pth"
        trainer.save_checkpoint(checkpoint_path, metrics={'samples': len(X_train)})
        
        print(f"✅ Model kaydedildi: {checkpoint_path}")
        
        # Test sonuçları
        test_results = trainer.predict_with_uncertainty(X_test)
        direction_pred = np.argmax(test_results['direction']['mean'], axis=1)
        accuracy = (direction_pred == y_dir_test).mean()
        print(f"📈 Test Doğruluğu: %{accuracy*100:.1f}")
        print(f"📊 Ortalama Belirsizlik: {test_results['direction']['std'].mean():.4f}")
        
    else:
        # Klasik Scikit-Learn modeli (fallback)
        print("📦 Scikit-Learn Random Forest kullanılıyor...")
        
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        
        model = Pipeline([
            ('scaler', StandardScaler()),
            ('clf', RandomForestClassifier(
                n_estimators=200,
                max_depth=15,
                min_samples_split=5,
                class_weight='balanced',
                random_state=42,
                n_jobs=-1
            ))
        ])
        
        model.fit(X_train, y_dir_train)
        
        # Test
        y_pred = model.predict(X_test)
        accuracy = (y_pred == y_dir_test).mean()
        print(f"📈 Test Doğruluğu: %{accuracy*100:.1f}")
        
        # Modeli kaydet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_path = f"ai_model_{timestamp}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model, f)
        
        print(f"✅ Model kaydedildi: {model_path}")
    
    print("🎉 Eğitim tamamlandı!\n")


def send_scan_to_telegram(df: pd.DataFrame, market: str, chat_ids: List[str]):
    """Tarama sonuçlarını Telegram'a gönderir."""
    if df.empty:
        print("⚠️ Gönderilecek tarama sonucu yok.")
        return
    
    msg = format_telegram_message(market, df, status="OPEN")
    
    for chat_id in chat_ids:
        send_msg(chat_id, msg)
    
    print(f"📬 Telegram'a gönderildi: {len(chat_ids)} alıcı")


def main():
    parser = argparse.ArgumentParser(description="LFM Tarama ve Eğitim Scripti")
    parser.add_argument("--market", type=str, default="BIST", 
                       choices=["BIST", "NASDAQ", "CRYPTO"],
                       help="Taranacak piyasa")
    parser.add_argument("--train", type=str, default="False",
                       choices=["True", "False"],
                       help="Model eğitimi yapılacak mı?")
    parser.add_argument("--symbols", type=str, default=None,
                       help="Özel sembol listesi (virgülle ayrılmış)")
    
    args = parser.parse_args()
    
    # Sembol listesini belirle
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    elif args.market == "BIST":
        symbols = DEFAULT_BIST_HISSELER
    elif args.market == "NASDAQ":
        symbols = DEFAULT_NASDAQ_HISSELER
    else:
        symbols = DEFAULT_CRYPTO_SYMBOLS
    
    print(f"\n{'='*60}")
    print(f"🚀 LFM ULTRA ADVANCED - TARAMA VE EĞİTİM")
    print(f"{'='*60}")
    print(f"📅 Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🏛️ Piyasa: {args.market}")
    print(f"📊 Sembol Sayısı: {len(symbols)}")
    print(f"🧠 Eğitim: {'EVET' if args.train == 'True' else 'HAYIR'}")
    print(f"{'='*60}\n")
    
    # 1. Tarama yap
    df, training_data = run_comprehensive_scan(
        symbols=symbols,
        market=args.market,
        tf_name="Gunluk",
        delay_ms=200,
        workers=8
    )
    
    if df.empty:
        print("❌ Tarama başarısız!")
        return
    
    # 2. En iyi 10 hisseyi göster
    print("\n🏆 EN İYİ 10 HİSSE:")
    top_10 = df.head(10)[["symbol", "close", "signal", "quality_score", "decision"]]
    print(top_10.to_string(index=False))
    
    # 3. Eğitim verisini kaydet
    if training_data:
        save_training_data(training_data, args.market)
    
    # 4. Telegram'a gönder
    send_scan_to_telegram(df, args.market, ALLOWED_CHAT_IDS)
    
    # 5. İstenirse modeli eğit
    if args.train == "True":
        train_model_with_new_data(args.market, use_deep_learning=HAS_DEEP_LEARNING)
    
    print(f"\n{'='*60}")
    print("✅ İŞLEM TAMAMLANDI")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
