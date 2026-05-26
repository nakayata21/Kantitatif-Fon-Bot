# 🚀 LFM Ultra Advanced - Tarama ve Otomatik Eğitim Sistemi

## 📋 Genel Bakış

Bu sistem, GitHub Actions üzerinde çalışan otomatik hisse tarama ve makine öğrenimi eğitimi pipeline'ıdır. Her 15 dakikada bir piyasaları tarar, Telegram'a bildirim gönderir ve toplanan verilerle modeli sürekli geliştirir.

## ✨ Özellikler

### 1. **Otomatik Tarama**
- **Piyasalar**: BIST, NASDAQ
- **Sıklık**: Her 15 dakikada (09:00-00:00 TR saati)
- **Çıktı**: Telegram bildirimi + JSON/CSV kayıtları

### 2. **Derin Öğrenme Motoru (LFM Ultra Advanced)**
- **Graf Sinir Ağları (GNN)**: Hisse senetleri arası korelasyonları modelleme
- **Temporal Fusion Transformer (TFT)**: Gelişmiş zaman serisi dikkati
- **Çoklu Görev Öğrenimi**: Yön + Volatilite + Hacim tahmini
- **Belirsizlik Ölçümü**: Monte Carlo Dropout ile güven skorları
- **Çevrimiçi Öğrenme**: Yeni verilere hızlı adaptasyon

### 3. **Veri Toplama ve Eğitim**
- Her taramadan sonra özellik vektörleri kaydedilir
- `training_data_all.json`: Birikimli eğitim verisi (max 10,000 örnek)
- Otomatik model eğitimi (3 günde bir veya manuel)

## 🛠️ Kullanım

### Manuel Tarama ve Eğitim

```bash
# Sadece tarama (eğitim yok)
python scan_and_train.py --market BIST --train False

# Tarama + Eğitim
python scan_and_train.py --market BIST --train True

# Özel sembol listesi
python scan_and_train.py --market BIST --train False --symbols "THYAO,ASELS,GARAN"

# NASDAQ taraması
python scan_and_train.py --market NASDAQ --train True
```

### Parametreler

| Parametre | Açıklama | Varsayılan | Seçenekler |
|-----------|----------|------------|------------|
| `--market` | Taranacak piyasa | BIST | BIST, NASDAQ, CRYPTO |
| `--train` | Model eğitimi yapılacak mı? | False | True, False |
| `--symbols` | Virgülle ayrılmış sembol listesi | Tüm liste | "THYAO,ASELS" |

## 📊 Çıktı Dosyaları

### Tarama Sonuçları
- `latest_scan_results.json`: En son tarama özeti
- `full_scan_BIST.csv`: Tüm semboller için detaylı sonuçlar
- `full_scan_NASDAQ.csv`: NASDAQ sonuçları

### Eğitim Verileri
- `training_data_BIST_YYYYMMDD_HHMMSS.json`: Günlük snapshot
- `training_data_BIST_YYYYMMDD_HHMMSS.csv`: CSV formatı
- `training_data_all.json`: Birikimli veri (incremental learning)

### Modeller
- `lfm_ultra_checkpoint_YYYYMMDD_HHMMSS.pth`: PyTorch checkpoint
- `ai_model_YYYYMMDD_HHMMSS.pkl`: Scikit-Learn fallback modeli

## ⚙️ GitHub Actions Entegrasyonu

### Workflow Ayarları

`.github/workflows/daily_screener.yml` dosyası:

```yaml
on:
  schedule:
    - cron: '*/15 6-20 * * 1-5'  # Hafta içi 09:00-00:00 TR
  workflow_dispatch:  # Manuel tetikleme

env:
  ENABLE_AUTO_TRAINING: 'true'      # Otomatik eğitim aktif mi?
  TRAINING_INTERVAL_DAYS: '3'       # Kaç günde bir tam eğitim?
```

### Secrets (Gerekli)

