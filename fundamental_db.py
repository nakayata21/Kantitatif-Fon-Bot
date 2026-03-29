import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta

DB_PATH = "fundamental_data.db"

def init_fund_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS fundamental_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT UNIQUE,
                    market TEXT,
                    pe_ratio REAL,
                    pb_ratio REAL,
                    piotroski_score INTEGER,
                    fundamental_score INTEGER,
                    fundamental_grade TEXT,
                    earnings_growth REAL,
                    debt_growth REAL,
                    takas_metrics TEXT,
                    last_updated TEXT
                )''')
    # Kolon ekleme (Migration)
    cols = ["takas_metrics"]
    for col in cols:
        try:
            c.execute(f"ALTER TABLE fundamental_metrics ADD COLUMN {col} TEXT")
        except: pass
    conn.commit()
    conn.close()

def save_fundamental_data(symbol, market, data):
    """Veriyi veritabanına kaydeder veya günceller."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    
    import json
    tk_json = json.dumps(data.get("takas_metrics", {})) if data.get("takas_metrics") else None

    c.execute('''INSERT OR REPLACE INTO fundamental_metrics 
                 (symbol, market, pe_ratio, pb_ratio, piotroski_score, fundamental_score, 
                  fundamental_grade, earnings_growth, debt_growth, takas_metrics, last_updated)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (symbol, market, 
               data.get("pe_ratio"), data.get("pb_ratio"), 
               data.get("piotroski_score"), data.get("isy_score", data.get("fundamental_score", 0)),
               data.get("isy_grade", data.get("fundamental_grade", "-")), 
               data.get("earnings_growth"), data.get("debt_growth"),
               tk_json,
               now))
    conn.commit()
    conn.close()

def get_fundamental_data(symbol):
    """Veritabanından hisseye ait veriyi çeker."""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM fundamental_metrics WHERE symbol = ?"
    df = pd.read_sql_query(query, conn, params=(symbol,))
    conn.close()
    
    if not df.empty:
        return df.iloc[0].to_dict()
    return None

if __name__ == "__main__":
    init_fund_db()
    print("✅ Temel Veri Deposu Başlatıldı.")
