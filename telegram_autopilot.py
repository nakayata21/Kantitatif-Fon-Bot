import time
import requests
import json
from datetime import datetime
import os
import threading

# Ana modelden gerekli verileri al
from streamlit_app import run_scan
from constants import DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER, DEFAULT_CRYPTO_SYMBOLS, TIMEFRAME_OPTIONS
from indicators import add_indicators, calculate_price_targets
from scoring import score_symbol
from data_fetcher import fetch_hist, interval_obj
from utils import _safe_get

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8336526803:AAEvg9b0P9Em5MSND9uCb9RfbTGXBHDGdAA")
# Birden fazla chat_id destekle (Hem kendi hesabın hem de kanalın)
ALLOWED_CHAT_IDS = ["1070470722", "-1003824371023"]
DATA_FILE = "latest_scan_results.json"

# GitHub Action Tetikleme Ayarları
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") # Manuel tetikleme için GITHUB_TOKEN (Personal Access Token) gerekli
REPO_OWNER = "nakayata21"
REPO_NAME = "Kantitatif-Fon-Bot"
WORKFLOW_ID = "daily_screener.yml" 

def send_msg(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    # Önce Markdown ile dene, hata alırsa düz metne dön (alt tire vb. karakterler Markdown'ı bozabiliyor)
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        r = requests.post(url, data=payload, timeout=12)
        if r.status_code != 200:
            print(f"⚠️ Telegram Mesaj Hatası ({chat_id}): {r.status_code} - {r.text}")
            # Düz metin olarak tekrar dene
            payload["parse_mode"] = ""
            requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"❌ Mesaj Gönderilemedi ({chat_id}): {e}")

def sync_from_cloud(filename):
    """GitHub üzerindeki en güncel dosyayı bulut üzerinden indirir ve yereli günceller."""
    raw_url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/{filename}"
    try:
        response = requests.get(raw_url, timeout=10)
        if response.status_code == 200:
            with open(filename, "wb") as f:
                f.write(response.content)
            # print(f"✅ Bulut Senkronizasyonu Başarılı: {filename}")
            return True
    except:
        pass
    return False

def send_doc(chat_id, file_path, caption=""):
    """Telegram üzerinden dosya (CSV/Excel) gönderir. Önce buluttan günceller."""
    sync_from_cloud(file_path) # Önce GitHub'daki en güncel dosyayı çek
    if not os.path.exists(file_path): return
    url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
            requests.post(url, data=data, files=files, timeout=20)
    except Exception as e:
        print(f"Dosya Gönderim Hatası: {e}")

def set_bot_commands():
    """Telegram sol alt menü butonuna (Bot Commands) komutları ekler."""
    url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"
    commands = [
        {"command": "menu", "description": "Ana Menüyü Göster"},
        {"command": "bist", "description": "Son BIST Taramasını Getir"},
        {"command": "nasdaq", "description": "Son NASDAQ Taramasını Getir"},
        {"command": "crypto", "description": "Son CRYPTO Taramasını Getir"},
        {"command": "tara_bist", "description": "Canlı BIST Taraması Başlat"},
        {"command": "tara_crypto", "description": "Canlı CRYPTO Taraması Başlat"},
        {"command": "analiz", "description": "Tek hisse analizi (ör: /analiz THYAO)"},
        {"command": "github", "description": "GitHub Bulut Taraması Tetikle"}
    ]
    try:
        requests.post(url, json={"commands": commands}, timeout=10)
        print("✅ Telegram Menü Komutları Tanımlandı.")
    except Exception as e:
        print(f"❌ Menü Komutları Tanımlanamadı: {e}")

def send_menu(chat_id):
    menu_text = """👋 *Merhaba! Ben VIP Asistanın TradeFatBot.*

📝 *Kullanım:*
• Bir hisse adı yazın → Detaylı analiz gelir
  Örnek: `THYAO`, `AAPL`, `ASELS`

• Veya aşağıdaki butonları kullanın:"""
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "💾 BIST Sonuçları", "callback_data": "cmd_bist"}, 
                {"text": "💾 NASDAQ Sonuçları", "callback_data": "cmd_nasdaq"},
                {"text": "💾 CRYPTO Sonuçları", "callback_data": "cmd_crypto"}
            ],
            [
                {"text": "🔥 BIST Tara", "callback_data": "cmd_tara_bist"}, 
                {"text": "🔥 NASDAQ Tara", "callback_data": "cmd_tara_nasdaq"},
                {"text": "🔥 CRYPTO Tara", "callback_data": "cmd_tara_crypto"}
            ],
            [
                {"text": "📂 BIST Tam Liste", "callback_data": "dl_bist"},
                {"text": "📂 NASDAQ Tam Liste", "callback_data": "dl_nasdaq"},
                {"text": "📂 CRYPTO Tam Liste", "callback_data": "dl_crypto"}
            ],
            [
                {"text": "🚀 GitHub Taramasını Başlat", "callback_data": "cmd_github_action"}
            ]
        ]
    }
    send_msg(chat_id, menu_text, reply_markup=keyboard)


