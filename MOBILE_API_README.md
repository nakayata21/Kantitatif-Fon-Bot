# Mobil Uygulama API Entegrasyonu

Bu doküman, GitHub Actions tarama sisteminin mobil uygulamaya nasıl bağlanacağını açıklar.

## 📋 Genel Bakış

Sistem 3 ana bileşenden oluşur:

1. **GitHub Actions** → Tarama yapar ve sonuçları API'ye gönderir
2. **Mobile API** (`/api/mobile`) → Verileri alır ve mobil uygulamanın erişimine sunar
3. **Mobil Uygulama** → API'den verileri çeker ve kullanıcıya gösterir

## 🔌 API Endpointleri

### 1. Webhook - GitHub Actions'tan veri almak için

**Endpoint:** `POST /api/mobile/webhook`

**Kullanım:** GitHub Actions tarama sonrası bu endpoint'e POST request gönderir.

**Request Body Örneği:**
```json
{
  "market": "BIST",
  "status": "OPEN",
  "scan_time": "2025-06-01T14:30:00+03:00",
  "results": [
    {
      "hisse": "THYAO",
      "fiyat": 285.50,
      "sinyal": "AL",
      "aksiyon": "Uzun Vadeli Alım",
      "kalite": 92.5,
      "hedef_1": 320.00,
      "hedef_1_pct": 12.1,
      "stop_loss": 270.00,
      "stop_pct": 5.4,
      "rr_orani": 2.23,
      "ozel_durum": "Pozitif Uyumsuzluk + UT Bot",
      "ultimate_sinyal": true,
      "ai_tahmin": 87.3,
      "trend_skor": 8.5,
      "dip_skor": 7.2,
      "momentum_skor": 9.1,
      "market_regime": "TREND"
    }
  ],
  "summary": {
    "total_symbols": 30,
    "buy_count": 5,
    "avg_quality": 78.5,
    "top_quality_symbol": "THYAO",
    "ultimate_count": 2
  },
  "ai_commentary": "AI analiz metni buraya..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "BIST için 30 sembol işlendi, 5 AL sinyali",
  "market": "BIST",
  "timestamp": "2025-06-01T14:30:00+03:00"
}
```

---

### 2. Tarama Sonuçlarını Almak İçin

**Endpoint:** `GET /api/mobile/scan-results`

**Parametreler:**
- `market` (opsiyonel): "BIST", "NASDAQ", "CRYPTO" - Belirtilmezse tüm piyasalar döner

**Kullanım:** Mobil uygulama periyodik olarak bu endpoint'i çağırarak son tarama sonuçlarını alır.

**Response Örneği (Tek Market):**
```json
{
  "market": "BIST",
  "status": "OPEN",
  "timestamp": "2025-06-01T14:30:00+03:00",
  "received_at": "2025-06-01T14:30:05+03:00",
  "result_count": 30,
  "buy_signals": 5,
  "summary": {
    "total_symbols": 30,
    "buy_count": 5,
    "avg_quality": 78.5,
    "top_quality_symbol": "THYAO",
    "ultimate_count": 2
  },
  "ai_commentary": "AI analiz metni buraya...",
  "results": [
    {
      "hisse": "THYAO",
      "fiyat": 285.50,
      "sinyal": "AL",
      "aksiyon": "Uzun Vadeli Alım",
      "kalite": 92.5,
      "hedef_1": 320.00,
      "hedef_1_pct": 12.1,
      "stop_loss": 270.00,
      "stop_pct": 5.4,
      "rr_orani": 2.23,
      "ozel_durum": "Pozitif Uyumsuzluk + UT Bot",
      "ultimate_sinyal": true,
      "ai_tahmin": 87.3,
      "trend_skor": 8.5,
      "dip_skor": 7.2,
      "momentum_skor": 9.1,
      "market_regime": "TREND",
      "pe_ratio": 5.2,
      "pb_ratio": 1.8,
      "isy_grade": "A"
    }
  ]
}
```

