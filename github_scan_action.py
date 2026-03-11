import os
from streamlit_app import run_scan, DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER
import requests
from datetime import datetime
import pytz

# GMT+3 (Türkiye) saati için timezone ayarı
TR_TZ = pytz.timezone("Europe/Istanbul")

# GitHub Secrets'ten okuyacağız, veya varsayılanları kullanacağız.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8336526803:AAFDV687CJzXz7J692hagcx4CiCKFoZm8f8")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8336526803")
MARKET = os.environ.get("TARGET_MARKET", "BIST") # Varsayılan BIST

def is_market_open():
    """BIST çalışma saatlerini kontrol eder (Hafta içi 10:00 - 18:15)"""
    now_tr = datetime.now(TR_TZ)
    day = now_tr.weekday()  # 0=Monday, 6=Sunday
    hour = now_tr.hour
    minute = now_tr.minute
    
    # Cumartesi(5) ve Pazar(6) kapalı
    if day >= 5:
        return False
    
    # 10:00'dan önce veya 18:15'ten sonra kapalı
    current_time_float = hour + minute / 60.0
    if current_time_float < 10.0 or current_time_float > 18.25:
        return False
        
    return True

def send_msg(text):
    if not TOKEN or not CHAT_ID:
        print("Telegram Ayarları Bulunamadı (Secrets Eksik)!")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=payload, timeout=5)

def format_telegram_message(market, df_res):
    if df_res.empty: return f"❌ {market} piyasasında AL sinyali bulunamadı."
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    if buy_signals.empty: return f"❌ {market} piyasasında AL sinyali bulunamadı."
    
    # En iyi 5 (veya bulabildiği kadar)
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
    msg = f"🚀 *{market} OTOMATİK TARAMA RAPORU*\n"
    msg += f"🗓 Tarih: {datetime.now(TR_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += f"⏱ Durum: Piyasa Açık (Canlı Veri)\n\n"
    
    for idx, row in top_buys.iterrows():
        ai_tahmin = row.get('AI Tahmin', '-')
        ozel_durum = row.get('Özel Durum', '-')
        squeeze = row.get('Daralma (Squeeze)', '-')
        bollinger = row.get('Bollinger', '-')
        
        msg += f"📌 *{row['Hisse']}*\n"
        msg += f"   ➤ Kalite: *{row['Kalite']}* | AI: *{ai_tahmin}*\n"
        msg += f"   ➤ Aksiyon: {row['Aksiyon']}\n"
        
        # Ekstra Teknik Detaylar
        teknik = []
        if ozel_durum != "-": teknik.append(ozel_durum)
        if squeeze != "-": teknik.append(squeeze)
        if bollinger != "-": teknik.append(bollinger)
        
        if teknik:
            msg += f"   ➤ Sinyal: {' | '.join(teknik)}\n"
        
        msg += f"   ➤ R/R Oranı: {row['R/R']}\n\n"
    return msg

if __name__ == "__main__":
    if not is_market_open():
        print(f"[{datetime.now(TR_TZ)}] Piyasa kapalı olduğu için tarama atlanıyor.")
        # Sadece sessizce log basıyoruz, Telegram'a mesaj atmıyoruz.
    else:
        print(f"[{datetime.now(TR_TZ)}] Piyasa AÇIK. {MARKET} taraması başlatılıyor...")
        symbols = DEFAULT_BIST_HISSELER if MARKET == "BIST" else DEFAULT_NASDAQ_HISSELER
        
        try:
            df, errs = run_scan(symbols, MARKET, "Gunluk", delay_ms=500, workers=5, gui=False)
            message = format_telegram_message(MARKET, df)
            send_msg(message)
            print(f"[{datetime.now(TR_TZ)}] İşlem Başarıyla Tamamlandı. Mesaj Gönderildi!")
        except Exception as e:
            error_msg = f"🔴 GİTHUB ACTION TARAMA HATASI ({MARKET}): {str(e)}"
            print(error_msg)
            send_msg(error_msg)