def trigger_github_action(chat_id):
    """GitHub Action workflow'unu manuel tetikler."""
    if not GITHUB_TOKEN:
        send_msg(chat_id, "❌ *GITHUB_TOKEN* bulunamadı. Lütfen çevre değişkenlerine ekleyin.")
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendChatAction"
    requests.post(url, data={"chat_id": chat_id, "action": "typing"})
    
    dispatch_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_ID}/dispatches"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"ref": "main"} # veya workflow'un bulunduğu branch
    
    try:
        response = requests.post(dispatch_url, headers=headers, json=payload, timeout=10)
        if response.status_code == 204:
            send_msg(chat_id, "🚀 *GitHub Action başarıyla tetiklendi!* Tarama sonuçları birazdan Telegram'a düşecektir.")
        else:
            send_msg(chat_id, f"❌ *GitHub Hatası:* {response.status_code}\n{response.text}")
    except Exception as e:
        send_msg(chat_id, f"❌ *Bağlantı Hatası:* {str(e)}")


def analyze_single_stock(chat_id, symbol):
    """Tek bir hisseyi tarayıp detaylı analiz gönderir."""
    symbol = symbol.upper().strip()
    
    # Piyasayı belirle
    if symbol in DEFAULT_BIST_HISSELER:
        market = "BIST"
    elif symbol in DEFAULT_NASDAQ_HISSELER:
        market = "NASDAQ"
    elif symbol in DEFAULT_CRYPTO_SYMBOLS:
        market = "CRYPTO"
    else:
        market = "BIST"  # Varsayılan
    
    send_msg(chat_id, f"🔍 *{symbol}* analiz ediliyor... (10-20 sn)")
    
    try:
        from tvDatafeed import TvDatafeed
        tv = TvDatafeed()
        tf = TIMEFRAME_OPTIONS["Gunluk"]
        
        tv_exchange = "BINANCE" if market == "CRYPTO" else market
        
        base_raw = fetch_hist(tv, symbol, tv_exchange, interval_obj(tf["base"]), tf["bars"], retries=3)
        conf_raw = fetch_hist(tv, symbol, tv_exchange, interval_obj(tf["confirm"]), tf["confirm_bars"], retries=3)
        
        if base_raw is None or base_raw.empty:
            send_msg(chat_id, f"❌ *{symbol}* için veri bulunamadı. Sembol adını kontrol edin.")
            return
        
        base = add_indicators(base_raw)
        conf = add_indicators(conf_raw)
        
        vb = base.dropna(subset=["close", "ema20", "ema50", "sma20", "rsi", "macd_hist", "atr", "atr_pct", "adx"])
        vc = conf.dropna(subset=["close", "ema20", "ema50", "macd_hist"])
        
        if vb.empty or vc.empty:
            send_msg(chat_id, f"❌ *{symbol}* için yeterli veri bulunamadı.")
            return
        
        last = vb.iloc[-1]
        prev = vb.iloc[-2] if len(vb) > 1 else last
        conf_last = vc.iloc[-1]
        
        # Skorlama
        s = score_symbol(last, prev, conf_last, market)
        
        # Hedef Fiyatlar
        targets = calculate_price_targets(vb)
        
        # Mesajı oluştur
        close = round(float(last["close"]), 2)
        rsi = round(float(last["rsi"]), 1)
        adx = round(float(last["adx"]), 1)
        atr_pct = round(float(last["atr_pct"]), 2)
        vol_spike = round(float(_safe_get(last, "vol_spike", 0.0)), 2)
        macd = round(float(last["macd_hist"]), 4)
        
        msg = f"📊 *{symbol} ({market}) DETAYLI ANALİZ*\n"
        msg += f"{'─' * 30}\n\n"
        
        # Fiyat Bilgisi
        msg += f"💰 *Fiyat:* {close}\n"
        msg += f"📈 *Günlük Değişim:* {s.get('Günlük %', '-')}\n\n"
        
        # Sinyal
        sinyal_emoji = "🟢" if s['Sinyal'] == "AL" else ("🟡" if s['Sinyal'] == "BEKLE" else "🔴")
        msg += f"{sinyal_emoji} *Sinyal:* {s['Sinyal']}\n"
        msg += f"🎯 *Aksiyon:* {s['Aksiyon']}\n\n"
        
        # Skorlar
        msg += f"⭐ *SKORLAR:*\n"
        msg += f"   Kalite: *{s['Kalite']}* / 100\n"
        msg += f"   Trend: {s['Trend Skor']} | Momentum: {s['Momentum Skor']}\n"
        msg += f"   Dip: {s['Dip Skor']} | Breakout: {s['Breakout Skor']}\n"
        msg += f"   Smart Money: {s['Smart Money Skor']} ({s['Kurumsal Giriş']})\n"
        msg += f"   Risk: {s['Dusus Riski']} | Güven: {s['Guven']}\n\n"
        
        # Teknik Göstergeler
        msg += f"📉 *TEKNİK GÖSTERGELER:*\n"
        msg += f"   RSI: {rsi}"
        if rsi > 70: msg += " 🔴 (Aşırı Alım)"
        elif rsi < 30: msg += " 🟢 (Aşırı Satım)"
        else: msg += " ⚪ (Nötr)"
        msg += "\n"
        
        msg += f"   ADX: {adx}"
        if adx > 25: msg += " 💪 (Güçlü Trend)"
        elif adx < 15: msg += " 😴 (Trend Yok)"
        else: msg += " 📊 (Orta)"
        msg += "\n"
        
        msg += f"   MACD: {'🟢 Pozitif' if macd > 0 else '🔴 Negatif'} ({macd})\n"
        msg += f"   ATR%: {atr_pct} (Volatilite)\n"
        msg += f"   Hacim: x{vol_spike}"
        if vol_spike >= 2.5: msg += " 💥 PATLAMA"
        elif vol_spike >= 1.5: msg += " 📈 Artış"
        msg += "\n"
        msg += f"   UT Bot: {s['UT Bot']}\n"
        msg += f"   SMA200: {s['Kurumsal SMA200']}\n\n"
        
        # Özel Durumlar
        ozel = s.get('Özel Durum', '-')
        dip_sin = s.get('Dip Sinyalleri', '-')
        if ozel != "-":
            msg += f"⚡ *Özel Durum:* {ozel}\n"
        if dip_sin != "-":
            msg += f"🏊 *Dip Sinyalleri:* {dip_sin}\n"
        
        # Hedef Fiyatlar
        if targets:
            msg += f"\n🎯 *HEDEF FİYATLAR:*\n"
            msg += f"   1️⃣ Kısa Vade: {targets['Hedef 1']} (+%{targets['Hedef 1 %']})\n"
            msg += f"   2️⃣ Orta Vade: {targets['Hedef 2']} (+%{targets['Hedef 2 %']})\n"
            msg += f"   3️⃣ Uzun Vade: {targets['Hedef 3']} (+%{targets['Hedef 3 %']})\n"
            msg += f"   🛑 Stop Loss: {targets['Stop Loss']} ({targets['Stop %']}%)\n"
        
        msg += f"\n   R/R Oranı: {s['R/R']}\n"
        
        # AI Yorumu (OpenRouter - Gelişmiş Quant Analist Modu)
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                from openai import OpenAI
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key)
                
                # Tüm teknik ve AI verilerini birleştirerek LLM'e gönderiyoruz
                phys = s.get('Fizik Skor', 0.0)
                noise = s.get('Gürültü', 'ORTA')
                bayesian = s.get('Bayesian Prob', 0.5)
                
                ai_prompt = f"""
SEN BİR QUANT YATIRIM DANIŞMANISIN. Kullanıcıya şu hisseyi analiz et: {symbol} ({market})
TEKNİK VERİLER:
- Fiyat: {close}, Günlük Değişim: {s.get('Günlük %', '-')}
- Sinyal: {s['Sinyal']}, Karar: {s['Decision']}
- Kalite Skoru: {s['Kalite']}/100, Güven Seviyesi: {s['Guven']}
- Fizik Motoru Skoru: {phys} (Gürültü: {noise})
- Bayesian Başarı Olasılığı: %{bayesian*100:.1f}
- Özel Durumlar: {s.get('Özel Durum', '-')}

TALİMAT:
1. Teknik terimleri (RSI, MACD vb.) kullanma. 
2. Bu verileri birleştirip "Al, Sat veya Bekle" tavsiyeni NEDENLERİYLE birlikte 3-4 cümlede söyle.
3. Çok samimi, dürüst ve mahalle bakkalının bile anlayacağı bir dil kullan.
4. "Eğer fiyat {targets.get('Stop Loss', 'bilinmiyor')} altına inerse tehlike var" gibi somut bir uyarı ekle.
5. Bol emoji kullan."""

                response = client.chat.completions.create(
                    model="google/gemini-2.0-flash-exp:free", # Hızlı ve akıllı model
                    messages=[
                        {"role": "system", "content": "Sen borsa verilerini halkın diliyle anlatan, samimi ve dürüst bir Türk yatırım danışmanısın. Teknik detaylara boğulmadan doğrudan sonuca odaklanırsın."},
                        {"role": "user", "content": ai_prompt}
                    ],
                    max_tokens=600,
                    temperature=0.7,
                )
                ai_text = response.choices[0].message.content.strip()
                msg += f"\n🧠 *AI ANALİST YORUMU:*\n{ai_text}\n"
            except Exception as e:
                print(f"AI Analiz Hatası: {e}")
        
        send_msg(chat_id, msg)
        
    except Exception as e:
        send_msg(chat_id, f"❌ *{symbol}* analiz hatası: {str(e)[:200]}")


