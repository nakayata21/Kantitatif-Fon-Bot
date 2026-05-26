# 🚀 LFM Ultra Advanced Deep Learning Engine

## 📋 Genel Bakış

Bu proje, **Graf Sinir Ağları (GNN)**, **Temporal Fusion Transformer (TFT)**, **Çoklu Görev Öğrenimi** ve **Belirsizlik Ölçümü** gibi gelişmiş teknikleri bir araya getiren bir borsa tahmin sistemidir.

## ✨ Yeni Özellikler

### 1. 🕸️ Graf Tabanlı Öğrenme (GNN)
- Hisseler arası korelasyonları graf yapısı olarak modelleme
- Komşu hisselerden bilgi toplama ve yayılım mekanizması
- Sektörel ve piyasa geneli etkileşimleri yakalama

### 2. ⚡ Temporal Fusion Transformer (TFT) Lite
- Gelişmiş zaman serisi dikkati
- Değişken seçim mekanizması
- Pozisyonel kodlama ve kapı mekanizması
- Uzun vadeli bağımlılıkları yakalama

### 3. 🎯 Çoklu Görev Öğrenimi
- **Yön Tahmini**: Yükseliş/Düşüş (2 sınıf)
- **Volatilite Tahmini**: Düşük/Orta/Yüksek (3 sınıf)
- **Hacim Değişimi**: Düşük/Orta/Yüksek (3 sınıf)
- Tek model ile çoklu çıktı, daha iyi genelleme

### 4. 🛡️ Belirsizlik Ölçümü (Monte Carlo Dropout)
- 50 örneklemli güven aralığı hesaplama
- Tahmin standart sapması ile risk ölçümü
- Düşük güvenilirlikli sinyalleri filtreleme

### 5. 🔄 Çevrimiçi Öğrenme
- Yeni gelen veriyle hızlı adaptasyon
- `partial_fit` metodu ile 5 epoch'ta güncelleme
- Piyasa koşullarına dinamik uyum

### 6. 🔍 Özellik Önemi Analizi
- Permütasyon tabanlı önem skorları
- Kararlılık izleme ve sapma tespiti
- Model yorumlanabilirliği

## 📁 Dosyalar

| Dosya | Açıklama |
|-------|----------|
| `deep_learning_core.py` | Ana model mimarisi (724 satır) |
| `scan_and_train_deep.py` | Tarama + Eğitim pipeline'ı |
| `test_deep_learning.py` | Test script'i |
| `.github/workflows/daily_screener.yml` | GitHub Actions (her 15 dk) |

## 🏗️ Model Mimarisi

```
Ham Veri (N, Features)
    ↓
Sequence Oluşturma (N, Seq_Len=10, Features)
    ↓
┌─────────────────────────────────────┐
│  Graf Sinir Ağı (GNN) [Opsiyonel]   │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  1D-CNN (Lokal Desenler)            │
│  - Conv1d → BatchNorm → ReLU        │
│  - Conv1d → BatchNorm → ReLU        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  LSTM (Uzun Vadeli Bellek)          │
│  - Hidden: 128                      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Temporal Fusion Block [Opsiyonel]  │
│  - Variable Selection               │
│  - Multi-Head Attention             │
│  - Positional Encoding              │
│  - Gating Mechanism                 │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Multi-Head Attention               │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  LSTM 2                             │
│  - Hidden: 64                       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Multi-Task Heads                   │
│  ├─ Direction Head (2 sınıf)        │
│  ├─ Volatility Head (Regresyon)     │
│  └─ Volume Head (Regresyon)         │
└─────────────────────────────────────┘
```

## 🔧 Kullanım

### Hızlı Başlangıç