**Response Örneği (Tüm Marketler):**
```json
{
  "BIST": {
    "status": "OPEN",
    "timestamp": "2025-06-01T14:30:00+03:00",
    "result_count": 30,
    "buy_signals": 5,
    "results": [...]
  },
  "NASDAQ": {
    "status": "CLOSED",
    "timestamp": "2025-06-01T08:00:00+03:00",
    "result_count": 30,
    "buy_signals": 3,
    "results": [...]
  },
  "CRYPTO": {
    "status": "OPEN",
    "timestamp": "2025-06-01T14:30:00+03:00",
    "result_count": 30,
    "buy_signals": 8,
    "results": [...]
  }
}
```

---

### 3. Sağlık Kontrolü

**Endpoint:** `GET /api/mobile/health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-06-01T14:35:00+03:00",
  "markets_available": ["BIST", "NASDAQ", "CRYPTO"]
}
```

---

### 4. Son Güncelleme Zamanları

**Endpoint:** `GET /api/mobile/last-update`

**Response:**
```json
{
  "BIST": {
    "last_scan": "2025-06-01T14:30:00+03:00",
    "received_at": "2025-06-01T14:30:05+03:00",
    "status": "OPEN",
    "symbol_count": 30
  },
  "NASDAQ": {
    "last_scan": "2025-06-01T08:00:00+03:00",
    "received_at": "2025-06-01T08:00:03+03:00",
    "status": "CLOSED",
    "symbol_count": 30
  },
  "CRYPTO": {
    "last_scan": "2025-06-01T14:30:00+03:00",
    "received_at": "2025-06-01T14:30:05+03:00",
    "status": "OPEN",
    "symbol_count": 30
  }
}
```

---

## 📱 Mobil Uygulama Entegrasyonu

### Örnek Kod (React Native / TypeScript)

```typescript
const API_BASE_URL = 'https://your-server.com/api/mobile';

interface ScanResult {
  hisse: string;
  fiyat: number;
  sinyal: 'AL' | 'SAT' | 'BEKLE';
  aksiyon: string;
  kalite: number;
  hedef_1?: number;
  hedef_1_pct?: number;
  stop_loss?: number;
  stop_pct?: number;
  rr_orani?: number;
  ozel_durum: string;
  ultimate_sinyal: boolean;
  ai_tahmin: number;
  trend_skor: number;
  dip_skor: number;
  momentum_skor: number;
  market_regime: string;
}

interface MarketData {
  status: string;
  timestamp: string;
  result_count: number;
  buy_signals: number;
  summary?: {
    total_symbols: number;
    buy_count: number;
    avg_quality: number;
    top_quality_symbol: string;
    ultimate_count: number;
  };
  ai_commentary?: string;
  results: ScanResult[];
}

async function fetchScanResults(market?: string): Promise<MarketData | Record<string, MarketData>> {
  const url = market 
    ? `${API_BASE_URL}/scan-results?market=${market}`
    : `${API_BASE_URL}/scan-results`;
  
  const response = await fetch(url);
  if (!response.ok) throw new Error('API request failed');
  return await response.json();
}

// Kullanım örnekleri:
// Tüm piyasaları getir
const allMarkets = await fetchScanResults();

// Sadece BIST'i getir
const bistData = await fetchScanResults('BIST');

// AL sinyallerini filtrele
const buySignals = bistData.results.filter(r => r.sinyal === 'AL');
```

### Örnek Kod (Flutter / Dart)

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

class ScanResult {
  final String hisse;
  final double fiyat;
  final String sinyal;
  final String aksiyon;
  final double kalite;
  final double? hedef1;
  final double? stopLoss;
  final bool ultimateSinyal;
  // ... diğer alanlar

  factory ScanResult.fromJson(Map<String, dynamic> json) {
    return ScanResult(
      hisse: json['hisse'],
      fiyat: (json['fiyat'] ?? 0).toDouble(),
      sinyal: json['sinyal'],
      aksiyon: json['aksiyon'],
      kalite: (json['kalite'] ?? 0).toDouble(),
      hedef1: json['hedef_1']?.toDouble(),
      stopLoss: json['stop_loss']?.toDouble(),
      ultimateSinyal: json['ultimate_sinyal'] ?? false,
    );
  }
}