def format_telegram_message(market, df_res):
    if df_res.empty: return f"❌ {market} piyasasında fırsat bulunamadı."
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    if buy_signals.empty: return f"❌ {market} piyasasında onaylı işlem setup'ı oluşmadı."
    
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
    msg = f"🛰️ *{market} QUANT DECISION ENGINE* ({datetime.now().strftime('%H:%M')})\n\n"
    
    for idx, row in top_buys.iterrows():
        engine = row.get('Engine', 'SAFE')
        decision = row.get('Decision', 'NO TRADE')
        
        # Engine Label
        if engine == "OPPORTUNITY": 
            engine_str = "⚡ OPPORTUNITY ENGINE DETECTED"
        else:
            engine_str = "🛡️ SAFE ENGINE DETECTED"
            
        msg += f"{engine_str} | *{row['Hisse']}*\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🎯 *Decision:* {decision}\n"
        msg += f"📊 *Setup Puanı:* {row.get('Skor', 0)}/100 | *Trade Puanı:* {row.get('Kalite', 0)}/100\n"
        msg += f"🔥 *Setup Stratejisi:* {row.get('Aksiyon', '-')}\n\n"
        
        # Ek Metrikler
        msg += f"📈 *Gerekçe/Metrikler:*\n"
        vol_s = row.get('Hacim Spike', 0.0)
        msg += f"   ➤ Hacim Gücü: x{vol_s} {'🔥 Patlama' if vol_s >= 2 else ''}\n"
        msg += f"   ➤ Ozel Durumlar: {row.get('Özel Durum', '-')}\n"
        msg += f"   ➤ Likidite Eşiği: {row.get('Likidite', 'Geçti')}\n\n"
        
        # Trade Decision (Fiyatlar ve Risk) 
        msg += f"💼 *TRADE PLANI (R/R: 1:{row.get('R/R', 0)})*\n"
        msg += f"   ➤ Giriş: {row.get('Fiyat', 0)}\n"
        msg += f"   ➤ Stop Loss: {row.get('Stop Loss', 0)} (%{row.get('Stop %', 0)})\n"
        
        tp1, tp2, tp3 = row.get('Hedef 1', 0), row.get('Hedef 2', 0), row.get('Hedef 3', 0)
        if tp1 > 0:
            msg += f"   ➤ TP 1 (%50 Çıkış): {tp1} (+%{row.get('Hedef 1 %', 0)})\n"
            msg += f"   ➤ TP 2: {tp2} (+%{row.get('Hedef 2 %', 0)})\n"
            msg += f"   ➤ TP 3 (Runner): {tp3} (+%{row.get('Hedef 3 %', 0)})\n"
            
        msg += "\n"
        
    return msg


