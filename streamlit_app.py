
import streamlit as st
import pandas as pd
import numpy as np
import concurrent.futures
from datetime import datetime
import time
import os

# Local imports
from constants import DEFAULT_NASDAQ_HISSELER, DEFAULT_BIST_HISSELER, DEFAULT_CRYPTO_SYMBOLS, TIMEFRAME_OPTIONS, BIST_SECTORS
import plotly.express as px
from utils import send_telegram_message, uniq, clamp, _safe_get
from indicators import add_indicators, calculate_price_targets
from scoring import score_symbol, calculate_elite_score
from ui_components import inject_custom_css, signal_style, action_style
from data_fetcher import (
    fetch_quick_fundamentals, fetch_yf_data, 
    fetch_hist, check_index_health, get_ai_model, interval_obj,
    fetch_global_indices, get_cached_index_history, to_float
)
from database import init_db, save_scan_results, get_new_elite_entries
from signals_db import log_signal, init_db as init_signals_db
from fundamental_db import init_fund_db



# --- Veri Tespiti (GUI mi yoksa Script mi?) ---
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    is_gui = get_script_run_ctx() is not None
except:
    is_gui = False

# Initialize DBs
init_db()
init_signals_db()
init_fund_db()


def init_gui():
    st.set_page_config(page_title="Gelişmiş Hisse Tarayıcı", layout="wide", initial_sidebar_state="expanded")
    inject_custom_css()
    st.markdown('<p class="main-title">⚡ Gelişmiş Algoritmik Tarayıcı</p>', unsafe_allow_html=True)
    st.caption("Veri Odaklı Kantitatif Yatırım Terminali (VCP, Smart Money & Bollinger Squeeze)")

    if "piyasa" not in st.session_state:
        st.session_state.piyasa = "NASDAQ"

    piyasa = st.sidebar.radio("🌐 Piyasa Seçimi", ["NASDAQ", "BIST", "CRYPTO"], index=["NASDAQ", "BIST", "CRYPTO"].index(st.session_state.piyasa))

    st.sidebar.markdown("---")
    st.sidebar.subheader("🌍 Piyasa Özeti")
    g_indices = fetch_global_indices()
    c1, c2 = st.sidebar.columns(2)
    with c1:
        st.metric("BIST100", g_indices.get("BIST100", "-"))
        st.metric("ALTIN (G)", g_indices.get("ALTIN (G)", "-"))
    with c2:
        st.metric("NASDAQ", g_indices.get("NASDAQ", "-"))
        st.metric("USD/TRY", g_indices.get("USD/TRY", "-"))

    st.sidebar.markdown("---")
    st.sidebar.subheader("📲 Bildirim & AI Ayarları")
    telegram_token = st.sidebar.text_input("Telegram Bot Token", type="password", key="tg_token_input", value=os.environ.get("TELEGRAM_BOT_TOKEN", "8336526803:AAEvg9b0P9Em5MSND9uCb9RfbTGXBHDGdAA"))
    telegram_chat_id = st.sidebar.text_input("Telegram Chat ID", key="tg_chat_id_input", value=os.environ.get("TELEGRAM_CHAT_ID", "1070470722"))
    if "or_key_input" not in st.session_state:
        st.session_state.or_key_input = os.environ.get("OPENROUTER_API_KEY", "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")
    
    openrouter_key = st.session_state.or_key_input

    # Trend Analiz Butonu (SQLite entegrasyonu ile)
    if st.sidebar.button("💎 Yeni Elit Hisseleri Bul"):
        new_elites = get_new_elite_entries()
        if not new_elites.empty:
            st.sidebar.success(f"Son taramada {len(new_elites)} yeni elit hisse tespit edildi!")
            st.sidebar.dataframe(new_elites[['hisse', 'elite_skor']])
        else:
            st.sidebar.info("Yeni elit hisse bulunamadı.")

    if piyasa != st.session_state.piyasa:
        st.session_state.piyasa = piyasa
        
        if piyasa == "NASDAQ":
            st.session_state.symbols_text = ", ".join(DEFAULT_NASDAQ_HISSELER)
        elif piyasa == "BIST":
            st.session_state.symbols_text = ", ".join(DEFAULT_BIST_HISSELER)
        else:
            st.session_state.symbols_text = ", ".join(DEFAULT_CRYPTO_SYMBOLS)
            
        st.session_state.scan_df = pd.DataFrame()
        st.session_state.scan_errs = []
        st.rerun()    # --- Veritabanı İlklendirme ---
    init_db()

    if is_gui and "symbols_text" not in st.session_state:
        if st.session_state.piyasa == "NASDAQ":
            st.session_state.symbols_text = ", ".join(DEFAULT_NASDAQ_HISSELER)
        elif st.session_state.piyasa == "BIST":
            st.session_state.symbols_text = ", ".join(DEFAULT_BIST_HISSELER)
        else:
            st.session_state.symbols_text = ", ".join(DEFAULT_CRYPTO_SYMBOLS)
            
    if is_gui and "scan_df" not in st.session_state:
        st.session_state.scan_df = pd.DataFrame()
    if is_gui and "scan_errs" not in st.session_state:
        st.session_state.scan_errs = []

    main_tab1, main_tab2 = st.tabs(["🚀 Sistem Taraması (Screener)", "⏪ Geriye Dönük Test (Backtest)"])

    with main_tab1:
        st.subheader(f"{st.session_state.piyasa} Taraması")
        symbols_input = st.text_area(f"{st.session_state.piyasa} Semboller", key="symbols_text", height=120)
        symbols = uniq([x.strip().upper() for x in symbols_input.split(",") if x.strip()])

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            tf_name = st.selectbox("Zaman Dilimi", list(TIMEFRAME_OPTIONS.keys()), index=0)
        with c2:
            delay_ms = st.slider("Sembol Gecikme (ms)", 300, 2000, 500, 50)
        with c3:
            workers = st.selectbox("⚡ Paralel Baglanti", options=[1, 2, 3, 4, 5], index=2)
        with c4:
            signal_filter = st.selectbox("Sinyal Filtresi", ["Tümü", "Sadece AL", "Sadece ŞORT"], index=0)

        if st.button("Taramayi Baslat", type="primary"):
            with st.spinner(f"{st.session_state.piyasa} verileri analiz ediliyor..."):
                df_res, err_res = run_scan(symbols, st.session_state.piyasa, tf_name, delay_ms, workers=workers)
                st.session_state.scan_df = df_res
                st.session_state.scan_errs = err_res
                st.session_state.scan_time = datetime.now().strftime("%H:%M:%S")

                # DB'ye Kaydet
                save_scan_results(df_res, st.session_state.piyasa, tf_name)

                if st.session_state.get("tg_token_input") and st.session_state.get("tg_chat_id_input") and not df_res.empty:
                    from reporting import format_telegram_message
                    msg = format_telegram_message(st.session_state.piyasa, df_res, "OPEN")
                    
                    if st.session_state.get("or_key_input"):
                        try:
                            from github_scan_action import get_ai_commentary
                            os.environ["OPENROUTER_API_KEY"] = st.session_state.get("or_key_input")
                            ai_msg = get_ai_commentary(st.session_state.piyasa, df_res)
                            if ai_msg:
                                msg += f"\n\n🤖 *AI ANALİZİ:*\n{ai_msg}"
                        except Exception as e:
                            print(f"AI Error: {e}")
                    
                    send_telegram_message(st.session_state.tg_token_input, st.session_state.tg_chat_id_input, msg)
                    st.success("✅ Telegram bildirimi gönderildi!")

        # --- SONUÇLARI GÖSTER ---
        # Tarama yapılmışsa (veya cache'ten geliyorsa) sonuçları ve hataları göster
        if not st.session_state.scan_df.empty or st.session_state.scan_errs:
            st.markdown(f"**Son Tarama:** {st.session_state.get('scan_time', '-')} | **Hisse Sayısı:** {len(st.session_state.scan_df)} | **Hata:** {len(st.session_state.scan_errs)}")
            
            df_to_show = st.session_state.scan_df.copy()
            if signal_filter == "Sadece AL":
                df_to_show = df_to_show[df_to_show["Sinyal"] == "AL"].copy()
            elif signal_filter == "Sadece ŞORT":
                df_to_show = df_to_show[df_to_show["Sinyal"] == "AÇIĞA SAT"].copy()
                
            cur_tf = tf_name if 'tf_name' in locals() else "Gunluk"
            
            # Her durumda UI'ı render et, hatalar sekmesini içerecek
            render_ui_results(df_to_show, cur_tf, st.session_state.scan_errs)
            
            if not df_to_show.empty:
                render_ai_assistant(df_to_show, st.session_state.get("or_key_input", ""))
        else:
             st.info("Henüz tarama yapılmadı. 'Taramayı Başlat' butonuna tıklayarak en güncel verileri analiz edebilirsiniz.")

    with main_tab2:
        render_backtest_tab()

