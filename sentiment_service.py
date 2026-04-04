import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch.nn.functional as F
import requests
from bs4 import BeautifulSoup
import re
import datetime

# ========================================================================= #
# BIST DUYGU ANALİZİ (SENTIMENT) SERVİSİ
#
# Teknoloji: savasy/bert-base-turkish-sentiment-cased (Hugging Face)
# Görev: Haber başlıklarını ve KAP duyurularını okuyup duygu skoruna (-1 to 1) 
#        çevirerek LFM TCN+Attention modeline girdi sağlar.
# ========================================================================= #

class TurkishSentimentAnalyzer:
    _instance = None
    _model = None
    _tokenizer = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TurkishSentimentAnalyzer, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if TurkishSentimentAnalyzer._model is not None:
            return
            
        # Türkçe Sentiment Analysis için en başarılı açık kaynaklı model (Savaş Yıldırım)
        self.model_name = "savasy/bert-base-turkish-sentiment-cased"
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')
        
        print(f"🌍 NLP Duygu Analizi Motoru Yükleniyor ({self.model_name})...")
        TurkishSentimentAnalyzer._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        TurkishSentimentAnalyzer._model = AutoModelForSequenceClassification.from_pretrained(self.model_name).to(self.device)
        TurkishSentimentAnalyzer._model.eval()
        print("✅ FinBERT/Turkish-BERT Aktif.")

    def analyze_text(self, text):
        """Metni analiz eder ve -1 (Negatif) ile +1 (Pozitif) arası skor döner."""
        if not text or len(text) < 3:
            return 0.0 # Nötr
            
        inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=128, padding=True).to(self.device)
        
        with torch.no_grad():
            outputs = self._model(**inputs)
            probs = F.softmax(outputs.logits, dim=1)
            
        # Model çıktıları: 0 -> Negative, 1 -> Positive
        # Skoru -1 ile 1 arasına normalize edelim
        neg_prob = probs[0][0].item()
        pos_prob = probs[0][1].item()
        
        sentiment_score = pos_prob - neg_prob # Pozitif baskınsa > 0, Negatif baskınsa < 0
        return sentiment_score

class BISTNewsScraper:
    """Haber kaynaklarından (KAP simülasyonu veya haber siteleri) veri çeker."""
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    def fetch_latest_news(self, symbol):
        """Hisse özelinde haberleri simüle eder veya haber sitelerinden çeker."""
        # Gerçek uygulamada Investing.com TR veya Bloomberght.com kullanılabilir
        # Şimdilik örnek başlıklar (API yerine simülasyon/örnekleme)
        # TODO: Gerçek bir NewsAPI veya Scraper entegrasyonu buraya gelecek
        news_samples = [
            f"{symbol} hissesinden dev yatırım kararı, kâr beklentisi arttı",
            f"{symbol} bilanço verileri beklentilerin altında kaldı, satış baskısı",
            f"Borsa İstanbul'da {symbol} için hedef fiyat revize edildi",
            f"{symbol} yeni ihale kazandığını KAP'a bildirdi"
        ]
        return news_samples

class SentimentFeatureEngine:
    """Haberleri skorlayıp teknik veriye ekleyecek motor."""
    _cache = {}

    def __init__(self):
        self.analyzer = TurkishSentimentAnalyzer()
        self.scraper = BISTNewsScraper()

    def get_sentiment_score(self, symbol):
        """Sembol bazlı ağırlıklı duygu skoru üretir."""
        if not symbol: return 0.0
        
        # Cache Check (Aynı tarama içinde tekrar hesaplama)
        if symbol in self._cache:
            return self._cache[symbol]
            
        news = self.scraper.fetch_latest_news(symbol)
        if not news: 
            self._cache[symbol] = 0.0
            return 0.0
        
        scores = [self.analyzer.analyze_text(n) for n in news]
        avg_score = sum(scores) / len(scores)
        
        # Micro-adjustment for AI confidence
        final_score = round(avg_score, 4)
        self._cache[symbol] = final_score
        return final_score

if __name__ == "__main__":
    # Test
    engine = SentimentFeatureEngine()
    test_symbol = "THYAO"
    score = engine.get_sentiment_score(test_symbol)
    print(f"\n📊 {test_symbol} Duygu Analizi Skoru: {score}")
    if score > 0.3: print("🚀 Pozitif Haber Akışı!")
    elif score < -0.3: print("🚨 Negatif Haber Akışı!")
    else: print("😐 Nötr Haber Akışı.")