def perform_scan(market):
    print(f"[{datetime.now()}] {market} Taraması Başladı...")
    if market == "BIST": symbols = DEFAULT_BIST_HISSELER
    elif market == "NASDAQ": symbols = DEFAULT_NASDAQ_HISSELER
    else: symbols = DEFAULT_CRYPTO_SYMBOLS
    
    df, errs = run_scan(symbols, market, "Gunluk", delay_ms=500, workers=5, gui=False)
    
    # Tüm sonuçları CSV olarak kaydet
    full_csv_path = f"full_scan_{market}.csv"
    if not df.empty:
        df.to_csv(full_csv_path, index=False, encoding="utf-8-sig")
        print(f"✅ {market} Tüm Liste Kaydedildi: {full_csv_path}")

    msg = format_telegram_message(market, df)
    
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
        
        # Kullanıcı talebi: BIST taraması saat 23:00 dolaylarında olsun (Kapanış sonrası net veriler)
        if now.hour == 23 and now.minute == 0:
            perform_scan("BIST")
            time.sleep(60)
            
        if now.hour == 23 and now.minute == 30:
            perform_scan("NASDAQ")
            time.sleep(60)

        if now.hour == 23 and now.minute == 45:
            perform_scan("CRYPTO")
            time.sleep(60)
            
        time.sleep(30)


