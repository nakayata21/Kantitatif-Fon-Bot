
import streamlit as st
import pandas as pd
import numpy as np
import concurrent.futures
from datetime import datetime
import time
import os

# Local imports
from constants import DEFAULT_NASDAQ_HISSELER, DEFAULT_BIST_HISSELER, DEFAULT_CRYPTO_SYMBOLS, TIMEFRAME_OPTIONS
from utils import send_telegram_message, uniq, clamp, _safe_get
from indicators import add_indicators, calculate_price_targets
from scoring import score_symbol, calculate_elite_score
from ui_components import inject_custom_css, signal_style, action_style
from data_fetcher import (
    fetch_quick_fundamentals, fetch_yf_data, 
    fetch_hist, check_index_health, get_ai_model, interval_obj,
    fetch_global_indices
)
from database import init_db, save_scan_results, get_new_elite_entries

# Initialize DB
init_db()

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
    telegram_token = st.sidebar.text_input("Telegram Bot Token", type="password", key="tg_token_input", value="")
    telegram_chat_id = st.sidebar.text_input("Telegram Chat ID", key="tg_chat_id_input", value="1070470722")
    openrouter_key = st.sidebar.text_input("OpenRouter API Key (AI Yorum)", type="password", key="or_key_input", value=os.environ.get("OPENROUTER_API_KEY", ""))

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
        st.rerun()

    if "symbols_text" not in st.session_state:
        if st.session_state.piyasa == "NASDAQ":
            st.session_state.symbols_text = ", ".join(DEFAULT_NASDAQ_HISSELER)
        elif st.session_state.piyasa == "BIST":
            st.session_state.symbols_text = ", ".join(DEFAULT_BIST_HISSELER)
        else:
            st.session_state.symbols_text = ", ".join(DEFAULT_CRYPTO_SYMBOLS)
            
    if "scan_df" not in st.session_state:
        st.session_state.scan_df = pd.DataFrame()
    if "scan_errs" not in st.session_state:
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
            only_buy = st.checkbox("Sadece AL", value=False)

        if st.button("Taramayi Baslat", type="primary"):
            df_res, err_res = run_scan(symbols, st.session_state.piyasa, tf_name, delay_ms, workers=workers)
            st.session_state.scan_df = df_res
            st.session_state.scan_errs = err_res
            st.session_state.scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # DB'ye Kaydet
            save_scan_results(df_res, st.session_state.piyasa, tf_name)

            if st.session_state.get("tg_token_input") and st.session_state.get("tg_chat_id_input") and not df_res.empty:
                buy_signals = df_res[df_res["Sinyal"] == "AL"]
                if not buy_signals.empty:
                    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
                    msg = f"🚀 *TARAMA SONUÇLARI ({st.session_state.piyasa})*\n"
                    for idx, row in top_buys.iterrows():
                        msg += f"💎 *{row['Hisse']}* (Elite: {row.get('Elite Skor', 0)})\n   ➤ Aksiyon: {row['Aksiyon']}\n\n"
                    send_telegram_message(telegram_token, telegram_chat_id, msg)

        df = st.session_state.scan_df.copy()
        if not df.empty:
            if only_buy:
                df = df[df["Sinyal"] == "AL"].copy()
            if not df.empty:
                render_ui_results(df)
                render_ai_assistant(df, st.session_state.get("or_key_input", ""))
        else:
            st.info("Tarama baslatildiginda sonuclar burada gorunecek.")

    with main_tab2:
        render_backtest_tab()

