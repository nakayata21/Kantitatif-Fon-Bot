import os
from streamlit_app import run_scan, DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER
import requests
from datetime import datetime

# GitHub Secrets'ten okuyacağız, eğer yoksa sistem çöksün ki hatayı anlayalım.
# GitHub Secrets'ten okuyacağız, veya varsayılanları kullanacağız.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8336526803:AAFDV687CJzXz7J692hagcx4CiCKFoZm8f8")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8336526803")
MARKET = os.environ.get("TARGET_MARKET", "BIST") # Varsayılan BIST

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
    msg = f"🚀 *{market} GÜN SONU OTOMATİK TARAMA*\n"
    msg += f"🗓 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)\n\n"
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
    print(f"[{datetime.now()}] GitHub Actions üzerinden {MARKET} taraması başlatılıyor...")
    symbols = DEFAULT_BIST_HISSELER if MARKET == "BIST" else DEFAULT_NASDAQ_HISSELER
    
    # Render UI olmadığından gui=False
    try:
        df, errs = run_scan(symbols, MARKET, "Gunluk", delay_ms=500, workers=5, gui=False)
        message = format_telegram_message(MARKET, df)
        send_msg(message)
        print(f"[{datetime.now()}] İşlem Başarıyla Tamamlandı. Mesaj Gönderildi!")
    except Exception as e:
        error_msg = f"🔴 GİTHUB ACTION TARAMA HATASI ({MARKET}): {str(e)}"
        print(error_msg)
        send_msg(error_msg)
