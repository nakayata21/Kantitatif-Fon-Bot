import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta

DB_PATH = "signals_log.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    exchange TEXT,
                    time_at_signal TEXT,
                    price_at_signal REAL,
                    signal_type TEXT,
                    features JSON,
                    outcome REAL,
                    is_labeled INTEGER DEFAULT 0,
                    label_time TEXT
                )''')
    conn.commit()
    conn.close()

def log_signal(symbol, exchange, price, signal_type, features):
    """Sinyali ve o anki özellikleri veritabanına kaydeder."""
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    # JSON features
    feat_json = json.dumps(features)
    c.execute("INSERT INTO signals (symbol, exchange, time_at_signal, price_at_signal, signal_type, features) VALUES (?, ?, ?, ?, ?, ?)",
              (symbol, exchange, now, price, signal_type, feat_json))
    conn.commit()
    conn.close()

def get_unlabeled_signals(days_ago=5):
    """Etiketlenmemiş ve üzerinden en az 'days_ago' geçmiş sinyalleri getirir."""
    conn = sqlite3.connect(DB_PATH)
    threshold = (datetime.now() - timedelta(days=days_ago)).isoformat()
    df = pd.read_sql_query("SELECT * FROM signals WHERE is_labeled = 0 AND time_at_signal < ?", conn, params=(threshold,))
    conn.close()
    return df

def update_label(signal_id, outcome):
    """Sinyal sonucunu (örn: % getiri) günceller ve etiketlendi olarak işaretler."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("UPDATE signals SET outcome = ?, is_labeled = 1, label_time = ? WHERE id = ?", (outcome, now, signal_id))
    conn.commit()
    conn.close()

def get_training_data():
    """Tüm etiketli verileri eğitim için çeker."""
    import json
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM signals WHERE is_labeled = 1", conn)
    conn.close()
    
    if df.empty:
        return pd.DataFrame()
        
    # JSON'dan features sözlüğünü çıkarıp sütunlara çevir
    features_list = []
    for f in df['features']:
        features_list.append(json.loads(f))
    
    feat_df = pd.DataFrame(features_list)
    # Hedef Değişken: Outcome > 3.5% (Success = 1)
    feat_df['target'] = (df['outcome'] > 3.5).astype(int)
    return feat_df

if __name__ == "__main__":
    init_db()
    print("✅ Signals DB Başlatıldı.")