```python
from deep_learning_core import LFMPyTorchTrainerAdvanced
import numpy as np

# Veri hazırla
X = np.random.randn(500, 21).astype(np.float32)
y_direction = np.random.randint(0, 2, 500)
y_volatility = np.random.randint(0, 3, 500)
y_volume = np.random.randint(0, 3, 500)

# Model başlat
trainer = LFMPyTorchTrainerAdvanced(
    input_dim=21,
    feature_names=[f'feat_{i}' for i in range(21)],
    epochs=50,
    lr=0.001,
    batch_size=64,
    seq_length=10,
    use_gnn=True,      # Graf ağı aktif
    use_tft=True,      # TFT aktif
    enable_uncertainty=True
)

# Eğit
trainer.fit(X, y_direction, y_volatility, y_volume)

# Belirsizlikle tahmin
results = trainer.predict_with_uncertainty(X[:10])
print(f"Yükseliş Olasılığı: {results['direction']['mean'][0, 1]:.2%}")
print(f"Belirsizlik: {results['direction']['std'][0, 1]:.4f}")
```

### Pipeline Çalıştırma

```bash
# Tam pipeline (tarama + eğitim + Telegram)
python scan_and_train_deep.py

# Test
python test_deep_learning.py
```

### Model Kaydetme ve Yükleme

```python
# Kaydet
trainer.save_model('lfm_ultra_best.pth')

# Yükle
new_trainer = LFMPyTorchTrainerAdvanced(input_dim=21)
new_trainer.load_model('lfm_ultra_best.pth')
```

## 📊 Performans Metrikleri

Model şu metrikleri optimize eder:

- **Direction Loss**: CrossEntropy (label_smoothing=0.1)
- **Volatility Loss**: MSE
- **Volume Loss**: MSE
- **Total Loss**: `0.6 * Dir + 0.2 * Vol + 0.2 * Volume`

## 🤖 Otomasyon

GitHub Actions ile:
- **Her 15 dakikada** otomatik tarama
- **Her 3 günde** tam model eğitimi
- **Diğer günlerde** çevrimiçi öğrenme
- **Telegram** bildirimi

## 📈 Özellik Listesi

Model şu özellikleri kullanır:

```python
feature_cols = [
    'rsi', 'macd', 'macd_signal', 
    'bb_upper', 'bb_lower', 'bb_middle',
    'sma_20', 'sma_50', 'ema_12', 'ema_26',
    'atr', 'adx', 'obv', 'mfi',
    'stoch_k', 'stoch_d', 'williams_r', 'cci',
    'price_change_pct', 'volume_change_pct', 'volatility'
]
```

## ⚙️ Konfigürasyon

`scan_and_train_deep.py` içindeki CONFIG dict'ini düzenleyin:

```python
CONFIG = {
    'markets': ['BIST'],  # ['BIST', 'NASDAQ', 'CRYPTO']
    'min_volume': 1_000_000,
    'top_n_signals': 10,
    'confidence_threshold': 0.6,  # Min olasılık
    'uncertainty_threshold': 0.15,  # Max belirsizlik
    'retrain_threshold': 50,  # Yeni örnek sayısı
    'sequence_length': 10,
    'use_gnn': True,
    'use_tft': True,
    'enable_uncertainty': True
}
```

## 🧪 Test Sonuçları

```
✅ GNN (Graf Sinir Ağları): Çalışıyor
✅ TFT (Temporal Fusion Transformer): Çalışıyor
✅ Çoklu Görev Öğrenimi: Çalışıyor
✅ Monte Carlo Belirsizlik: Çalışıyor
✅ Özellik Önemi Analizi: Çalışıyor
✅ Model Kaydetme/Yükleme: Çalışıyor
✅ Çevrimiçi Öğrenme: Hazır
```

## 📝 Notlar

1. **GPU Desteği**: CUDA veya MPS (Mac) otomatik algılanır
2. **Batch Size**: GPU belleğine göre 32-128 arası ayarlayın
3. **Sequence Length**: Kısa vade için 5-10, uzun vade için 20-30
4. **Early Stopping**: Validasyon kaybı 10 epoch düşmezse durur

## 🚀 Gelecek Geliştirmeler

- [ ] Meta-öğrenme ile hızlı adaptasyon
- [ ] Nedensel çıkarım modülleri
- [ ] Derin topluluk (ensemble) çeşitliliği
- [ ] Hiperparametre zamanlama
- [ ] Anomaly detection entegrasyonu

## 📄 Lisans

Proje özel kullanım içindir.

---

**Son Güncelleme**: 2025-04-02
**Versiyon**: 2.0 Ultra Advanced