def render_ui_results(df, tf_name, errs=None):
    if df is None or df.empty:
        st.warning("Gösterilecek veri bulunamadı. Lütfen tarama yapın.")
        if errs:
            for e in errs: st.error(e)
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Toplam", len(df))
    m2.metric("AL Sinyali", int((df["Sinyal"] == "AL").sum()))
    m3.metric("AÇIĞA SAT", int((df["Sinyal"] == "AÇIĞA SAT").sum()))
    m4.metric("Ort Risk", round(float(df["Dusus Riski"].mean()), 1))

    st.markdown("---")

    tabs = st.tabs([
        "📅 Uzun Vade", "📅 Orta Vade", "📅 Kısa Vade", "💎 ELİT HİSSELER", 
        "📊 Temel Analiz", "📈 Stan Weinstein", "🚀 Mark Minervini",
        "📉 Dip", "🚀 Breakout", "📈 Momentum", "💥 Hacim Patlaması", 
        "🗜️ Bollinger Sıkışması", "📐 Konsolidasyon", "❌ Hatalar & Loglar"
    ])
    
    (tab_uzun, tab_orta, tab_kisa, tab_elite, tab_fundamental, tab_weinstein, tab_minervini, 
     tab2, tab3, tab4, tab5, tab6, tab7, tab_errs) = tabs

    with tab_uzun:
        if "Vade" in df.columns:
            uzun_df = df[df["Vade"] == "Uzun"]
            render_scan_table(uzun_df, sort_col="Kalite")
    with tab_orta:
        if "Vade" in df.columns:
            orta_df = df[df["Vade"] == "Orta"]
            render_scan_table(orta_df, sort_col="Kalite")
    with tab_kisa:
        if "Vade" in df.columns:
            kisa_df = df[df["Vade"] == "Kısa"]
            render_scan_table(kisa_df, sort_col="Kalite")
    with tab_elite:
        if "Elite Skor" in df.columns:
            elite_df = df.sort_values(by="Elite Skor", ascending=False)
            render_scan_table(elite_df, sort_col="Elite Skor")
        else:
            st.info("Elite veri yok.")
    
    with tab_fundamental:
        st.subheader("Temel Analiz (Haftalık İş Yatırım Taraması Verileri)")
        st.caption("F-Score, F/K ve PD/DD rasyolarına göre en sağlam şirketler.")
        if "isy_score" in df.columns:
            render_scan_table(df[df["isy_score"] > 0], sort_col="isy_score")
        else:
            st.info("Temel analiz verisi bulunamadı. Lütfen haftalık taramanın bitmesini bekleyin.")
    
    with tab_weinstein:
        st.subheader("Stan Weinstein - Aşama Analizi")
        st.caption("Fiyatın 30 haftalık SMA üzerinde olduğu ve SMA'nın yukarı döndüğü (Aşama 2) hisseler.")
        weinstein_df = df[df["Weinstein"] == "Aşama 2"].copy()
        render_scan_table(weinstein_df, sort_col="Kalite")
        
    with tab_minervini:
        st.subheader("Mark Minervini - Trend Template")
        st.caption("Aşama 2 trendinde olan, SMA 50 > 150 > 200 dizilimini sağlayan kurumsal trend adayları.")
        minervini_df = df[df["Trend Sablonu"] == "✅ GÜÇLÜ (MINERVINI)"].copy()
        render_scan_table(minervini_df, sort_col="Kalite")
    with tab2: render_scan_table(df, sort_col="Dip Skor")
    with tab3: render_scan_table(df, sort_col="Breakout Skor")
    with tab4: render_scan_table(df, sort_col="Momentum Skor")
    with tab5: render_scan_table(df[df["Hacim Spike"] >= 2.0], sort_col="Hacim Spike")
    with tab6: render_scan_table(df[df["Daralma (Squeeze)"] == "🗜 İzlenir"], sort_col="Bollinger Genisligi")
    with tab7: render_scan_table(df, sort_col="Konsol Skor")
    
    with tab_errs:
        st.subheader("⚠️ Tarama Sırasında Oluşan Hatalar")
        if errs:
            for e in errs:
                st.error(e)
        else:
            st.success("Tüm semboller başarıyla tarandı.")

    # --- YENİ: TAKAS MONİTÖRÜ SEKME ÖZELLEŞTİRMESİ ---
    st.markdown("---")
    res_col1, res_col2 = st.columns(2)
    with res_col1:
        st.subheader("🏢 Takas & AKD Detaylı İzleyici")
        st.caption("En iyi 10 'AL' sinyalinin kurumsal takas verilerini buradan kontrol edebilirsiniz.")
        al_hisseler = df[df["Sinyal"] == "AL"].head(10)
        if not al_hisseler.empty:
            for _, row in al_hisseler.iterrows():
                with st.expander(f"📌 {row['Hisse']} Takas Verisi"):
                    st.write(f"Takas Kararı: **{row.get('Takas Karari', '-')}**")
                    st.write(f"Takas Puanı: **{row.get('Takas Puani', 0)}**")
                    st.write("Sinyaller:")
                    for sig in str(row.get('takas_detay', '-')).split('|'):
                        st.info(sig.strip())
        else:
            st.info("Henüz güçlü takas onayı alan AL sinyali yok.")

    # Korelasyon ve Sektör Analizi (Alt Bölüm)
    render_correlation_analysis(df, st.session_state.piyasa, tf_name)

