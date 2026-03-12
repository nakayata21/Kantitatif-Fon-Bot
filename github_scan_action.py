import os
from streamlit_app import run_scan, DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER
import requests
from datetime import datetime
import pytz

# GMT+3 (Türkiye) saati için timezone ayarı
TR_TZ = pytz.timezone("Europe/Istanbul")

# GitHub Secrets'ten okuyacağız, veya varsayılanları kullanacağız.
# Güvenlik uyarısı: Hardcoded tokenlar kaldırıldı. GitHub Secrets üzerinden yönetilmelidir.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MARKET = os.environ.get("TARGET_MARKET", "BIST")

def get_market_status(market="BIST"):
    """Piyasa durumunu kontrol eder: OPEN, PRE_MARKET, CLOSED"""
    now_tr = datetime.now(TR_TZ)
    day = now_tr.weekday()  # 0=Pazartesi, 6=Pazar
    
    # Hafta sonu tüm piyasalar kapalı
    if day >= 5:
        return "CLOSED"
    
    current_time_float = now_tr.hour + now_tr.minute / 60.0
    
    if market == "BIST":
        # 10:00 - 18:15 arası BIST Açık
        if 10.0 <= current_time_float <= 18.25:
            return "OPEN"
        # 09:15 - 10:00 arası AÇILIŞ ÖNCESİ
        if 9.25 <= current_time_float < 10.0:
            return "PRE_MARKET"
    else: 
        # NASDAQ (TR Saatiyle 16:30 - 23:00)
        if 16.5 <= current_time_float <= 23.0:
            return "OPEN"
        # 16:00 - 16:30 ÖN HAZIRLIK
        if 16.0 <= current_time_float < 16.5:
            return "PRE_MARKET"
            
    return "CLOSED"

def send_msg(text):
    print(f"DEBUG: Mesaj gonderiliyor... Token uzunlugu: {len(TOKEN) if TOKEN else 0}, Chat ID: {CHAT_ID}")
    if not TOKEN or ":" not in TOKEN:
        print("❌ HATA: Telegram Token gecersiz veya eksik!")
        return
    if not CHAT_ID:
        print("❌ HATA: Telegram Chat ID eksik!")
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    print(f"DEBUG: Gonderilen mesajın ilk 100 karakteri: {text[:100]}...")
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code != 200:
            print(f"❌ Telegram Hatası: {response.status_code} - {response.text}")
        else:
            print(f"✅ Mesaj başarıyla gönderildi ({CHAT_ID})")
    except Exception as e:
        print(f"❌ Telegram Bağlantı Hatası: {str(e)}")

def format_telegram_message(market, df_res, status):
    if df_res.empty: return f"❌ {market} piyasasında AL sinyali bulunamadı."
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    if buy_signals.empty: return f"❌ {market} piyasasında AL sinyali bulunamadı."
    
    # En iyi 5
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
    
    status_text = "🟢 Piyasa Açık (Canlı)" if status == "OPEN" else "🕒 Piyasa Açılmak Üzere (Ön Hazırlık)"
    
    msg = f"🚀 *{market} OTOMATİK TARAMA RAPORU*\n"
    msg += f"🗓 Tarih: {datetime.now(TR_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += f"⏱ Durum: {status_text}\n\n"
    
    for idx, row in top_buys.iterrows():
        ai_tahmin = row.get('AI Tahmin', '-')
        ozel_durum = row.get('Özel Durum', '-')
        squeeze = row.get('Daralma (Squeeze)', '-')
        bollinger = row.get('Bollinger', '-')
        vol_spike = row.get('Hacim Spike', 0.0)
        dip_skor = row.get('Dip Skor', 0.0)
        
        # Dipten Hacim Patlaması Durumu
        vol_info = f"📊 Hacim: x{vol_spike}"
        if vol_spike >= 2.0 and dip_skor >= 70:
            vol_info = f"🔥 *DİPTEN HACIM PATLAMASI (x{vol_spike})*"
        elif vol_spike >= 2.0:
            vol_info = f"💥 Hacim Patlaması (x{vol_spike})"

        msg += f"📌 *{row['Hisse']}*\n"
        msg += f"   ➤ Kalite: *{row['Kalite']}* | AI: *{ai_tahmin}*\n"
        msg += f"   ➤ Aksiyon: {row['Aksiyon']}\n"
        msg += f"   ➤ {vol_info}\n"
        
        teknik = []
        if ozel_durum != "-": teknik.append(ozel_durum)
        if squeeze != "-": teknik.append(squeeze)
        if bollinger != "-": teknik.append(bollinger)
        
        if teknik:
            msg += f"   ➤ Sinyal: {' | '.join(teknik)}\n"
        
        msg += f"   ➤ R/R Oranı: {row['R/R']}\n\n"
    return msg

if __name__ == "__main__":
    status = get_market_status(MARKET)
    
    if status == "CLOSED":
        # TEST İÇİN: Eğer manuel tetiklendiyse kapalı olsa bile çalıştır (veya isterseniz bu bloğu silebiliriz)
        print(f"[{datetime.now(TR_TZ)}] Piyasa kapalı ({MARKET}), tarama atlanıyor.")
        # if os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch': # Manuel başlattıysanız burayı açabilirim
    else:
        print(f"[{datetime.now(TR_TZ)}] Durum: {status}. {MARKET} taraması başlatılıyor...")
        symbols = DEFAULT_BIST_HISSELER if MARKET == "BIST" else DEFAULT_NASDAQ_HISSELER
        
        try:
            df, errs = run_scan(symbols, MARKET, "Gunluk", delay_ms=500, workers=5, gui=False)
            message = format_telegram_message(MARKET, df, status)
            send_msg(message)
            print(f"[{datetime.now(TR_TZ)}] İşlem Başarıyla Tamamlandı. Mesaj Gönderildi!")
            # Arka plandaki WebSocket vb. süreçleri kesin olarak sonlandırmak için:
            os._exit(0)
        except Exception as e:
            error_msg = f"🔴 GİTHUB ACTION TARAMA HATASI ({MARKET}): {str(e)}"
            print(error_msg)
            send_msg(error_msg)
            os._exit(1)
