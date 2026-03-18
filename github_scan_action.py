import os
from streamlit_app import run_scan
from constants import DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER
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
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

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
    if df_res.empty: return f"❌ {market} piyasasında fırsat bulunamadı."
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    if buy_signals.empty: return f"❌ {market} piyasasında onaylı işlem setup'ı oluşmadı."
    
    # En iyi 5
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
    status_text = "🟢 Piyasa Açık (Canlı)" if status == "OPEN" else "🕒 Piyasa Kapalı/Açılmak Üzere"
    
    msg = f"🛰️ *{market} QUANT DECISION ENGINE* ({datetime.now(TR_TZ).strftime('%H:%M')})\n"
    msg += f"⏱ Durum: {status_text}\n\n"
    
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

def get_ai_commentary(market, df_res):
    """OpenRouter üzerinden AI yorumu alır."""
    if not OPENROUTER_API_KEY:
        print("DEBUG: OPENROUTER_API_KEY bulunamadı, AI yorumu atlanıyor.")
        return None
    
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    if buy_signals.empty:
        return None
    
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
    
    # Tarama verilerini AI'ya gönderilecek metin formatına çevir
    stock_data = ""
    for idx, row in top_buys.iterrows():
        stock_data += f"Hisse: {row['Hisse']}\n"
        stock_data += f"  Kalite Skoru: {row['Kalite']}\n"
        stock_data += f"  Sinyal: {row['Sinyal']} | Aksiyon: {row['Aksiyon']}\n"
        stock_data += f"  RSI: {row.get('RSI', '-')} | ADX: {row.get('ADX', '-')}\n"
        stock_data += f"  Hacim Spike: x{row.get('Hacim Spike', 0)}\n"
        stock_data += f"  R/R Oranı: {row.get('R/R', '-')}\n"
        stock_data += f"  AI Tahmin: {row.get('AI Tahmin', '-')}\n"
        stock_data += f"  Özel Durum: {row.get('Özel Durum', '-')}\n\n"
    
    prompt = f"""Aşağıda {market} piyasasından taranan en iyi 5 hissenin verileri var:
{stock_data}

Bu verileri teknik terim kullanmadan, sanki borsa ile hiç ilgilenmemiş birine durumu özetler gibi her hisse için 1 kısa cümlede anlat. 
Hissenin durumu iyi mi kötü mü, şu an almak mantıklı mı yoksa "iş işten geçmiş" mi net söyle. 
Mahalle bakkalının anlayacağı kadar sade ve samimi bir dil kullan. Bol emoji ekle."""
    
    try:
        from openai import OpenAI
        
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        
        response = client.chat.completions.create(
            model="nvidia/nemotron-3-super-120b-a12b:free",
            messages=[
                {"role": "system", "content": "Sen borsa verilerini halkın diliyle anlatan, teknik terimlerden nefret eden, samimi ve dürüst bir Türk yatırım danışmanısın. Doğrudan sonuca odaklanırsın."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7,
        )
        
        ai_text = response.choices[0].message.content.strip()
        print(f"✅ AI Yorumu alındı ({len(ai_text)} karakter)")
        return ai_text
        
    except Exception as e:
        print(f"❌ AI Yorum Hatası: {str(e)}")
        return None


if __name__ == "__main__":
    status = get_market_status(MARKET)
    
    # Kripto için her zaman açık diyebiliriz (Borsa tatili yoktur)
    if MARKET == "CRYPTO":
        status = "OPEN"

    if status == "CLOSED":
        print(f"[{datetime.now(TR_TZ)}] Piyasa kapalı ({MARKET}), tarama atlanıyor.")
    else:
        print(f"[{datetime.now(TR_TZ)}] Durum: {status}. {MARKET} taraması başlatılıyor...")
        
        if MARKET == "BIST":
            symbols = DEFAULT_BIST_HISSELER
        elif MARKET == "NASDAQ":
            symbols = DEFAULT_NASDAQ_HISSELER
        elif MARKET == "CRYPTO":
            from constants import DEFAULT_CRYPTO_SYMBOLS
            symbols = DEFAULT_CRYPTO_SYMBOLS
        else:
            symbols = DEFAULT_BIST_HISSELER # Fallback
            
        try:
            # run_scan'daki gui=False argümanı kaldırıldı (Otomatik algılıyor)
            df, errs = run_scan(symbols, MARKET, "Gunluk", delay_ms=500, workers=5)
            message = format_telegram_message(MARKET, df, status)
            
            # Yapay Zeka Yorumu Ekle
            if not df.empty:
                ai_comment = get_ai_commentary(MARKET, df)
                if ai_comment:
                    message += f"\n\n\U0001f9e0 *YAPAY ZEKA YORUMU:*\n{ai_comment}"
            
            send_msg(message)
            print(f"[{datetime.now(TR_TZ)}] İşlem Başarıyla Tamamlandı. Mesaj Gönderildi!")
            os._exit(0)
        except Exception as e:
            error_msg = f"\U0001f534 GİTHUB ACTION TARAMA HATASI ({MARKET}): {str(e)}"
            print(error_msg)
            send_msg(error_msg)
            os._exit(1)
