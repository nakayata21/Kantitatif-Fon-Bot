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
                    label_type TEXT,
                    max_price REAL,
                    min_price REAL,
                    is_labeled INTEGER DEFAULT 0,
                    label_time TEXT
                )''')
    # Eski tabloya yeni kolonlari ekle (zaten varsa hata vermez)
    for col, coltype in [("label_type", "TEXT"), ("max_price", "REAL"), ("min_price", "REAL")]:
        try:
            c.execute(f"ALTER TABLE signals ADD COLUMN {col} {coltype}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def log_signal(symbol, exchange, price, signal_type, features, market_context=None, signal_time=None):
    """Sinyali, o anki teknik özellikleri ve piyasa bağlamını veritabanına kaydeder."""
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Eğer signal_time verilmediyse güncel zamanı kullan
    if not signal_time:
        now = datetime.now().isoformat()
    else:
        now = signal_time if isinstance(signal_time, str) else signal_time.isoformat()
        
    if market_context:
        features.update(market_context)
    
    feat_json = json.dumps(features)
    c.execute(
        "INSERT INTO signals (symbol, exchange, time_at_signal, price_at_signal, signal_type, features) VALUES (?, ?, ?, ?, ?, ?)",
        (symbol, exchange, now, price, signal_type, feat_json)
    )
    conn.commit()
    conn.close()

def get_unlabeled_signals(days_ago=5):
    """Etiketlenmemis ve uzerinden en az 'days_ago' gecmis sinyalleri getirir."""
    conn = sqlite3.connect(DB_PATH)
    threshold = (datetime.now() - timedelta(days=days_ago)).isoformat()
    df = pd.read_sql_query(
        "SELECT * FROM signals WHERE is_labeled = 0 AND time_at_signal < ?",
        conn, params=(threshold,)
    )
    conn.close()
    return df

def update_label(signal_id, outcome, label_type="TIME", max_price=None, min_price=None):
    """
    Sinyal sonucunu gunceller.
    label_type:
      'TP'   -> Take Profit hedefine ulasti  (Basarili)
      'SL'   -> Stop Loss'a degdi            (Basarisiz)
      'TIME' -> Sure doldu, getiriye gore karar verilir
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute(
        "UPDATE signals SET outcome=?, is_labeled=1, label_time=?, label_type=?, max_price=?, min_price=? WHERE id=?",
        (outcome, now, label_type, max_price, min_price, signal_id)
    )
    conn.commit()
    conn.close()

def get_training_data():
    """Tum etiketli verileri egitim icin hazirlar. Seasonality ozellikleri ekler."""
    import json
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM signals WHERE is_labeled = 1", conn)
    conn.close()

    if df.empty:
        return pd.DataFrame()

    # JSON features'i sutunlara cevir
    features_list = [json.loads(f) for f in df['features']]
    feat_df = pd.DataFrame(features_list)

    # --- SEASONALITY OZELLIKLERI ---
    signal_times = pd.to_datetime(df['time_at_signal'])
    feat_df['day_of_week']   = signal_times.dt.dayofweek                          # 0=Pzt, 4=Cum
    feat_df['day_of_month']  = signal_times.dt.day                                # 1-31
    feat_df['week_of_year']  = signal_times.dt.isocalendar().week.astype(int)     # 1-53
    feat_df['month']         = signal_times.dt.month                              # 1-12
    feat_df['hour_of_day']   = signal_times.dt.hour                               # 0-23
    feat_df['is_month_start'] = signal_times.dt.is_month_start.astype(int)
    feat_df['is_month_end']   = signal_times.dt.is_month_end.astype(int)

    # --- TRIPLE BARRIER ETIKETI ---
    # TP -> her zaman basarili
    # SL -> her zaman basarisiz
    # TIME -> outcome > 3.5% ise basarili
    if 'label_type' in df.columns:
        label_types = df['label_type'].fillna('TIME').values
        outcomes    = df['outcome'].fillna(0).values
        targets = []
        for lt, oc in zip(label_types, outcomes):
            if lt == 'TP':
                targets.append(1)
            elif lt == 'SL':
                targets.append(0)
            else:  # TIME
                targets.append(1 if oc > 3.5 else 0)
        feat_df['target'] = targets
    else:
        feat_df['target'] = (df['outcome'] > 3.5).astype(int)

    # Sadece sayisal sutunlari tut, eksik degerleri dusur
    feat_df = feat_df.select_dtypes(include='number')
    feat_df = feat_df.dropna()

    return feat_df

if __name__ == "__main__":
    init_db()
    print("✅ Signals DB Baslatildi.")
