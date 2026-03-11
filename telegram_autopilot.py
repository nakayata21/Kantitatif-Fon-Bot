import time
import requests
import json
from datetime import datetime
import os
import threading

# Ana modelden gerekli verileri al
from streamlit_app import run_scan, DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER

TOKEN = "8336526803:AAFDV687CJzXz7J692hagcx4CiCKFoZm8f8"
ALLOWED_CHAT_IDS = ["1070470722"]
DATA_FILE = "latest_scan_results.json"

def send_msg(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, data=payload, timeout=5)

def send_menu(chat_id):
    menu_text = "👋 *Merhaba Selman! Ben VIP Asistanın TradeFatBot.*\n\nLütfen yapmak istediğiniz işlemi seçin:"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "💾 Son BIST Kaydı", "callback_data": "cmd_bist"}, 
                {"text": "💾 Son NASDAQ Kaydı", "callback_data": "cmd_nasdaq"}
            ],
            [
                {"text": "🔥 BIST'i Canlı Tara", "callback_data": "cmd_tara_bist"}, 
                {"text": "🔥 NASDAQ'ı Canlı Tara", "callback_data": "cmd_tara_nasdaq"}
            ]
        ]
    }
    send_msg(chat_id, menu_text, reply_markup=keyboard)

def format_telegram_message(market, df_res):
    if df_res.empty: return f"❌ {market} piyasasında AL sinyali bulunamadı."
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    if buy_signals.empty: return f"❌ {market} piyasasında AL sinyali bulunamadı."
    
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
    msg = f"🚀 *{market} {datetime.now().strftime('%H:%M')} OTOMATİK TARAMA*\n\n"
    for idx, row in top_buys.iterrows():
        ai_tahmin = row.get('AI Tahmin', '-')
        msg += f"📌 *{row['Hisse']}*\n"
        msg += f"   ➤ Kalite: *{row['Kalite']}*\n"
        msg += f"   ➤ Aksiyon: {row['Aksiyon']}\n"
        msg += f"   ➤ R/R Oranı: {row['R/R']}\n"
        msg += f"   ➤ AI Tahmin: {ai_tahmin}\n\n"
    return msg

def perform_scan(market):
    print(f"[{datetime.now()}] {market} Taraması Başladı...")
    symbols = DEFAULT_BIST_HISSELER if market == "BIST" else DEFAULT_NASDAQ_HISSELER
    
    # gui=False parametresiyle ana dosyamızdaki tarayıcıyı arkaplanda sessiz sedasız çalıştırırız
    df, errs = run_scan(symbols, market, "Gunluk", delay_ms=500, workers=5, gui=False)
    
    msg = format_telegram_message(market, df)
    
    # Hafızaya (JSON) Kaydet
    data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
        except:
            data = {}
            
    data[market] = msg
    data[market + "_time"] = str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)
        
    for cid in ALLOWED_CHAT_IDS:
        send_msg(cid, msg)
    print(f"[{datetime.now()}] {market} Taraması Bitti ve Gönderildi.")

def schedule_loop():
    """Belirli saatler gelince otomatik tarama yapan döngü"""
    while True:
        now = datetime.now()
        # Saat 17:30'da BIST, Kapanış öncesi son durum
        if now.hour == 17 and now.minute == 30:
            perform_scan("BIST")
            time.sleep(60) # Aynı dakikada 2 kez basmasın diye 1 dk uyutur
            
        # Saat 17:45'te NASDAQ (ABD Piyasa açılışı sonrası ilk net sinyaller)
        if now.hour == 17 and now.minute == 45:
            perform_scan("NASDAQ")
            time.sleep(60)
            
        time.sleep(30)

def polling_loop():
    """Sürekli Telegram'daki mesajları dinleyen Asistan yapı"""
    last_update_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id}&timeout=30"
            r = requests.get(url, timeout=40)
            if r.ok:
                data = r.json()
                for item in data.get("result", []):
                    last_update_id = item["update_id"] + 1
                    
                    # Buton tıklaması geldiyse (Callback Query)
                    if "callback_query" in item:
                        cq = item["callback_query"]
                        chat_id = str(cq.get("message", {}).get("chat", {}).get("id", ""))
                        callback_data = cq.get("data", "")
                        
                        if chat_id not in ALLOWED_CHAT_IDS:
                            continue
                            
                        # Butondaki "Yükleniyor..." saatini durdurmak için Telegram'a geri dönüş yap
                        try:
                            requests.get(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery?callback_query_id={cq['id']}")
                        except:
                            pass
                        
                        if callback_data == "cmd_bist" or callback_data == "cmd_nasdaq":
                            market = callback_data.replace("cmd_", "").upper()
                            if not os.path.exists(DATA_FILE):
                                send_msg(chat_id, f"⚠️ *{market}* için henüz (bugüne ait) kaydedilmiş bir tarama sonucu yok.")
                                continue
                            with open(DATA_FILE, "r") as f:
                                saved = json.load(f)
                            
                            ans = saved.get(market, f"❌ *{market}* için önbellekte henüz sonuç yok.")
                            ans_time = saved.get(market + "_time", "")
                            if ans_time: ans += f"\n_Son Güncelleme: {ans_time}_"
                            send_msg(chat_id, ans)
                            
                        elif callback_data == "cmd_tara_bist":
                            send_msg(chat_id, "⏳ *BIST* taraması sizin emrinizle arka planda başlatılıyor (1-2 dk sürebilir)...")
                            threading.Thread(target=perform_scan, args=("BIST",), daemon=True).start()
                            
                        elif callback_data == "cmd_tara_nasdaq":
                            send_msg(chat_id, "⏳ *NASDAQ* taraması anlık olarak başlatılıyor...")
                            threading.Thread(target=perform_scan, args=("NASDAQ",), daemon=True).start()

                    # Normal mesaj veya komut geldiyse
                    elif "message" in item:
                        msg = item["message"]
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        
                        if chat_id not in ALLOWED_CHAT_IDS:
                            continue
                            
                        # Yazılan ne olursa olsun direkt Butonlu Menüyü çıkart
                        send_menu(chat_id)
                        
        except Exception as e:
            time.sleep(5)

if __name__ == '__main__':
    print("🤖 VIP Telegram Autopilot Robotu Başlatıldı ve Dinlemede!")
    t1 = threading.Thread(target=schedule_loop, daemon=True)
    t2 = threading.Thread(target=polling_loop, daemon=True)
    
    t1.start()
    t2.start()
    
    while True:
        time.sleep(1)
