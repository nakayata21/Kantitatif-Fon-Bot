import os
import pandas as pd
from streamlit_app import run_scan
from constants import DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER
import requests
from datetime import datetime
import pytz

# GMT+3 (Türkiye) saati için timezone ayarı
TR_TZ = pytz.timezone("Europe/Istanbul")

# GitHub Secrets'ten okuyacağız, veya varsayılanları kullanacağız.
# Güvenlik uyarısı: Hardcoded tokenlar kaldırıldı. GitHub Secrets üzerinden yönetilmelidir.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8336526803:AAEvg9b0P9Em5MSND9uCb9RfbTGXBHDGdAA")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1070470722")
MARKET = os.environ.get("TARGET_MARKET", "BIST")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "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")

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

from reporting import format_telegram_message, TR_TZ

def get_ai_commentary(market, df_res):
    """OpenRouter üzerinden AI yorumu alır."""
    if not OPENROUTER_API_KEY:
        print("DEBUG: OPENROUTER_API_KEY bulunamadı, AI yorumu atlanıyor.")
        return None
    
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    if not buy_signals.empty:
        top_stocks = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
        title = "onaylı AL veren en iyi 5 hisse"
    else:
        top_stocks = df_res.sort_values(by="Kalite", ascending=False).head(5)
        title = "şu an onaylı AL vermese de en yüksek kalite puanına sahip 5 hisse"
    
    # Tarama verilerini AI'ya gönderilecek metin formatına çevir
    stock_data = ""
    for idx, row in top_stocks.iterrows():
        stock_data += f"Hisse: {row['Hisse']}\n"
        stock_data += f"  Kalite Skoru: {row['Kalite']}\n"
        stock_data += f"  Sinyal: {row['Sinyal']} | Aksiyon: {row['Aksiyon']}\n"
        stock_data += f"  Özel Durum (Kritik): {row.get('Özel Durum', '-')}\n"
        stock_data += f"  ULTIMATE SİNYAL: {'Evet' if row.get('UT_Plus_Div', False) else 'Hayır'}\n"
        
        pe_str = f"F/K: {round(float(row['pe_ratio']),1)}" if pd.notna(row.get('pe_ratio')) and str(row.get('pe_ratio')) != "nan" else ""
        pb_str = f"PD/DD: {round(float(row['pb_ratio']),1)}" if pd.notna(row.get('pb_ratio')) and str(row.get('pb_ratio')) != "nan" else ""
        if pe_str or pb_str:
            stock_data += f"  Temel Veriler: {pe_str} | {pb_str} | Not: {row.get('isy_grade', '-')}\n"
            
        stock_data += f"  R/R Oranı: {row.get('R/R', '-')}\n\n"
    
    prompt = f"""Aşağıda {market} piyasasından filtrelenmiş algoritmik sistemin seçtiği en iyi {len(top_stocks)} hissenin teknik ve temel verileri var:
{stock_data}

Sen üst düzey bir Quant Analisti ve Portföy Yöneticisisin. Sana verilen teknik "Özel Durumlar" (örneğin Pozitif Uyumsuzluk veya UT Bot) ile "Temel Verileri" (F/K, PD/DD) harmanlayarak, her hisse için *1-2 cümlelik çok keskin, net ve profesyonel (ama herkesin anlayacağı kadar sade)* bir analiz yap.

Kurallar:
1. Temel analiz verisi (F/K - PD/DD) varsa ucuz/pahalı yorumu yap.
2. Sinyal "ULTIMATE SİNYAL: Evet" ise bunun teknik açıdan çok nadir ve güçlü bir alım fırsatı olduğunu vurgula.
3. Asla yatırım tavsiyesi veriyorum demezsin, "Sistem verilerine göre..." diye konuşursun. Hissenin riskli mi yoksa güvenli bir dönüşte mi olduğunu net belirt. Bol ilgili emoji kullan."""
    
    try:
        from openai import OpenAI
        
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        
        response = client.chat.completions.create(
            model="nvidia/nemotron-3-super-120b-a12b:free",
            messages=[
                {"role": "system", "content": "Sen dünyanın en büyük hedge fonlarından birinde çalışan, soğukkanlı, disiplinli ve verilerle konuşan elit bir Türk Quant Analisti ve Portföy Yöneticisisin. Gereksiz heyecan yapmazsın, sadece matematik ve istatistikle konuşursun. Aynı zamanda yatırım terimlerini halkın anlayabileceği kadar berrak bir şekilde açıklarsın."},
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
            # GitHub (TradingView) rate limit sorunları için worker sayısını ve bekleme süresini optimize et.
            workers_count = 1 if MARKET in ["BIST", "NASDAQ"] else 2
            df, errs = run_scan(symbols, MARKET, "Gunluk", delay_ms=1000, workers=workers_count)
            print(f"DEBUG: Tarama bitti. Basarili: {len(df)}, Hata: {len(errs)}")
            
            message = format_telegram_message(MARKET, df, status)
            
            # Eger tarama yapildiysa ama sinyal yoksa veya hata coksa bilgi ekle
            if len(df) == 0 and len(errs) > 0:
                message = f"🛑 *{MARKET} Tarama Hatası*\nVeri çekilemedi. Toplam {len(errs)} hata oluştu. GitHub IP engeli olabilir."
            elif not df.empty:
                # Yapay Zeka Yorumu Ekle
                ai_comment = get_ai_commentary(MARKET, df)
                if ai_comment:
                    message += f"\n\n\U0001f9e0 *YAPAY ZEKA YORUMU:*\n{ai_comment}"
                
                # Ozet bilgisi ekle
                message += f"\n\n📊 *Tarama Özeti:*\n- Toplam Sembol: {len(symbols)}\n- Başarılı: {len(df)}\n- Hata: {len(errs)}\n- Sinyal: {int((df['Sinyal'] == 'AL').sum()) if 'Sinyal' in df.columns else 0}"
            
            send_msg(message)
            print(f"[{datetime.now(TR_TZ)}] İşlem Tamamlandı. Mesaj Gönderildi!")
            os._exit(0)
        except Exception as e:
            error_msg = f"\U0001f534 GİTHUB ACTION TARAMA HATASI ({MARKET}): {str(e)}"
            print(error_msg)
            send_msg(error_msg)
            os._exit(1)