def render_ui_results(df):
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Toplam", len(df))
    m2.metric("AL", int((df["Sinyal"] == "AL").sum()))
    m3.metric("Ort Guven", round(float(df["Guven"].mean()), 1))
    m4.metric("Ort Risk", round(float(df["Dusus Riski"].mean()), 1))

    st.markdown("---")

    tab1, tab_elite, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "⭐ Kalite Sirala", "💎 ELİT HİSSELER", "📉 Dip", "🚀 Breakout", 
        "📈 Momentum", "💥 Hacim Patlaması", "🗜️ Bollinger Sıkışması", 
        "📐 Konsolidasyon"
    ])

    with tab1:
        render_scan_table(df, sort_col="Kalite")
    with tab_elite:
        if "Elite Skor" in df.columns:
            elite_df = df.sort_values(by="Elite Skor", ascending=False)
            render_scan_table(elite_df, sort_col="Elite Skor")
        else:
            st.info("Elite veri yok.")
    with tab2: render_scan_table(df, sort_col="Dip Skor")
    with tab3: render_scan_table(df, sort_col="Breakout Skor")
    with tab4: render_scan_table(df, sort_col="Momentum Skor")
    with tab5: render_scan_table(df[df["Hacim Spike"] >= 2.0], sort_col="Hacim Spike")
    with tab6: render_scan_table(df[df["Daralma (Squeeze)"] == "🗜 İzlenir"], sort_col="Bollinger Genisligi")
    with tab7: render_scan_table(df, sort_col="Konsol Skor")

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

def render_scan_table(input_df, sort_col="Kalite"):
    if input_df.empty:
        st.info("Sonuç yok.")
        return
    col_config = {
        "Hisse": st.column_config.TextColumn("📊 Hisse"),
        "Elite Skor": st.column_config.ProgressColumn("💎 Elite", min_value=0, max_value=100),
        "Kalite": st.column_config.ProgressColumn("⭐ Kalite", min_value=0, max_value=100),
        "Sinyal": st.column_config.TextColumn("📡 Sinyal"),
    }
    display_df = input_df.sort_values(by=sort_col, ascending=False)
    st.dataframe(
        display_df.style.map(signal_style, subset=["Sinyal"]).map(action_style, subset=["Aksiyon"]),
        use_container_width=True, height=600, column_config=col_config
    )

def run_scan(symbols, exchange, tf_name, delay_ms, workers=1):
    from tvDatafeed import TvDatafeed
    tv = TvDatafeed()
    tf = TIMEFRAME_OPTIONS[tf_name]
    ai_model, ai_features = get_ai_model(exchange, tf_name, _tv=tv)
    index_healthy = check_index_health(tv, exchange, tf_name)
    
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
            base_raw = fetch_hist(tv, sym, tv_exchange, interval_obj(tf["base"]), tf["bars"])
            conf_raw = fetch_hist(tv, sym, tv_exchange, interval_obj(tf["confirm"]), tf["confirm_bars"])
            base, conf = add_indicators(base_raw), add_indicators(conf_raw)
            vb = base.dropna(subset=["close", "rsi", "adx"])
            vc = conf.dropna(subset=["close", "macd_hist"])
            if vb.empty or vc.empty: return {"_err": f"{sym}: Veri yok"}

            last, prev, conf_last = vb.iloc[-1], vb.iloc[-2] if len(vb)>1 else vb.iloc[-1], vc.iloc[-1]
            s = score_symbol(last, prev, conf_last, exchange, index_healthy)
            targets = calculate_price_targets(vb)
            
            ai_prob = 0.0
            if ai_model:
                feat = [float(_safe_get(last, c, 0.0)) for c in ai_features]
                ai_prob = ai_model.predict_proba([feat])[0][1] * 100
            
            res = {"Hisse": sym, "AI Tahmin": f"%{round(ai_prob,1)}", **s,
                   "Hacim Spike": round(float(_safe_get(last, "vol_spike", 0.0)), 2),
                   "Daralma (Squeeze)": "🗜 İzlenir" if bool(_safe_get(last, "bb_squeeze", False)) else "-"}
            if targets: res.update(targets)
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
    st.info("Geriye dönük test mantığı burada çalışır.")
    # ... (Backtest implementation remains similar but calls updated modules)

if __name__ == "__main__":
    init_gui()