```
TELEGRAM_BOT_TOKEN: Bot token'ınız
TELEGRAM_CHAT_ID: Bildirim alınacak chat ID
OPENROUTER_API_KEY: AI yorumları için (opsiyonel)
GITHUB_TOKEN: Repo push için (otomatik)
```

## 📈 Model Performansı

### Beklenen Metrikler

| Görev | Hedef Doğruluk | Açıklama |
|-------|----------------|----------|
| Yön Tahmini | %55-65 | 1 günlük fiyat yönü |
| Volatilite | %60-70 | Düşük/Orta/Yüksek sınıflandırma |
| Hacim | %55-65 | Hacim değişim yönü |
| Belirsizlik | < 0.15 | Ortalama standart sapma |

### Özellik Önemi Analizi

```python
from deep_learning_core import LFMPyTorchTrainerAdvanced

trainer = LFMPyTorchTrainerAdvanced(input_dim=20)
importance = trainer.get_feature_importance(X_test, y_test)
print(importance.head(10))
```

## 🔧 Sorun Giderme

### Yetersiz Disk Alanı

```bash
# Eski checkpoint'leri temizle
rm lfm_ultra_checkpoint_*.pth
rm ai_model_*.pkl

# Eski eğitim verilerini temizle (birikimli dosya hariç)
rm training_data_BIST_*.json
rm training_data_NASDAQ_*.json
```

### Memory Allocation Hatası

```bash
# NLP modelini atla (442MB tasarruf)
export SKIP_NLP=true
python scan_and_train.py --market BIST --train False
```

### Model Eğitimi Başarısız

```bash
# Minimum veri kontrolü
cat training_data_all.json | python -c "import json,sys; d=json.load(sys.stdin); print(f'Örnek sayısı: {len(d)}')"

# En az 100 örnek gerekli
```

## 📝 Örnek Çıktı

```
============================================================
🚀 LFM ULTRA ADVANCED - TARAMA VE EĞİTİM
============================================================
📅 Zaman: 2026-05-25 20:06:18
🏛️ Piyasa: BIST
📊 Sembol Sayısı: 300
🧠 Eğitim: EVET
============================================================

🔍 BIST taraması başlıyor... (300 sembol)
   İlerleme: 20/300
   İlerleme: 40/300
   ...
✅ Tarama tamamlandı: 298 sembol işlendi
📦 Eğitim verisi: 298 örnek

🏆 EN İYİ 10 HİSSE:
 symbol  close signal  quality_score decision
 THYAO   285.5 AL      87            BUY
 ASELS   42.3  AL      82            BUY
 GARAN   78.9  BEKLE   75            HOLD

✅ Eğitim verisi kaydedildi: training_data_BIST_20260525_200618.json
📚 Toplam eğitim verisi: 3542 örnek

🧠 Model eğitimi başlıyor...
🤖 LFM Ultra Advanced (PyTorch) kullanılıyor...
   🌀 LSTM+CNN Epoch [1/30] - Loss: 0.6931 - LR: 0.001000
   ...
✅ Model kaydedildi: lfm_ultra_checkpoint_20260525_200730.pth
📈 Test Doğruluğu: %62.3
📊 Ortalama Belirsizlik: 0.1234

📬 Telegram'a gönderildi: 2 alıcı
✅ İŞLEM TAMAMLANDI
```

## 🎯 Gelecek Geliştirmeler

- [ ] Graf yapısını dinamik olarak güncelleme (korelasyon matrisi)
- [ ] Meta-öğrenme ile yeni piyasalara hızlı adaptasyon
- [ ] Nedensel çıkarım ile yanıltıcı korelasyonları filtreleme
- [ ] Hyperparameter time scheduling (Optuna ile)
- [ ] Ensemble çeşitliliği izleme ve optimizasyon

## 📞 Destek

Sorularınız için GitHub Issues açabilirsiniz.