def render_ai_assistant(df: pd.DataFrame, api_key: str):
    st.markdown("---")
    st.subheader("🤖 Yapay Zeka Veri Asistanı")
    st.caption("Ekranda listelenen hisse verilerine dayanarak AI'dan puanlama, özetleme veya en iyi fırsatları bulmasını isteyebilirsiniz.")
    
    question = st.text_input("Tarama verileriyle ilgili ne öğrenmek istersiniz?", placeholder="Örn: En düşük düşüş riskine sahip ve kalitesi 60'ın üzerinde olan ilk 3 hisseyi benim için açıkla.")
    
    if st.button("Soruyu Sor", type="primary"):
        if not api_key:
            st.error("Bu özelliği kullanmak için soldaki menüden OpenRouter API anahtarını girmelisiniz.")
            return
            
        with st.spinner("AI verileri inceliyor, lütfen bekleyin..."):
            try:
                from openai import OpenAI
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
                
                # Veriyi AI'ın anlayacağı CSV formatına çevir (Hız ve Token tasarrufu için top 30)
                display_cols = ["Hisse", "Kalite", "Sinyal", "Dusus Riski", "Guven", "Özel Durum", "Aksiyon", "Trend Skor", "Dip Skor", "Momentum Skor", "R/R"]
                # Mevcut sütunları güvenli şekilde al
                safe_cols = [c for c in display_cols if c in df.columns]
                
                context_df = df.sort_values(by="Kalite", ascending=False).head(30)[safe_cols]
                csv_data = context_df.to_csv(index=False)
                
                system_prompt = "Sen uzman bir algoritma/veri analiz danışmanısın. Kullanıcıya verilen hisse tablosu (CSV) üzerinden net, kısa ve teknik terimleri aşırı kullanmadan sıralama ve analizler çıkar. Yalnızca tabloda olan hisseleri kullan. Cevaplarını markdown ile listeler veya tablolar halinde ver."
                user_msg = f"Şu anki tarama tablosu (İlk 30 hisse):\n{csv_data}\n\nKullanıcının Sorusu: {question}"

                response = client.chat.completions.create(
                    model="nvidia/nemotron-3-super-120b-a12b:free",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg}
                    ],
                    max_tokens=1500,
                    temperature=0.3,
                )
                
                ai_text = response.choices[0].message.content.strip()
                st.info(f"**Cevap:**\n\n{ai_text}")
            except Exception as e:
                st.error(f"Yapay zeka ile bağlantı kurulurken bir hata oluştu: {e}")