def polling_loop():
    """Sürekli Telegram'daki mesajları dinleyen Asistan yapı"""
    last_update_id = 0
    
    # Tüm hisseleri birleştir (hızlı arama için set)
    all_symbols = set(DEFAULT_BIST_HISSELER) | set(DEFAULT_NASDAQ_HISSELER)
    
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
                            # Opsiyonel: Admin menüsünde görünmesi için yeni bir chat_id tespit edildiğinde log bas
                            print(f"⚠️  Buton Tıklaması Reddedildi: {chat_id} (Whitelist'te yok)")
                            continue
                            
                        try:
                            requests.get(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery?callback_query_id={cq['id']}")
                        except:
                            pass
                        
                        if callback_data in ["cmd_bist", "cmd_nasdaq", "cmd_crypto"]:
                            market = callback_data.replace("cmd_", "").upper()
                            sync_from_cloud(DATA_FILE) # Önce GitHub'dan en güncel JSON'u çek
                            if not os.path.exists(DATA_FILE):
                                send_msg(chat_id, f"⚠️ *{market}* için henüz kaydedilmiş bir tarama sonucu yok.")
                                continue
                            with open(DATA_FILE, "r") as f:
                                saved = json.load(f)
                            
                            ans = saved.get(market, f"❌ *{market}* için önbellekte henüz sonuç yok.")
                            ans_time = saved.get(market + "_time", "")
                            if ans_time: ans += f"\n_Son Güncelleme: {ans_time}_"
                            send_msg(chat_id, ans)
                            
                        elif callback_data == "cmd_tara_bist":
                            send_msg(chat_id, "⏳ *BIST* taraması başlatılıyor (1-2 dk)...")
                            threading.Thread(target=perform_scan, args=("BIST",), daemon=True).start()
                            
                        elif callback_data == "cmd_tara_nasdaq":
                            send_msg(chat_id, "⏳ *NASDAQ* taraması başlatılıyor...")
                            threading.Thread(target=perform_scan, args=("NASDAQ",), daemon=True).start()
                            
                        elif callback_data == "cmd_tara_crypto":
                            send_msg(chat_id, "⏳ *CRYPTO* taraması başlatılıyor...")
                            threading.Thread(target=perform_scan, args=("CRYPTO",), daemon=True).start()
                            
                        elif callback_data == "cmd_github_action":
                            trigger_github_action(chat_id)
                        
                        elif callback_data.startswith("dl_"):
                            market = callback_data.replace("dl_", "").upper()
                            file_path = f"full_scan_{market}.csv"
                            if os.path.exists(file_path):
                                send_doc(chat_id, file_path, f"📊 *{market}* piyasasının son tam tarama sonuçları.")
                            else:
                                send_msg(chat_id, f"⚠️ *{market}* için henüz tam liste oluşturulmadı. Lütfen önce tarama başlat.")

                        # Normal mesaj veya Kanal paylaşımı geldiyse
                        elif "message" in item or "channel_post" in item:
                            msg = item.get("message") or item.get("channel_post")
                            chat_id = str(msg.get("chat", {}).get("id", ""))
                            text = msg.get("text", "").strip().lower()
                            
                            if chat_id not in ALLOWED_CHAT_IDS:
                                print(f"🔍 Yeni Chat ID Tespit Edildi: {chat_id} | Mesaj: {text}")
                                # Kanala botu admin yaptıysan, kanala /id yazıp ID'yi buradan görebilirsin.
                                continue
                            
                            # Komut mu yoksa Hisse mi kontrol et
                            if text == "/start" or text == "/menu":
                                send_menu(chat_id)
                            elif text == "/bist":
                                # Callback logic for cmd_bist
                                perform_saved_check(chat_id, "BIST")
                            elif text == "/nasdaq":
                                perform_saved_check(chat_id, "NASDAQ")
                            elif text == "/crypto":
                                perform_saved_check(chat_id, "CRYPTO")
                            elif text == "/tara_bist":
                                send_msg(chat_id, "⏳ *BIST* taraması başlatılıyor (1-2 dk)...")
                                threading.Thread(target=perform_scan, args=("BIST",), daemon=True).start()
                            elif text == "/tara_crypto":
                                send_msg(chat_id, "⏳ *CRYPTO* taraması başlatılıyor...")
                                threading.Thread(target=perform_scan, args=("CRYPTO",), daemon=True).start()
                            elif text == "/github":
                                trigger_github_action(chat_id)
                            elif text.startswith("/analiz"):
                                parts = text.split()
                                if len(parts) >= 2:
                                    sym = parts[1].upper()
                                    send_msg(chat_id, f"🔍 *{sym}* analiz ediliyor...")
                                    threading.Thread(target=analyze_single_stock, args=(chat_id, sym), daemon=True).start()
                                else:
                                    send_msg(chat_id, "⚠️ Kullanım: /analiz THYAO")
                            else:
                                # Pazar/Borsa Özeti Sorgusu
                                if any(x in text_clean for x in ["borsa", "piyasa", "durum", "ozet", "özet"]):
                                    market_info = ""
                                    if os.path.exists(DATA_FILE):
                                        with open(DATA_FILE, "r") as f:
                                            saved = json.load(f)
                                        market_info = f"BIST: {saved.get('BIST_time', '-')}\nNASDAQ: {saved.get('NASDAQ_time', '-')}"
                                    
                                    send_msg(chat_id, "📈 *Piyasa genel durumu analiz ediliyor...*")
                                    # Burası için de LLM kullanılabilir ama şimdilik hızlı cevap:
                                    msg = f"🛰️ *Piyasa Gözlem Raporu*\n\n{market_info}\n\nDetaylı sonuçlar için aşağıdaki menüyü kullanabilirsin."
                                    send_menu(chat_id)
                                    continue

                                # Doğal Dil ve Hisse Analizi Tetikleyicileri
                                text_clean = text.lower().replace("/", "").replace("$", "")
                                
                                # Cümle içinden hisse kodunu bul (Örn: "THYAO ne olur?" -> "THYAO")
                                found_symbol = None
                                for s in all_symbols:
                                    if s.lower() in text_clean:
                                        found_symbol = s
                                        break
                                
                                # Eğer hisse bulunduysa ve bir soru/analiz talebi varsa
                                if found_symbol:
                                    threading.Thread(
                                        target=analyze_single_stock, 
                                        args=(chat_id, found_symbol), 
                                        daemon=True
                                    ).start()
                                elif len(text_clean) >= 2 and len(text_clean) <= 6 and text_clean.isalpha():
                                    # Sadece kısa bir kod yazıldıysa (örn: thy)
                                    threading.Thread(
                                        target=analyze_single_stock, 
                                        args=(chat_id, text_clean.upper()), 
                                        daemon=True
                                    ).start()
                                else:
                                    send_menu(chat_id)
                        
        except Exception as e:
            time.sleep(5)


def perform_saved_check(chat_id, market):
    """Buluttan senkronize eder ve kayıtlı dosyadan sonucu okur."""
    sync_from_cloud(DATA_FILE) # Önce GitHub'dan en güncel JSON'u çek
    if not os.path.exists(DATA_FILE):
        send_msg(chat_id, f"⚠️ *{market}* için henüz kaydedilmiş bir tarama sonucu yok.")
        return
    try:
        with open(DATA_FILE, "r") as f:
            saved = json.load(f)
        
        ans = saved.get(market, f"❌ *{market}* için önbellekte henüz sonuç yok.")
        ans_time = saved.get(market + "_time", "")
        if ans_time: ans += f"\n_Son Güncelleme: {ans_time}_"
        send_msg(chat_id, ans)
    except Exception as e:
        send_msg(chat_id, f"❌ Dosya okuma hatası: {e}")

if __name__ == '__main__':
    print("🤖 VIP Telegram Autopilot Robotu Başlatıldı ve Dinlemede!")
    set_bot_commands()
    t1 = threading.Thread(target=schedule_loop, daemon=True)
    t2 = threading.Thread(target=polling_loop, daemon=True)
    
    t1.start()
    t2.start()
    
    while True:
        time.sleep(1)