Future<Map<String, dynamic>> fetchScanResults({String? market}) async {
  final url = Uri.parse(
    market != null 
      ? 'http://your-server.com/api/mobile/scan-results?market=$market'
      : 'http://your-server.com/api/mobile/scan-results'
  );
  
  final response = await http.get(url);
  if (response.statusCode == 200) {
    return json.decode(response.body);
  }
  throw Exception('Failed to load scan results');
}

// Kullanım
void loadBistSignals() async {
  try {
    final data = await fetchScanResults(market: 'BIST');
    final results = (data['results'] as List)
        .map((r) => ScanResult.fromJson(r))
        .toList();
    
    final buySignals = results.where((r) => r.sinyal == 'AL').toList();
    print('Found ${buySignals.length} buy signals');
  } catch (e) {
    print('Error: $e');
  }
}
```

---

## 🔧 GitHub Actions Yapılandırması

### Gerekli Environment Variables

GitHub Secrets olarak aşağıdakileri ekleyin:

```yaml
env:
  MOBILE_API_URL: https://your-server.com/api/mobile/webhook
  API_SECRET_KEY: your-secret-key  # Opsiyonel güvenlik için
  TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
  TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
  OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

### Workflow Örneği

```yaml
name: Stock Scanner

on:
  schedule:
    - cron: '0 */2 * * *'  # Her 2 saatte bir
  workflow_dispatch:

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run Scanner
        env:
          MOBILE_API_URL: ${{ secrets.MOBILE_API_URL }}
          API_SECRET_KEY: ${{ secrets.API_SECRET_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          TARGET_MARKET: BIST
        run: python github_scan_action.py
      
      - name: Upload Results as Artifact
        uses: actions/upload-artifact@v3
        with:
          name: mobile-scan-results
          path: mobile_scan_results.json
```

---

## 🔒 Güvenlik Önerileri

1. **API Secret Key:** Production ortamında `X-API-Key` header'ı ile istemcileri doğrulayın
2. **HTTPS:** API'nizi mutlaka HTTPS üzerinden yayınlayın
3. **Rate Limiting:** Mobil uygulama için rate limiting ekleyin
4. **Authentication:** Kullanıcı bazlı erişim için JWT veya OAuth ekleyebilirsiniz

---

## 📊 Veri Alanları Açıklaması

| Alan | Tip | Açıklama |
|------|-----|----------|
| `hisse` | string | Hisse senedi sembolü |
| `fiyat` | float | Güncel fiyat |
| `sinyal` | string | AL/SAT/BEKLE |
| `aksiyon` | string | Önerilen işlem |
| `kalite` | float | 0-100 arası kalite skoru |
| `hedef_1` | float | Birinci hedef fiyat |
| `hedef_1_pct` | float | Hedef yüzdesi |
| `stop_loss` | float | Stop loss fiyatı |
| `stop_pct` | float | Stop loss yüzdesi |
| `rr_orani` | float | Risk/Reward oranı |
| `ozel_durum` | string | Özel teknik durum |
| `ultimate_sinyal` | bool | UT Bot + Uyumsuzluk |
| `ai_tahmin` | float | AI tahmin olasılığı (%) |
| `trend_skor` | float | Trend gücü (0-10) |
| `dip_skor` | float | Dip yakalama skoru (0-10) |
| `momentum_skor` | float | Momentum skoru (0-10) |
| `market_regime` | string | Piyasa rejimi (TREND/ACCUMULATION/BEAR/MIXED) |
| `pe_ratio` | float | F/K oranı |
| `pb_ratio` | float | PD/DD oranı |
| `isy_grade` | string | İş Yatırım notu |

---

## 🚀 Hızlı Başlangıç

1. **Server'ı başlatın:**
   ```bash
   python server.py
   ```

2. **API'yi test edin:**
   ```bash
   curl http://localhost:8000/api/mobile/health
   ```

3. **Manuel webhook testi:**
   ```bash
   curl -X POST http://localhost:8000/api/mobile/webhook \
     -H "Content-Type: application/json" \
     -d '{"market":"BIST","status":"OPEN","scan_time":"2025-06-01T14:30:00","results":[],"summary":{}}'
   ```

4. **Sonuçları kontrol edin:**
   ```bash
   curl http://localhost:8000/api/mobile/scan-results
   ```
