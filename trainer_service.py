import yfinance as yf
import pandas as pd
import numpy as np
from signals_db import get_unlabeled_signals, update_label, get_training_data
from sklearn.ensemble import RandomForestClassifier
import pickle
import os

MODEL_PATH = "ai_model.pkl"

def get_current_price(symbol, exchange):
    """Sembolün güncel fiyatını çeker."""
    try:
        ticker = symbol if exchange != "BIST" else f"{symbol}.IS"
        data = yf.download(ticker, period="1d", progress=False)
        if not data.empty:
            return float(data['Close'].iloc[-1])
    except:
        pass
    return None

def label_past_signals():
    """5 gün önce verilen sinyalleri kontrol eder ve kâr/zarar etiketini basar."""
    df = get_unlabeled_signals(days_ago=5)
    print(f"🔍 {len(df)} adet etiketlenmemiş sinyal inceleniyor...")
    
    for _, row in df.iterrows():
        curr_price = get_current_price(row['symbol'], row['exchange'])
        if curr_price:
            entry_price = row['price_at_signal']
            # Yüzde Değişim
            diff = ((curr_price - entry_price) / entry_price) * 100
            update_label(row['id'], diff)
            print(f"✅ {row['symbol']} etiketlendi: %{round(diff, 2)}")

def retrain_model():
    """Veritabanındaki tüm etiketli verilerle modeli yeniden eğitir."""
    data = get_training_data()
    if len(data) < 50:
        print("⚠️ Yetersiz veri (en az 50 örnek gerekli). Eğitim atlanıyor.")
        return
    
    # Target = Success (outcome > 3.5%)
    X = data.drop(columns=['target'])
    y = data['target']
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    
    print(f"🚀 AI Modeli {len(data)} veri üzerinde başarıyla yeniden eğitildi!")

if __name__ == "__main__":
    # 1. Önce etiketle
    label_past_signals()
    # 2. Sonra eğit
    retrain_model()
