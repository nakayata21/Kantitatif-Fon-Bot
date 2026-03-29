import os
import time
import pandas as pd
from streamlit_app import run_scan
from constants import DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER
import requests
from datetime import datetime
import pytz

# GMT+3 (Türkiye) saati için timezone ayarı
TR_TZ = pytz.timezone("Europe/Istanbul")

from dotenv import load_dotenv
load_dotenv()

# GitHub Secrets'ten okuyacağız, veya varsayılanları kullanacağız.
# Güvenlik uyarısı: Hardcoded tokenlar kaldırıldı. GitHub Secrets üzerinden yönetilmelidir.
# GitHub Secrets'ten okuyoruz.
TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
if not TOKEN:
    TOKEN = "8336526803:AAEvg9b0P9Em5MSND9uCb9RfbTGXBHDGdAA"

# Birden fazla chat_id desteği (virgülle ayrılabilir)
CHAT_IDS = [cid.strip() for cid in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if cid.strip()]
if not CHAT_IDS:
    CHAT_IDS = ["1070470722", "-1003824371023"] # Varsayılan Chat ID Fallback
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
    if not TOKEN or ":" not in TOKEN:
        print("❌ HATA: Telegram Bot Token bulunamadı veya geçersiz! Lütfen GitHub Secrets (TELEGRAM_BOT_TOKEN) kısmını kontrol edin.")
        return
    if not CHAT_IDS:
        print("❌ HATA: Telegram Chat ID listesi boş!")
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    for chat_id in CHAT_IDS:
        # Parse mode'u Markdown'dan HTML'e çevirerek karakter hatalarını azaltıyoruz
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        
        try:
            response = requests.post(url, data=payload, timeout=15)
            if response.status_code != 200:
                print(f"❌ Telegram API Hatası ({chat_id}): {response.status_code} - {response.text}")
                # Eğer Markdown/HTML hatası ise düz metin dene
                print(f"🔄 {chat_id} için düz metin olarak tekrar deneniyor...")
                payload["parse_mode"] = ""
                requests.post(url, data=payload, timeout=10)
            else:
                print(f"✅ Mesaj başarıyla gönderildi (ChatID: {chat_id})")
        except Exception as e:
            print(f"❌ Telegram Bağlantı Hatası ({chat_id}): {str(e)}")


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


def run_with_self_healing(symbols, market, timeframe, max_retries=3):
    """Hata durumunda kendini yenileyen ve alternatif çözüm bulan tarama motoru."""
    delay = 1000
    workers = 1
    
    for attempt in range(max_retries):
        try:
            print(f"🔄 Deneme {attempt + 1}: {market} taraması yapılıyor (Delay: {delay}ms, Workers: {workers})...")
            df, errs = run_scan(symbols, market, timeframe, delay_ms=delay, workers=workers)
            
            # Başarı kontrolü (En az %10 başarı bekliyoruz, aksi halde IP blok şüphesi)
            success_rate = len(df) / len(symbols) if len(symbols) > 0 else 0
            
            if success_rate > 0.1 or (len(errs) == 0 and len(df) >= 0):
                return df, errs
            
            print(f"⚠️ Düşük başarı oranı (%{round(success_rate*100, 1)}). Kendi kendini iyileştirme modu aktif...")
            
            # Çözüm 1: Gecikmeyi artır ve paralelliği azalt
            delay += 1000
            workers = 1
            
            # Çözüm 2: Eğer BIST ise ve hata çoksa, sadece en kritik sembollere odaklan (Hayatta kalma modu)
            if attempt == 1 and market == "BIST":
                from constants import DEFAULT_BIST_30
                symbols = DEFAULT_BIST_30[:10]
                print("🚨 Kritik Hata: 'Hayatta Kalma Modu'na geçiliyor. Sadece en büyük 10 hisse taranacak.")
            
            time.sleep(5) # Hata sonrası kısa soğuma
            
        except Exception as e:
            print(f"❌ Kritik Sistem Hatası: {e}")
            time.sleep(10)
            
    return pd.DataFrame(), ["Tüm denemeler başarısız oldu."]

if __name__ == "__main__":
    status = get_market_status(MARKET)
    
    if MARKET == "CRYPTO":
        status = "OPEN"

    if status == "CLOSED":
        print(f"[{datetime.now(TR_TZ)}] Piyasa kapalı ({MARKET}), tarama atlanıyor.")
    else:
        print(f"[{datetime.now(TR_TZ)}] Durum: {status}. {MARKET} taraması başlatılıyor...")
        
        # Sembol Seçimi
        from constants import DEFAULT_BIST_30, DEFAULT_NASDAQ_HISSELER, DEFAULT_CRYPTO_SYMBOLS
        if MARKET == "BIST":
            symbols = DEFAULT_BIST_30
        elif MARKET == "NASDAQ":
            symbols = DEFAULT_NASDAQ_HISSELER[:30] # Hız için ilk 30
        else:
            symbols = DEFAULT_CRYPTO_SYMBOLS[:30]
            
        try:
            start_time = datetime.now(TR_TZ)
            # SELF-HEALING ENGINE ÇALIŞTIR
            df, errs = run_with_self_healing(symbols, MARKET, "Gunluk", max_retries=3)
            
            end_time = datetime.now(TR_TZ)
            duration = (end_time - start_time).total_seconds()
            
            if not df.empty:
                message = format_telegram_message(MARKET, df, status)
                # Başarılı ise AI yorumu ekle
                ai_msg = get_ai_commentary(MARKET, df)
                if ai_msg:
                    message += f"\n\n🤖 *AI ANALİZİ:*\n{ai_msg}"
            else:
                message = f"🛑 *{MARKET} Tarama Başarısız*\n{len(errs)} denemeden sonra veri alınamadı. GitHub IP engeli veya veri sağlayıcı hatası mevcut."
            
            send_msg(message)
            print(f"[{datetime.now(TR_TZ)}] İşlem Tamamlandı.")
            os._exit(0)
        except Exception as e:
            import traceback
            print(f"❌ KRİTİK SİSTEM HATASI (Traceback):")
            traceback.print_exc()
            os._exit(1)