def render_correlation_analysis(df, exchange, tf_name):
    st.markdown("---")
    st.subheader("🧩 Sepet & Karar Analizi")
    st.info("Portföyünüzün risk dağılımını ve hisseler arasındaki hareket benzerliğini analiz edin.")
    
    # 1. Korelasyon Matrisi
    st.write("📊 **Fiyat Hareket Benzerliği (Son 60 Gün)**")
    
    if df.empty:
        st.warning("Analiz için veri bulunamadı.")
        return

    # Hangi hisseler analiz edilecek?
    # En yüksek kalite puanlı ilk 10 hisseyi seç
    top_stocks = df.sort_values(by="Kalite", ascending=False).head(10)["Hisse"].tolist()
    
    if len(top_stocks) < 2:
        st.warning("Korelasyon analizi için en az 2 hisse gereklidir.")
        return

    if st.button("🧩 Korelasyon Analizini Başlat"):
        from tvDatafeed import TvDatafeed
        tv = TvDatafeed()
        tf = TIMEFRAME_OPTIONS[tf_name]
        
        prices_dict = {}
        with st.spinner("Geçmiş veriler çekiliyor (60 Bar)..."):
            for sym in top_stocks:
                try:
                    raw = fetch_hist(tv, sym, "BINANCE" if exchange=="CRYPTO" else exchange, interval_obj(tf["base"]), 60)
                    if raw is not None and not raw.empty:
                        prices_dict[sym] = raw["close"]
                except:
                    continue
        
        if len(prices_dict) < 2:
            st.error("Veri çekilemedi.")
            return

        df_prices = pd.DataFrame(prices_dict).dropna()
        if df_prices.empty:
            st.error("Korelasyon için yeterli ortak veri noktası yok.")
            return
            
        corr_matrix = df_prices.pct_change().corr()
        
        fig = px.imshow(corr_matrix, 
                        text_auto=True, 
                        color_continuous_scale='RdBu_r', 
                        aspect="auto",
                        labels=dict(color="Korelasyon"),
                        title="Hisseler Arası Hareket Benzerliği (-1 ile 1 arası)")
        st.plotly_chart(fig, use_container_width=True)
        
        st.caption("💡 0.70 üzerindeki dege rler yüksek benzerlik gösterir. Riski dağıtmak için farklı sektörlerden ve düşük korelasyonlu hisseler seçmelisiniz.")
    
    # 2. Sektör Dağılımı (Sadece BIST için)
    if exchange == "BIST" and not df.empty:
        st.markdown("---")
        st.write("🏢 **Sektör Yoğunlaşması (Top 15)**")
        top_15 = df.head(15)["Hisse"].tolist()
        sectors = [BIST_SECTORS.get(s, "Diğer") for s in top_15]
        sec_counts = pd.Series(sectors).value_counts()
        
        fig_sec = px.pie(values=sec_counts.values, names=sec_counts.index, title="Sepetteki Sektör Dağılımı")
        st.plotly_chart(fig_sec, use_container_width=True)

