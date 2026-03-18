
import sqlite3
import pandas as pd
from datetime import datetime
import os

DB_NAME = "trade_history.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            hisse TEXT,
            market TEXT,
            timeframe TEXT,
            kalite REAL,
            skor REAL,
            elite_skor REAL,
            risk_skor REAL,
            sinyal TEXT,
            aksiyon TEXT,
            ozel_durum TEXT,
            ai_tahmin TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_scan_results(df: pd.DataFrame, market: str, timeframe: str):
    if df.empty:
        return
    
    init_db()
    conn = sqlite3.connect(DB_NAME)
    
    # Mevcut zaman dilimi
    now = datetime.now()
    
    # DataFrame'i veritabanı formatına hazırla
    save_df = df.copy()
    save_df['timestamp'] = now
    save_df['market'] = market
    save_df['timeframe'] = timeframe
    
    # Sadece gerekli sütunları al (veritabanında olanları)
    cols_to_save = [
        'timestamp', 'Hisse', 'market', 'timeframe', 'Kalite', 'Skor', 
        'Elite Skor', 'Dusus Riski', 'Sinyal', 'Aksiyon', 'Özel Durum', 'AI Tahmin'
    ]
    # Sütun isimlerini veritabanı ile eşleştir
    rename_dict = {
        'Hisse': 'hisse',
        'Kalite': 'kalite',
        'Skor': 'skor',
        'Elite Skor': 'elite_skor',
        'Dusus Riski': 'risk_skor',
        'Sinyal': 'sinyal',
        'Aksiyon': 'aksiyon',
        'Özel Durum': 'ozel_durum',
        'AI Tahmin': 'ai_tahmin'
    }
    
    present_cols = [c for c in cols_to_save if c in save_df.columns]
    final_df = save_df[present_cols].rename(columns=rename_dict)
    
    final_df.to_sql('scan_results', conn, if_exists='append', index=False)
    conn.close()

def get_recent_signals(days=3):
    conn = sqlite3.connect(DB_NAME)
    query = f"""
        SELECT * FROM scan_results 
        WHERE timestamp >= date('now', '-{days} days')
        ORDER BY timestamp DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_new_elite_entries():
    """Son taramada Elite olup bir önceki taramada olmayanları bulur."""
    conn = sqlite3.connect(DB_NAME)
    
    # Son iki farklı zaman damgasını bul
    c = conn.cursor()
    c.execute("SELECT DISTINCT timestamp FROM scan_results ORDER BY timestamp DESC LIMIT 2")
    times = c.fetchall()
    
    if len(times) < 2:
        conn.close()
        return pd.DataFrame()
    
    latest_time = times[0][0]
    prev_time = times[1][0]
    
    query = f"""
        SELECT * FROM scan_results WHERE timestamp = '{latest_time}' AND elite_skor >= 75
        AND hisse NOT IN (
            SELECT hisse FROM scan_results WHERE timestamp = '{prev_time}' AND elite_skor >= 75
        )
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df
