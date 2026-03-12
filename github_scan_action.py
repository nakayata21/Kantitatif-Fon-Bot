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
    if df_res.empty: return f"❌ {market} piyasasında AL sinyali bulunamadı."
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    if buy_signals.empty: return f"❌ {market} piyasasında AL sinyali bulunamadı."
    
    # En iyi 5
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
    
    status_text = "🟢 Piyasa Açık (Canlı)" if status == "OPEN" else "🕒 Piyasa Açılmak Üzere (Ön Hazırlık)"
    
    msg = f"🚀 *{market} OTOMATİK TARAMA RAPORU*\n"
    msg += f"🗓 Tarih: {datetime.now(TR_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += f"⏱ Durum: {status_text}\n\n"
    msg += f"⭐ *EN İYİ 5 HİSSE (Kalite Sıralaması):*\n\n"
    
    for idx, row in top_buys.iterrows():
        ai_tahmin = row.get('AI Tahmin', '-')
        ozel_durum = row.get('Özel Durum', '-')
        squeeze = row.get('Daralma (Squeeze)', '-')
        bollinger = row.get('Bollinger', '-')
        vol_spike = row.get('Hacim Spike', 0.0)
        dip_skor = row.get('Dip Skor', 0.0)
        
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
    
    # === DİPTEN HACİM PATLAMASI YAPAN HİSSELER ===
    # Tüm taranmış hisseler arasından (sadece AL sinyali olanlar değil) hacim patlaması yapanları bul
    dip_hacim = df_res[
        (df_res["Hacim Spike"] >= 2.0)
    ].sort_values(by=["Dip Skor", "Hacim Spike"], ascending=[False, False]).head(5)
    
    # Zaten yukarıda gösterilenleri çıkar
    top_hisseler = set(top_buys["Hisse"].tolist())
    dip_hacim_yeni = dip_hacim[~dip_hacim["Hisse"].isin(top_hisseler)]
    
    if not dip_hacim_yeni.empty:
        msg += f"💥 *DİPTEN HACİM PATLAMASI YAPANLAR:*\n\n"
        for idx, row in dip_hacim_yeni.iterrows():
            dip_s = row.get('Dip Skor', 0)
            vol_s = row.get('Hacim Spike', 0)
            sinyal = row.get('Sinyal', '-')
            kalite = row.get('Kalite', 0)
            
            durum = "🔥 DİP+HACİM" if dip_s >= 70 else "💥 HACİM"
            
            msg += f"📌 *{row['Hisse']}* ({durum})\n"
            msg += f"   ➤ Hacim: *x{vol_s}* | Dip Skor: *{dip_s}*\n"
            msg += f"   ➤ Sinyal: {sinyal} | Kalite: {kalite}\n\n"
    
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
    
    prompt = f"""Aşağıda {market} piyasasından algoritmik tarama ile bulunan en iyi 5 hissenin teknik analiz verileri var.

Tarama Verileri:
{stock_data}

Görevin:
1. Her hisse için ayrı ayrı 2-3 cümlelik sade Türkçe yorum yaz.
2. Teknik analiz terimlerini kullan ama bir borsa yeni başlayanı bile anlayabilsin.
3. RSI, Hacim, MACD gibi verileri yorumla: "Bu ne anlama geliyor?" sorusuna cevap ver.
4. Hissenin risk seviyesini belirt (düşük/orta/yüksek).
5. "Alınır mı alınmaz mı?" sorusuna net bir görüş bildir.
6. Her hissenin başına uygun emoji koy (📈 yükseliş, ⚠️ dikkat, 🔥 güçlü sinyal gibi).
7. En sona 1-2 cümlelik genel bir piyasa değerlendirmesi ekle.

Önemli: Yatırım tavsiyesi olmadığını belirtme. Doğrudan analiz yap. Sade ve anlaşılır Türkçe kullan."""
    
    try:
        from openai import OpenAI
        
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        
        response = client.chat.completions.create(
            model="nvidia/nemotron-3-super-120b-a12b:free",
            messages=[
                {"role": "system", "content": "Sen deneyimli bir Türk borsa analisti ve yatırım danışmanısın. Teknik analizi sade bir dille, herkesin anlayacağı şekilde açıklıyorsun. Yorum yaparken detaylı ve açıklayıcı ol. Emoji kullan. Türkçe yaz."},
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
    
    if status == "CLOSED":
        print(f"[{datetime.now(TR_TZ)}] Piyasa kapalı ({MARKET}), tarama atlanıyor.")
    else:
        print(f"[{datetime.now(TR_TZ)}] Durum: {status}. {MARKET} taraması başlatılıyor...")
        symbols = DEFAULT_BIST_HISSELER if MARKET == "BIST" else DEFAULT_NASDAQ_HISSELER
        
        try:
            df, errs = run_scan(symbols, MARKET, "Gunluk", delay_ms=500, workers=5, gui=False)
            message = format_telegram_message(MARKET, df, status)
            
            # Yapay Zeka Yorumu Ekle
            if not df.empty:
                ai_comment = get_ai_commentary(MARKET, df)
                if ai_comment:
                    message += f"\n\n\U0001f9e0 *YAPAY ZEKA YORUMU:*\n{ai_comment}"
            
            send_msg(message)
            print(f"[{datetime.now(TR_TZ)}] \u0130\u015flem Ba\u015far\u0131yla Tamamland\u0131. Mesaj G\u00f6nderildi!")
            os._exit(0)
        except Exception as e:
            error_msg = f"\U0001f534 G\u0130THUB ACTION TARAMA HATASI ({MARKET}): {str(e)}"
            print(error_msg)
            send_msg(error_msg)
            os._exit(1)