def render_scan_table(input_df, sort_col="Kalite"):
    if input_df.empty:
        st.info("Sonuç yok.")
        return
    col_config = {
        "Hisse": st.column_config.TextColumn("📊 Hisse"),
        "Vade": st.column_config.TextColumn("⏳ Vade"),
        "Pozisyon": st.column_config.TextColumn("💰 Poz. Büyüklüğü (x)"),
        "Elite Skor": st.column_config.ProgressColumn("💎 Elite", min_value=0, max_value=100),
        "Kalite": st.column_config.ProgressColumn("⭐ Kalite", min_value=0, max_value=100),
        "Sinyal": st.column_config.TextColumn("📡 Sinyal"),
        "Weinstein": st.column_config.TextColumn("📈 Weinstein"),
        "Trend Sablonu": st.column_config.TextColumn("🚀 Trend Şablonu"),
        "Aksiyon": st.column_config.TextColumn("🎯 Aksiyon Planı"),
        "pe_ratio": st.column_config.NumberColumn("💰 F/K", format="%.2f"),
        "pb_ratio": st.column_config.NumberColumn("🏢 PD/DD", format="%.2f"),
        "isy_score": st.column_config.ProgressColumn("💎 Temel Puan", min_value=0, max_value=100),
        "isy_grade": st.column_config.TextColumn("📜 Temel Not"),
        "piotroski_score": st.column_config.ProgressColumn("📊 F-Score", min_value=0, max_value=9),
        "Takas Puani": st.column_config.ProgressColumn("🏢 Takas Puanı", min_value=0, max_value=100),
        "Takas Karari": st.column_config.TextColumn("🔍 Takas Kararı"),
        "has_bullish_div": st.column_config.CheckboxColumn("🐂 Boğa Uyumsuzluğu"),
        "div_msg": st.column_config.TextColumn("Uyumsuzluk Notu"),
    }
    display_df = input_df.sort_values(by=sort_col, ascending=False)
    st.dataframe(
        display_df.style.map(signal_style, subset=["Sinyal"]).map(action_style, subset=["Aksiyon"]),
        use_container_width=True, height=600, column_config=col_config
    )

def run_scan(symbols, exchange, tf_name, delay_ms, workers=1):
    from tvDatafeed import TvDatafeed
    from divergence import DivergenceEngine
    from data_fetcher import get_cached_index_history
    
    tv = TvDatafeed()
    div_engine = DivergenceEngine()
    tf = TIMEFRAME_OPTIONS[tf_name]
    ai_model, ai_features = get_ai_model(exchange, tf_name, _tv=tv)
    index_healthy = check_index_health(tv, exchange, tf_name)
    
    # Global Endeks Verisini Bir Kez Çek (Göreceli Güç - RS İçin)
    global_index_df = get_cached_index_history(exchange, tf_name, bars=tf["bars"])
    
    tv_exchange = "BINANCE" if exchange == "CRYPTO" else exchange
    
    rows, errs = [], []
    
    # Check if running in Streamlit to use progress bar
    is_gui = False
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is not None:
            is_gui = True
    except:
        pass

    if is_gui:
        p = st.progress(0)
        t = st.empty()
    else:
        p, t = None, None

    def scan_one(sym, worker_id=0):
        try:
            if delay_ms > 0:
                time.sleep((delay_ms / 1000.0) + (worker_id * 0.1))
            base_raw = fetch_hist(tv, sym, tv_exchange, interval_obj(tf["base"]), tf["bars"])
            conf_raw = fetch_hist(tv, sym, tv_exchange, interval_obj(tf["confirm"]), tf["confirm_bars"])
            base, conf = add_indicators(base_raw, index_df=global_index_df), add_indicators(conf_raw)
            vb = base.dropna(subset=["close", "rsi", "adx"])
            vc = conf.dropna(subset=["close", "macd_hist"])
            if vb.empty or vc.empty: return {"_err": f"{sym}: Veri yok"}

            # Divergence Analysis
            candles = base_raw[["open", "high", "low", "close", "volume"]].dropna().to_dict("records")
            div_res_data = div_engine.analyze(candles)
            has_bullish_div = (div_res_data["summary"]["bias"] == "bullish")
            div_msg = div_res_data["summary"].get("ai_hint", "")

            last, prev, conf_last = vb.iloc[-1].copy(), vb.iloc[-2] if len(vb)>1 else vb.iloc[-1].copy(), vc.iloc[-1]
            last["has_bullish_div"] = has_bullish_div
            last["div_msg"] = div_msg
            
            # --- SİNYAL TAKİBİ (Faz 4) ---
            # Geriye dönük tarama yapabilmek için vb'yi kullanıyoruz
            lookback = 15
            recent_vb = vb.tail(lookback).copy()
            # Divergence'ları seriye ekle (indeks bazlı)
            recent_vb["has_div"] = False
            for sig in div_res_data.get("signals", []):
                idx = sig.get("current_index", -1)
                # vb indeksleri datetime olduğu için candle listesindeki index ile eşleştirmek gerekecek
                # vb.iloc[idx] bazen kayabilir ama candles listesi vb ile aynı uzunluktaysa güvenlidir
                if 0 <= idx < len(vb):
                    raw_idx = vb.index[idx]
                    if raw_idx in recent_vb.index:
                        if sig.get("divergence_type") in ["positive_regular", "positive_hidden"]:
                            recent_vb.at[raw_idx, "has_div"] = True
                            
            # Sinyal türlerini tespit et (Ultimate, UT Bot, Div)
            # Ultimate = Strong UT + Bullish Div
            # UT Strong = ut_buy and (close > ema20) and (rsi > 50) and (macd > -0.5)
            # Re-calculating temporary signals for lookback bars
            ema20_ser = recent_vb["ema20"]
            rsi_ser = recent_vb["rsi"]
            macd_ser = recent_vb["macd_hist"]
            ut_buy_ser = recent_vb["ut_buy"]
            div_ser = recent_vb["has_div"]
            close_ser = recent_vb["close"]

            sig_price, sig_bars, sig_type = None, 0, "-"
            
            # Geriye doğru tara (en sonuncuyu bul)
            for i in range(len(recent_vb)-1, -1, -1):
                c_close = float(close_ser.iloc[i])
                c_ut = bool(ut_buy_ser.iloc[i])
                c_div = bool(div_ser.iloc[i])
                c_strong = c_ut and (c_close > float(ema20_ser.iloc[i])) and (float(rsi_ser.iloc[i]) > 50) and (float(macd_ser.iloc[i]) > -0.5)
                
                # Sinyal Öncelik Sıralaması
                found = False
                if c_strong and c_div:
                    sig_type, found = "🚀 ULTIMATE", True
                elif c_strong:
                    sig_type, found = "🤖 UT BOT", True
                elif c_div:
                    sig_type, found = "🐂 DİV", True
                
                if found:
                    sig_price = c_close
                    sig_bars = len(vb) - (len(vb) - len(recent_vb) + i) - 1
                    break
            
            dist_pct = 0.0
            if sig_price:
                dist_pct = ((float(last["close"]) - sig_price) / sig_price) * 100
            
            # Sinyal bilgisini last'a ekle (score_symbol'e gidecek)
            last["sig_entry_price"] = sig_price
            last["sig_entry_bars"] = sig_bars
            last["sig_entry_dist"] = dist_pct
            last["sig_entry_type"] = sig_type

            s = score_symbol(last, prev, conf_last, exchange, index_healthy)
            targets = calculate_price_targets(vb)
            
            ai_prob = 0.0
            if ai_model:
                feat = [float(_safe_get(last, c, 0.0)) for c in ai_features]
                ai_prob = ai_model.predict_proba([feat])[0][1] * 100
            
            res = {
                "Hisse": sym, 
                "AI Tahmin": f"%{round(ai_prob,1)}", 
                **s,
                "Hacim Spike": round(float(_safe_get(last, "vol_spike", 0.0)), 2),
                "Bollinger Genisligi": round(float(_safe_get(last, "bb_width", 0.0)), 2),
                "Daralma (Squeeze)": "🗜 İzlenir" if bool(_safe_get(last, "bb_squeeze", False)) else "-",
                "has_bullish_div": has_bullish_div,
                "div_msg": div_msg,
                "Takas Puani": s.get("Takas Puani", 0),
                "Takas Karari": s.get("Takas Karari", "-"),
                "Sinyal Fiyatı": sig_price if sig_price else "-",
                "Sinyal Mesafesi": f"%{round(dist_pct, 1)}" if sig_price else "-",
                "Sinyal Zamanı": f"{sig_bars} bar önce" if sig_price else "-"
            }
            if targets: res.update(targets)
            
            # --- AI ÖĞRENME LOGLAMASI (Zenginleştirilmiş) ---
            if s.get("Sinyal") in ["AL", "DİP AL", "AÇIĞA SAT"] or res.get("UT_Plus_Div"):
                feat_log = {
                    "rsi": float(_safe_get(last, "rsi", 50)),
                    "adx": float(_safe_get(last, "adx", 15)),
                    "ema20_dist": float(_safe_get(last, "ema20_dist", 0.0)),
                    "vol_spike": float(_safe_get(last, "vol_spike", 1.0)),
                    "mfi": float(_safe_get(last, "mfi", 50.0)),
                    "mansfield_rs": float(_safe_get(last, "mansfield_rs", 0.0)),
                    "above_vwap": int(_safe_get(last, "above_vwap", 0)),
                    "score": float(s.get("Skor", 0)),
                    "kalite": float(s.get("Kalite", 0))
                }
                
                # Market Bağlamını Ekle (Endeks ne yapıyor?)
                m_ctx = {}
                if global_index_df is not None and not global_index_df.empty:
                    idx_last = global_index_df.iloc[-1]
                    idx_ret_5 = ((float(idx_last["close"]) - float(global_index_df.iloc[-6]["close"])) / float(global_index_df.iloc[-6]["close"])) * 100 if len(global_index_df) > 6 else 0
                    m_ctx["index_return_5d"] = idx_ret_5
                    m_ctx["index_rsi"] = float(idx_last.get("rsi", 50))
                
                # Temel Verileri Ekle (Local DB'den hızlıca çek)
                from fundamental_db import get_fundamental_data
                fund = get_fundamental_data(sym)
                if fund:
                    feat_log.update({
                        "pe_ratio": fund.get("pe_ratio", 0),
                        "pb_ratio": fund.get("pb_ratio", 0),
                        "piotroski_score": fund.get("piotroski_score", 0),
                        "isy_score": fund.get("isy_score", 0),
                    })
                
                try:
                    log_signal(sym, exchange, float(last["close"]), s.get("Sinyal"), feat_log, market_context=m_ctx)
                except Exception as e:
                    print(f"Log Error: {e}")

            return res
        except Exception as e: return {"_err": f"{sym}: {e}"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(scan_one, s, i % workers): s for i, s in enumerate(symbols)}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            r = fut.result()
            if "_err" in r: errs.append(r["_err"])
            else: rows.append(r)
            if is_gui:
                t.write(f"Bitti: {futures[fut]} ({i}/{len(symbols)})")
                p.progress(i / len(symbols))
            else:
                print(f"Bitti: {futures[fut]} ({i}/{len(symbols)})")
    
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by="Kalite", ascending=False).reset_index(drop=True)
        # Sadece AL sinyali verenler veya Kalite puanı yüksek olanlar için temel analiz yap (Hız için limitli)
        to_check = df[df["Sinyal"] == "AL"].index.tolist()
        if len(to_check) < 3: # Eğer hiç AL yoksa en iyi 3 kaliteyi kontrol et
            to_check = df.head(3).index.tolist()
            
        for idx in to_check[:15]: # Maksimum 15 hisse için temel veri çek (Rate limit koruması)
            sym = df.loc[idx, "Hisse"]
            fund = fetch_quick_fundamentals(sym, exchange)
            if not fund.get("error"):
                elite = calculate_elite_score(df.loc[idx].to_dict(), fund)
                for k, v in elite.items(): df.at[idx, k] = v
    return df, errs

def render_backtest_tab():
    st.markdown("### ⏪ Geriye Dönük Algoritma Testi (Backtest)")
    st.markdown("Bu modül, bir hissenin geçmişte çıkarttığı 'ULTIMATE REVERSAL' veya 'UT BOT AL' sinyallerinin **X gün sonra ne kadar kazandırdığını** test eder.")
    
    col1, col2, col3 = st.columns(3)
    market = col1.selectbox("Piyasa Seç", ["BIST", "NASDAQ", "CRYPTO"], key="bt_market")
    symbol = col2.text_input("Hisse/Coin Sembolü", value="THYAO").upper()
    days_forward = col3.number_input("Test Süresi (Gün Sonrası Hedef)", min_value=1, max_value=100, value=20)
    
    if st.button("🚀 Testi Başlat", type="primary", use_container_width=True):
        with st.spinner(f"{symbol} geçmiş verileri analiz ediliyor..."):
            try:
                from data_fetcher import fetch_hist, interval_obj
                from indicators import TIMEFRAME_OPTIONS, add_indicators
                
                tf = TIMEFRAME_OPTIONS["Gunluk"]
                exch = "BIST" if market == "BIST" else ("BINANCE" if market == "CRYPTO" else "NASDAQ")
                
                # 600 bar geriye gidiyoruz ki bol sinyal yakalayalım
                raw_df = fetch_hist(st.session_state.tv, symbol, exch, interval_obj(tf["base"]), 600)
                if raw_df is None or raw_df.empty:
                    st.error("Veri alınamadı! Lütfen sembolü kontrol edin.")
                    return
                
                df = add_indicators(raw_df)
                
                results = []
                for i in range(len(df) - int(days_forward)):
                    row = df.iloc[i]
                    
                    # Sinyal Kuralları (Scoring mantığı)
                    ut_buy = row.get("ut_buy", False)
                    ema20 = row.get("ema20", 0)
                    rsi = row.get("rsi", 0)
                    macd = row.get("macd", 0)
                    has_div = row.get("has_bullish_div", False)
                    close_val = float(row["close"])
                    
                    is_ut_strong = ut_buy and (close_val > ema20) and (rsi > 50) and (macd > -0.5)
                    
                    signal_type = None
                    if is_ut_strong and has_div:
                        signal_type = "🚀 ULTIMATE REVERSAL"
                    elif is_ut_strong:
                        signal_type = "🤖 GÜÇLÜ UT BOT"
                    elif has_div:
                        signal_type = "🐂 POZİTİF UYUMSUZLUK"
                        
                    if signal_type:
                        future_close = float(df.iloc[i + int(days_forward)]["close"])
                        max_future_high = float(df.iloc[i+1 : i+int(days_forward)+1]["high"].max())
                        
                        ret_pct = ((future_close - close_val) / close_val) * 100
                        max_ret_pct = ((max_future_high - close_val) / close_val) * 100
                        
                        dt_val = df.index[i]
                        # Handling pandas timestamp formats string conversion
                        date_str = dt_val.strftime("%Y-%m-%d") if hasattr(dt_val, "strftime") else str(dt_val)
                        
                        results.append({
                            "Tarih": date_str,
                            "Kapanış": round(close_val, 2),
                            "Sinyal Türü": signal_type,
                            f"{int(days_forward)} Gün Sonra": round(future_close, 2),
                            "Kapanış Getirisi (%)": round(ret_pct, 2),
                            "Maksimum Potansiyel (%)": round(max_ret_pct, 2)
                        })
                
                if not results:
                    st.warning(f"Son 600 işlem gününde {symbol} için herhangi bir 'Güçlü Al' veya 'Uyumsuzluk' sinyali bulunamadı.")
                else:
                    res_df = pd.DataFrame(results)
                    # NaN temizliği
                    res_df = res_df.fillna(0)
                    
                    avg_ret = float(res_df["Kapanış Getirisi (%)"].mean())
                    win_rate = float((res_df["Kapanış Getirisi (%)"] > 0).mean() * 100)
                    max_avg = float(res_df["Maksimum Potansiyel (%)"].mean())
                    
                    st.success(f"Analiz Tamamlandı: Toplam {len(results)} sinyal tarihi bulundu.")
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Kazanma Oranı (Win Rate)", f"%{win_rate:.1f}")
                    m2.metric(f"Ortalama Getiri ({int(days_forward)} Gün)", f"%{avg_ret:.1f}")
                    m3.metric("Ortalama Potansiyel Zirve", f"%{max_avg:.1f}")
                    m4.metric("Toplam Sinyal Sayısı", str(len(res_df)))
                    
                    def color_cells(val):
                        try:
                            v = float(val)
                            color = '#00ff0020' if v > 0 else '#ff000020' if v < 0 else ''
                            return f'background-color: {color}'
                        except: return ''
                        
                    st.dataframe(
                        res_df.style.map(color_cells, subset=["Kapanış Getirisi (%)", "Maksimum Potansiyel (%)"]),
                        use_container_width=True
                    )
                    
                    # Küçük bir AI Yorumu Eklentisi (opsiyonel ama şık durur)
                    st.info(f"💡 **İpucu:** Maksimum Potansiyel, sinyal sonrası {int(days_forward)} gün içinde hissenin gördüğü en yüksek kâr marjını gösterir. İzleyen stop-loss kullansaydınız ortalama **%{max_avg:.1f}** kadar kâr kilitleyebilirdiniz.")
                    
            except Exception as e:
                st.error(f"Backtest motorunda hata oluştu: {str(e)}")
if __name__ == "__main__":
    init_gui()
