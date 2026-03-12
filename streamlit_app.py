import math
import random
import time
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yf_data(ticker_symbol: str, market: str = "NASDAQ") -> dict:
    import requests
    isy_financials = None
    if ticker_symbol.endswith(".IS"):
        try:
            import isyatirimhisse as isy
            isy_sym = ticker_symbol.replace(".IS", "")
            isy_financials = isy.fetch_financials(symbols=isy_sym, exchange="TRY")
        except:
            pass
    
    last_err = None
    for attempt in range(3):
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.5",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive"
            })
            time.sleep(random.uniform(1.0, 3.0))
            tk = yf.Ticker(ticker_symbol, session=session)
            y_fin = tk.financials
            if isy_financials is not None and not isy_financials.empty:
                y_fin = isy_financials
            return {
                "info": tk.info,
                "financials": y_fin,
                "balance": tk.balance_sheet,
                "cashflow": tk.cashflow,
                "error": None
            }
        except Exception as e:
            last_err = str(e)
            wait = (2 ** attempt) + random.uniform(0.5, 1.5)
            if attempt < 2:
                time.sleep(wait)
            continue
    return {"error": last_err, "info": {}, "financials": None, "balance": None, "cashflow": None}

# st.set_page_config sadece ana uygulama olarak çalışırken çağrılmalı.
def init_gui():
    st.set_page_config(page_title="Gelişmiş Hisse Tarayıcı", layout="wide", initial_sidebar_state="expanded")
    inject_custom_css()
    st.markdown('<p class="main-title">⚡ Gelişmiş Algoritmik Tarayıcı</p>', unsafe_allow_html=True)
    st.caption("Veri Odaklı Kantitatif Yatırım Terminali (VCP, Smart Money & Bollinger Squeeze)")

    if "piyasa" not in st.session_state:
        st.session_state.piyasa = "NASDAQ"

    piyasa = st.sidebar.radio("🌐 Piyasa Seçimi", ["NASDAQ", "BIST"], index=0 if st.session_state.piyasa == "NASDAQ" else 1)

    st.sidebar.markdown("---")
    st.sidebar.subheader("📲 Telegram Bildirimleri")
    st.sidebar.caption("Taramalar bittiğinde sonuçları cebinize gönderin.")
    telegram_token = st.sidebar.text_input("Telegram Bot Token", type="password", key="tg_token_input", value="", help="@BotFather üzerinden alabilirsiniz.")
    telegram_chat_id = st.sidebar.text_input("Telegram Chat ID", key="tg_chat_id_input", value="1070470722", help="@userinfobot üzerinden alabilirsiniz.")

    if piyasa != st.session_state.piyasa:
        st.session_state.piyasa = piyasa
        if piyasa == "NASDAQ":
            st.session_state.symbols_text = ", ".join(DEFAULT_NASDAQ_HISSELER)
        else:
            st.session_state.symbols_text = ", ".join(DEFAULT_BIST_HISSELER)
        st.session_state.scan_df = pd.DataFrame()
        st.session_state.scan_errs = []
        st.rerun()

    if "symbols_text" not in st.session_state:
        st.session_state.symbols_text = ", ".join(DEFAULT_NASDAQ_HISSELER) if st.session_state.piyasa == "NASDAQ" else ", ".join(DEFAULT_BIST_HISSELER)
    if "scan_df" not in st.session_state:
        st.session_state.scan_df = pd.DataFrame()
    if "scan_errs" not in st.session_state:
        st.session_state.scan_errs = []

    main_tab1, main_tab2 = st.tabs(["🚀 Sistem Taraması (Screener)", "⏪ Geriye Dönük Test (Backtest)"])

    with main_tab1:
        st.subheader(f"{st.session_state.piyasa} Taraması")
        symbols_input = st.text_area(f"{st.session_state.piyasa} Semboller (virgulle ayir)", key="symbols_text", height=120)
        symbols = uniq([x.strip().upper() for x in symbols_input.split(",") if x.strip()])

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            tf_name = st.selectbox("Zaman Dilimi", list(TIMEFRAME_OPTIONS.keys()), index=0) # 4 Saatlik varsayılan
        with c2:
            delay_ms = st.slider("Sembol Gecikme (ms)", 300, 2000, 500, 50)
        with c3:
            workers = st.selectbox(
                "⚡ Paralel Baglanti",
                options=[1, 2, 3, 4, 5],
                index=2,  # Varsayilan olarak guvenli "3" secili gelsin
                help="1 = siradizimli (guvenli), 3-5 = paralel (hizli ama veri kopma riski var)",
            )
        with c4:
            only_buy = st.checkbox("Sadece AL", value=False)

        # Tahmini sure goster (Her hissenin ag baglanti maliyeti artik ~0.3s)
        est_sec = len(symbols) * (delay_ms / 1000 + 0.6) / max(workers, 1)
        if workers > 1:
            est_sec += 3 # Threading havuzu baslatma suresini ekle

        st.caption(
            f"📊 {len(symbols)} hisse | "
            f"⏱ Tahmini sure: ~{int(est_sec // 60)}d {int(est_sec % 60)}s "
            f"({workers} baglanti ile)"
        )

        if st.button("Taramayi Baslat", type="primary"):
            df_res, err_res = run_scan(symbols, st.session_state.piyasa, tf_name, delay_ms, workers=workers)
            st.session_state.scan_df = df_res
            st.session_state.scan_errs = err_res
            st.session_state.scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # --- TELEGRAM BİLDİRİMİ GÖNDER ---
            if st.session_state.get("tg_token_input") and st.session_state.get("tg_chat_id_input") and not df_res.empty:
                buy_signals = df_res[df_res["Sinyal"] == "AL"]
                if not buy_signals.empty:
                    # Kaliteye göre sırala ve en iyi 5'ini al
                    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(5)
                    msg = f"🚀 *YENİ TARAMA SONUÇLARI ({st.session_state.piyasa} - {tf_name})*\n\n"
                    for idx, row in top_buys.iterrows():
                        ai_tahmin = row.get('AI Tahmin', '-')
                        msg += f"📌 *{row['Hisse']}*\n"
                        msg += f"   ➤ Kalite: *{row['Kalite']}*\n"
                        msg += f"   ➤ Aksiyon: {row['Aksiyon']}\n"
                        msg += f"   ➤ R/R Oranı: {row['R/R']}\n"
                        msg += f"   ➤ AI Tahmin: {ai_tahmin}\n\n"
                    
                    success = send_telegram_message(telegram_token, telegram_chat_id, msg)
                    if success:
                        st.toast("✅ Sonuçlar Telegram'a başarıyla gönderildi!")
                    else:
                        st.toast("❌ Telegram'a gönderilirken hata oluştu (Token veya Chat ID hatalı).", icon="🚨")

        df = st.session_state.scan_df.copy()
        errs = st.session_state.scan_errs

        # Son tarama zamanini goster (varsa)
        if "scan_time" in st.session_state:
            st.caption(f"🕐 Son tarama: {st.session_state.scan_time}")

        if df.empty:
            st.info("Tarama baslatildiginda sonuclar burada gorunecek.")
        else:
            if only_buy:
                df = df[df["Sinyal"] == "AL"].copy()
            if df.empty:
                st.warning("Filtrede sonuc yok. Filtreyi gevsetin.")
            else:
                top = df.iloc[0]
                st.success(
                    f" **Sistem Tavsiyesi (Top 1):** {top['Hisse']} | **Sinyal:** {top['Sinyal']} "
                    f"| **Kalite Skoru:** {top['Kalite']} | **Smart Money:** {top['Smart Money Skor']}"
                )

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Toplam", len(df))
                m2.metric("AL", int((df["Sinyal"] == "AL").sum()))
                m3.metric("Ort Guven", round(float(df["Guven"].mean()), 1))
                m4.metric("Ort Risk", round(float(df["Dusus Riski"].mean()), 1))

                tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["⭐ Kalite Sirala", "📉 Dip", "🚀 Breakout", "📈 Momentum", "💥 Hacim Patlaması", "🗜️ Bollinger Sıkışması"])

                with tab1:
                    # Kalite = Skor - Risk*0.4 + Guven*0.25 (bilesik en iyi siralama)
                    g = df.sort_values(by=["Kalite", "Skor", "Guven"], ascending=False)
                    
                    # Seçilebilir Dataframe Etkileşimi Eklendi (Streamlit'in yeni özelliği)
                    event = st.dataframe(
                        g.style.map(signal_style, subset=["Sinyal"]).map(action_style, subset=["Aksiyon"]),
                        use_container_width=True, 
                        height=650,
                        on_select="rerun",
                        selection_mode="single-row"
                    )
                    
                    # Eğer kullanıcı satıra tıklarsa o hisseyi session'a kaydet (Backtest sekmesine aktarmak için)
                    if len(event.selection.rows) > 0:
                        selected_idx = event.selection.rows[0]
                        st.session_state.selected_ticker = g.iloc[selected_idx]["Hisse"]
                        st.success(f"📌 {st.session_state.selected_ticker} seçildi! Geriye Dönük Test sekmesine gidebilirsiniz.")

                with tab2:
                    # En yuksek dip skoru: asiri satimdan toparlanan, destek yakinindaki hisseler
                    d = df.sort_values(by=["Dip Skor", "Kalite"], ascending=False)
                    st.dataframe(d.style.map(signal_style, subset=["Sinyal"]).map(action_style, subset=["Aksiyon"]), use_container_width=True, height=650)

                with tab3:
                    # En yuksek breakout skoru: direnc kiran, hacim destekli hisseler
                    b = df.sort_values(by=["Breakout Skor", "Kalite"], ascending=False)
                    st.dataframe(b.style.map(signal_style, subset=["Sinyal"]).map(action_style, subset=["Aksiyon"]), use_container_width=True, height=650)

                with tab4:
                    # En yuksek momentum: MACD genisleme + ROC + RSI boga bolgesi
                    m = df.sort_values(by=["Momentum Skor", "Kalite"], ascending=False)
                    st.dataframe(m.style.map(signal_style, subset=["Sinyal"]).map(action_style, subset=["Aksiyon"]), use_container_width=True, height=650)
                    
                with tab5:
                    # Hacim patlaması en yüksekten en düşüğe (Hacim Spike >= 2.0 olanlar)
                    v = df[df["Hacim Spike"] >= 2.0].sort_values(by=["Hacim Spike", "Kalite"], ascending=[False, False])
                    if v.empty:
                        st.info("Şu an 2x ve üzeri hacim patlaması yaşayan hisse bulunmuyor.")
                    else:
                        st.dataframe(v.style.map(signal_style, subset=["Sinyal"]).map(action_style, subset=["Aksiyon"]), use_container_width=True, height=650)
                        
                with tab6:
                    # Bollinger daralması (Squeeze) algoritmik şartını geçenler (Son 50 mumluk %20'lik sıkışma)
                    s = df[df["Daralma (Squeeze)"] == "🗜 İzlenir"].sort_values(by=["Bollinger Genisligi", "Kalite"], ascending=[True, False])
                    if s.empty:
                        st.info("Şu an Bollinger bantları yeterince daralan (VCP - Squeeze Modunda olan) hisse bulunmuyor.")
                    else:
                        st.dataframe(s.style.map(signal_style, subset=["Sinyal"]).map(action_style, subset=["Aksiyon"]), use_container_width=True, height=650)

        if errs:
            with st.expander("Veri Hatalari"):
                for e in errs[:200]:
                    st.error(e)

    with main_tab2:
        st.markdown("Seçtiğiniz hissenin geçmiş **1500 mumluk verisi** üzerinden, sıfırdan sisteme dahil olup **'AL'** sinyali oluştuğunda paranın tamamıyla işlem yapılır. Kâr alma seviyesi **4.0x ATR**, zarar durdurma (Stop) seviyesi **2.0x ATR** olarak ve **15 mum luk zaman kısıtı / EMA20 kırılım şartlarıyla** (Trend Takip Modu) otomatik çalışır.")
        
        b1, b2, b3 = st.columns(3)
        with b1:
            # Seçili hisseyi (varsa) otomatik olarak input'a aktar
            default_sym = st.session_state.get("selected_ticker", "NVDA")
            bt_sym = st.text_input("Test Edilecek Hisse", default_sym).upper()
        with b2:
            bt_tf = st.selectbox("Zaman Dilimi", list(TIMEFRAME_OPTIONS.keys()), index=1, key="bt_tf_selectbox")
        with b3:
            bt_capital = st.number_input("Başlangıç Sermayesi ($)", value=10000)
            
        if st.button("Simülasyonu Başlat", type="primary", key="bt_run"):
            trades_df, stats, base_df, vbt_portfolio = run_backtest(bt_sym, st.session_state.piyasa, bt_tf, bt_capital)
            
            if not trades_df.empty:
                st.subheader(f"📊 Performans Özeti: {bt_sym} ({bt_tf})")
                k1, k2, k3, k4 = st.columns(4)
                
                p_color = "normal" if stats['Toplam Getiri (%)'] >= 0 else "inverse"
                
                k1.metric("Final Bakiye", f"${stats['Final Bakiye ($)']}", f"%{stats['Toplam Getiri (%)']}", delta_color=p_color)
                k2.metric("Toplam İşlem", stats['Toplam İşlem'])
                k3.metric("Kazanma Oranı", f"%{stats['Kazanma Oranı (%)']}")
                k4.metric("K/Z İşlemler", f"{stats['Kazançlı İşlem']} / {stats['Zararlı İşlem']}")
                
                st.divider()
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Profit Factor", stats['Profit Factor'])
                m2.metric("Ort Kazanç/Zarar", f"${stats['Ortalama Kazanç ($)']} / ${stats['Ortalama Zarar ($)']}")
                m3.metric("Max Drawdown", f"%{stats['Max Drawdown (%)']}")
                m4.metric("Expectancy", f"${stats['Expectancy ($)']}")
                
                st.divider()
                
                st.subheader("📈 Profesyonel Portföy Grafiği (VectorBT)")
                if vbt_portfolio is not None:
                    fig = vbt_portfolio.plot()
                    fig.update_layout(template="plotly_dark", height=500, margin=dict(t=30, b=30, l=30, r=30), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.subheader("📉 Drawdown (Maksimum Kayıp) Analizi")
                    fig_dd = vbt_portfolio.plot_underwater()
                    fig_dd.update_layout(template="plotly_dark", height=300, margin=dict(t=30, b=30, l=30, r=30), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_dd, use_container_width=True)
                else:
                    st.line_chart(base_df["close"], use_container_width=True)
                
                c_macd, c_rsi = st.columns(2)
                with c_macd:
                    st.caption("MACD Histogramı")
                    st.bar_chart(base_df["macd_hist"], use_container_width=True)
                with c_rsi:
                    st.caption("RSI (Göreceli Güç Endeksi)")
                    st.line_chart(base_df["rsi"], use_container_width=True)
                
                st.subheader("📝 İşlem Geçmişi (Son İşlemler Üstte)")
                st.dataframe(trades_df.iloc[::-1], use_container_width=True)
                
            elif stats:
                st.warning("Bu hisse ve zaman dilimi için geçmiş tarihte uygulamanın kriterlerine uyan bir AL sinyali oluşmamıştır.")

            # --- YENİ EKLENTİ: TEMEL ANALİZ (YFINANCE) ---
            st.divider()
            st.subheader(f"🏢 {bt_sym} Şirket Temel Analizi")
            
            # FIX: Market string karışıklığı düzeltildi
            yf_ticker = f"{bt_sym}.IS" if st.session_state.piyasa == "BIST" else bt_sym
            
            with st.spinner("Şirket temel analizi ve bilançosu yükleniyor..."):
                yf_data = fetch_yf_data(yf_ticker, st.session_state.piyasa)
                
                if yf_data.get("error"):
                    err_msg = yf_data["error"]
                    if "Too Many Requests" in err_msg or "Rate limited" in err_msg or "429" in err_msg:
                        st.error("⚠️ Yahoo Finance veri limitine ulaşıldı (Çok fazla sık istek atıldı). Lütfen 10-15 dakika bekledikten sonra tekrar deneyiniz.")
                    else:
                        st.error(f"Finasal veri çekilirken /yfinance/ bir hata oluştu: {err_msg}")
                else:
                    info = yf_data["info"]
                    
                    # Sütunlar: 1. Şirket Özeti | 2. Önemli Çarpanlar
                    col_info, col_ratios = st.columns(2)
                    
                    with col_info:
                        st.markdown("#### 📌 Genel Bilgiler")
                        st.markdown(f"**Şirket Adı:** {info.get('longName', 'Bilinmiyor')}")
                        st.markdown(f"**Sektör/Endüstri:** {info.get('sector', 'Bilinmiyor')} / {info.get('industry', 'Bilinmiyor')}")
                        
                        market_cap = info.get('marketCap', 0)
                        if market_cap > 0:
                            mc_text = f"{market_cap / 1e9:.2f} Milyar"
                            st.markdown(f"**Piyasa Değeri:** {mc_text}")
                        else:
                            st.markdown("**Piyasa Değeri:** Bilinmiyor")
                            
                        st.markdown(f"**Çalışan Sayısı:** {info.get('fullTimeEmployees', 'Bilinmiyor')}")
                        
                    with col_ratios:
                        st.markdown("#### 🧮 Önemli Çarpanlar")
                        st.markdown(f"**F/K Oranı (P/E):** {info.get('trailingPE', 'Hesaplanamadı / Zarar')}")
                        st.markdown(f"**P/D Oranı (P/B):** {info.get('priceToBook', 'Bilinmiyor')}")
                        
                        div = info.get('dividendYield', None)
                        st.markdown(f"**Temettü Verimliliği:** %{round(div*100, 2) if div else 'Yok'}")
                        st.markdown(f"**Hisse Başına Kazanç (EPS):** {info.get('trailingEps', 'Bilinmiyor')}")
                        
                    # Alt Sekmeler: Gelir Tablosu - Bilanço - Nakit Akışı
                    st.markdown("#### 📊 Finansal Tablolar (Son 4 Dönem)")
                    ftab1, ftab2, ftab3 = st.tabs(["Gelir Tablosu", "Bilanço", "Nakit Akış Tablosu"])
                    
                    with ftab1:
                        gelir = yf_data["financials"]
                        if gelir is not None and not gelir.empty:
                            # Tablonun yönünü çevir (Transpoze) - Sütun isimlerinden saat kısımlarını at
                            gelir.columns = [str(c).split(" ")[0] for c in gelir.columns] 
                            st.dataframe(gelir.head(15), use_container_width=True)
                        else:
                            st.info("Gelir tablosu verisi bulunamadı.")
                            
                    with ftab2:
                        bilanco = yf_data["balance"]
                        if bilanco is not None and not bilanco.empty:
                            bilanco.columns = [str(c).split(" ")[0] for c in bilanco.columns] 
                            st.dataframe(bilanco.head(15), use_container_width=True)
                        else:
                            st.info("Bilanço verisi bulunamadı.")
                            
                    with ftab3:
                        nakit = yf_data["cashflow"]
                        if nakit is not None and not nakit.empty:
                            nakit.columns = [str(c).split(" ")[0] for c in nakit.columns]
                            st.dataframe(nakit.head(15), use_container_width=True)
                        else:
                            st.info("Nakit akış verisi bulunamadı.")

# init_gui define and call
if __name__ == "__main__":
    init_gui()


def inject_custom_css():
    st.markdown("""
    <style>
    /* Metric Cards (Kutucuklar) */
    div[data-testid="metric-container"] {
        background-color: #1a1c24;
        border: 1px solid #2d303e;
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
        border-color: #3b82f6;
    }
    /* Metric Yazıları */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700;
        color: #f3f4f6;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.95rem;
        color: #9ca3af;
        font-weight: 500;
        margin-bottom: 0.25rem;
    }
    /* Gradient Buton Tasarımı */
    .stButton>button {
        background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
        color: white;
        font-weight: 600;
        border: none;
        border-radius: 0.5rem;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        box-shadow: 0 0 15px rgba(59, 130, 246, 0.5);
        border: none;
    }
    /* Tab Menüleri */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e212b;
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        color: #d1d5db;
        border: 1px solid #374151;
        border-bottom: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: white !important;
        border-color: #2563eb !important;
    }
    /* Başlık */
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #60a5fa, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0rem;
    }
    /* Sidebar Header */
    [data-testid="stSidebar"] {
        background-color: #0f111a;
        border-right: 1px solid #1f2335;
    }
    </style>
    """, unsafe_allow_html=True)

    # init_gui() fonksiyonu içinde çağrılıyor.
    pass

# inject_custom_css() # Globalden kaldırıldı

# init_gui() fonksiyonu UI kodlarını kapsayacak şekilde aşağıda tanımlanacak.

DEFAULT_NASDAQ_HISSELER = [
    # === NASDAQ Top & Popular Hisseler ===
    "AAPL", "MSFT", "GOOG", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "PEP",
    "COST", "CSCO", "TMUS", "ADBE", "TXN", "QCOM", "AMGN", "INTU", "ISRG", "CMCSA",
    "AMD", "HON", "NFLX", "SBUX", "GILD", "BKNG", "AMAT", "ADI", "MDLZ", "VRTX",
    "REGN", "PANW", "MU", "MELI", "SNPS", "CDNS", "KLAC", "CSX", "PYPL", "MAR",
    "ASML", "ORLY", "MNST", "WBD", "LULU", "CRWD", "FTNT", "KDP", "CHTR", "CTAS",
    "DXCM", "ABNB", "WDAY", "ODFL", "ROST", "KHC", "PAYX", "IDXX", "BIIB", "AEP",
    "CPRT", "MRVL", "EA", "PCAR", "ILMN", "FAST", "VRSK", "CEG", "EXC", "DLTR",
    "VRSN", "ALGN", "WBA", "BKR", "BMRN", "SWKS", "CDW", "TSCO", "SIRI", "ZM",
    "CRSP", "DOCU", "PLTR", "RIVN", "LCID", "COIN", "U", "DKNG", "HOOD", "AFRM",
    "JD", "PDD", "BIDU", "NTES", "BABA", "TCEHY", "NIO", "XPEV", "LI",
    # Eklenen Popüler Hisseler (AI, Yarı İletken & Enerji)
    "SMCI", "ARM", "MSTR", "TGT", "WMT", "JPM", "BAC", "GS", "MS", "CVX", "XOM", "UNH",
    "LLY", "V", "MA", "ABBV", "KO", "PFE", "DIS", "NKE", "VZ", "T", "BA", "CAT",
    "IBM", "ORCL", "CRM", "INTC", "UBER", "ABNB", "SHOP", "SQ", "SE", "SNAP", "DASH"
]

DEFAULT_BIST_HISSELER = [
    "A1CAP", "ACSEL", "ADEL", "ADESE", "AEFES", "AFYON", "AGESA", "AGHOL", "AGROT", "AHGAZ", "AKBNK", "AKCNS",
    "AKENR", "AKFGY", "AKFYE", "AKGRT", "AKMGY", "AKSA", "AKSEN", "AKSGY", "AKSUE", "AKYHO", "ALARK", "ALBRK",
    "ALCAR", "ALCTL", "ALFAS", "ALGYO", "ALKA", "ALKIM", "ALMAD", "ALTNY", "ALVES", "ANELE", "ANGEN", "ANHYT",
    "ANSGR", "ARASE", "ARCLK", "ARDYZ", "ARENA", "ARSAN", "ARTMS", "ARZUM", "ASELS", "ASGYO", "ASTOR", "ASUZU",
    "ATAGY", "ATAKP", "ATATP", "ATEKS", "ATLAS", "ATSYH", "AVGYO", "AVHOL", "AVOD", "AVTUR", "AYCES", "AYDEM",
    "AYEN", "AYES", "AYGAZ", "AZTEK", "BAGFS", "BAKAB", "BALAT", "BANVT", "BARMA", "BASGZ", "BAYRK", "BEAYO",
    "BERA", "BEYAZ", "BFREN", "BGYO", "BIENY", "BIGCH", "BIMAS", "BINHO", "BIOEN", "BIZIM", "BJKAS", "BLCYT",
    "BMSCH", "BMSTL", "BNTAS", "BOBET", "BOSSA", "BOYNER", "BRIS", "BRKO", "BRKSN", "BRKVY", "BRLSM", "BRMEN",
    "BRSAN", "BRYAT", "BTCIM", "BUCIM", "BURCE", "BURVA", "BVSAN", "BYDNR", "CANTE", "CASA", "CATES", "CCOLA",
    "CELHA", "CEMAS", "CEMTS", "CEOEM", "CMENT", "CONSE", "CORBS", "COSMO", "CRDFA", "CRFSA", "CUSAN", "CVKMD",
    "CWENE", "DAGHL", "DAGI", "DAPGM", "DARDL", "DERHL", "DERIM", "DESA", "DESPC", "DEVA", "DGATE", "DGGYO",
    "DGNMO", "DIRIT", "DITAS", "DMRGD", "DMSAS", "DOAS", "DOBUR", "DOCO", "DOGUB", "DOHOL", "DOKTA", "DURDO",
    "DYOBY", "DZGYO", "EBEBK", "ECILC", "ECZYT", "EDATA", "EDIP", "EGEEN", "EGGUB", "EGPRO", "EGSER", "EKGYO",
    "EKIZ", "EKOS", "EKSUN", "ELITE", "EMKEL", "ENJSA", "ENKAI", "ENSRI", "ENTRA", "EPLAS", "ERBOS", "ERCB",
    "EREGL", "ERSU", "ESCAR", "ESCOM", "ESEN", "ETILR", "EUHOL", "EUKYO", "EUPWR", "EUREN", "EUYO", "EYGYO",
    "FADE", "FASIL", "FENER", "FLAP", "FMIZP", "FONET", "FORMT", "FORTE", "FRIGO", "FROTO", "FZLGY", "GARAN",
    "GARFA", "GEDIK", "GEDZA", "GENIL", "GENTS", "GEREL", "GESAN", "GIPTA", "GLBMD", "GLCVY", "GLRYH", "GLYHO",
    "GMTAS", "GOKNR", "GOLTS", "GOODY", "GOZDE", "GRNYO", "GRSEL", "GSDDE", "GSDHO", "GSRAY", "GUBRF", "GWIND",
    "HALKB", "HATEK", "HATSN", "HDFGS", "HEDEF", "HEKTS", "HKTM", "HLGYO", "HTTBT", "HUBVC", "HUNER", "HURGZ",
    "ICBCT", "ICUGS", "IDGYO", "IEYHO", "IHAAS", "IHLAS", "IHLGM", "IHYAY", "IMASM", "INDES", "INFO", "INGRM",
    "INTEM", "INVEO", "INVES", "IPEKE", "ISATR", "ISBIR", "ISBTR", "ISCTR", "ISDMR", "ISFIN", "ISGSY", "ISGYO",
    "ISKPL", "ISKUR", "ISMEN", "ISSEN", "ISYAT", "ITTFH", "IZENR", "IZFAS", "IZINV", "IZMDC", "JANTS", "KAPLM",
    "KAREL", "KARSN", "KARTN", "KARYE", "KATMR", "KAYSE", "KCAER", "KCHOL", "KENT", "KERVN", "KERVT", "KFEIN",
    "KGYO", "KIMMR", "KLGYO", "KLKIM", "KLMSN", "KLNMA", "KLRHO", "KLSYN", "KMPUR", "KNFRT", "KOCMT", "KONKA",
    "KONTR", "KONYA", "KOPOL", "KORDS", "KOZAA", "KOZAL", "KRDMA", "KRDMB", "KRDMD", "KRGYO", "KRONT", "KRPLS",
    "KRSTL", "KRTEK", "KRVGD", "KTSKR", "KSTUR", "KTLEV", "KUTPO", "KUYAS", "KZBGY", "KZGYO", "LIDER",
    "LINK", "LKMNH", "LMKDC", "LOGO", "LRSHO", "LUKSK", "MAALT", "MACKO", "MACRO", "MAGEN", "MAKIM", "MAKTK",
    "MANAS", "MARKA", "MARTI", "MAVI", "MAXDD", "MEDTR", "MEGAP", "MEKAG", "MEPET", "MERCN", "MERIT", "MERKO",
    "METRO", "METUR", "MGROS", "MHRGY", "MIATK", "MIPAZ", "MMCAS", "MNDRS", "MNDTR", "MOBTL", "MOGAN", "MPARK",
    "MRGYO", "MRSHL", "MSGYO", "MTRKS", "MTRYO", "MUHAL", "MUREN", "MZHLD", "NATEN", "NETAS", "NIBAS", "NTGAZ",
    "NTHOL", "NUGYO", "NUHCM", "OBASE", "OBAMG", "ODAS", "OFSYM", "ONCSM", "ORCAY", "ORGE", "ORMA", "OSMEN",
    "OSTIM", "OTKAR", "OTTO", "OYAKC", "OYAYO", "OYLUM", "OYYAT", "OZGYO", "OZKGY", "OZRDN", "OZSUB", "PAGYO",
    "PAMEL", "PAPIL", "PARSN", "PASEU", "PATEK", "PCILT", "PEGYO", "PEKGY", "PENGD", "PENTA", "PETKM", "PETUN",
    "PGSUS", "PINSU", "PKART", "PKENT", "PLTUR", "PNLSN", "PNSUT", "POLHO", "POLTK", "PRDGS", "PRKAB", "PRKME",
    "PRZMA", "PSGYO", "PSUTC", "PTFS", "QNBFB", "QNBFL", "QUAGR", "RALYH", "RAYSG", "REEDR", "RNPOL", "RODRG",
    "ROYAL", "RTALB", "RUBNS", "RYGYO", "RYSAS", "SAHOL", "SAMAT", "SANEL", "SANFM", "SANKO", "SARKY", "SASA",
    "SAYAS", "SDTTR", "SEGYO", "SEKFK", "SEKUR", "SELEC", "SELGD", "SELVA", "SEYKM", "SILVR", "SINKO", "SNGYO",
    "SNICA", "SNKRN", "SNPAM", "SOKE", "SOKM", "SONME", "SRVGY", "SUMAS", "SUNTK", "SURGY", "SUWEN", "TABGD",
    "TARKM", "TATEN", "TATGD", "TAVHL", "TBORG", "TCELL", "TDGYO", "TEKTU", "TERA", "TETMT", "TEZOL", "TGSAS",
    "THYAO", "TKFEN", "TKNSA", "TLMAN", "TMPOL", "TMSN", "TOASO", "TRCAS", "TRGYO", "TRILC", "TSGYO", "TSKB",
    "TSPOR", "TTKOM", "TTRAK", "TUCLK", "TUKAS", "TUPRS", "TUREX", "TURGG", "TURSG", "UFUK", "ULAS", "ULKER",
    "ULUFA", "ULUSE", "ULUUN", "UMPAS", "UNLU", "USAK", "UZERB", "VAKBN", "VAKFN", "VAKKO", "VANGD", "VBTYZ",
    "VERTU", "VERUS", "VESBE", "VESTL", "VKFYO", "VKGYO", "VKING", "VRGYO", "YAPRK", "YATAS", "YAYLA", "YBTAS",
    "YEOTK", "YESIL", "YGGYO", "YGYO", "YIPLA", "YKBNK", "YKGYO", "YKSLN", "YONGA", "YUNSA", "YYAPI", "ZEDUR",
    "ZGOLD", "ZOREN", "ZRGYO"
]

TIMEFRAME_OPTIONS = {
    "4 Saatlik": {"base": "4h", "confirm": "1d", "bars": 500, "confirm_bars": 300},
    "Gunluk": {"base": "1d", "confirm": "1w", "bars": 300, "confirm_bars": 200},
    "Haftalik": {"base": "1w", "confirm": "1d", "bars": 220, "confirm_bars": 300},
    "Gunluk + Haftalik": {"base": "1d", "confirm": "1w", "bars": 300, "confirm_bars": 220, "multi": True},
}


def uniq(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    return out.dropna(subset=["open", "high", "low", "close"])





import numba as nb

@nb.njit
def _ut_bot_numba(close_arr: np.ndarray, loss_arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(close_arr)
    out_stop = np.zeros(n)
    out_pos = np.zeros(n, dtype=nb.int64)
    buy = np.zeros(n, dtype=nb.boolean)
    sell = np.zeros(n, dtype=nb.boolean)
    
    # FIX: İlk bar'ı initialize et
    out_stop[0] = close_arr[0]
    out_pos[0] = 1 if close_arr[0] > close_arr[0] else -1  # Başlangıçta nötr
    
    for i in range(1, n):
        src = close_arr[i]
        src_1 = close_arr[i-1]
        loss = loss_arr[i] if not np.isnan(loss_arr[i]) else 0.0
        prev_stop = out_stop[i-1]
        
        if src > prev_stop and src_1 > prev_stop:
            out_stop[i] = max(prev_stop, src - loss)
        elif src < prev_stop and src_1 < prev_stop:
            out_stop[i] = min(prev_stop, src + loss)
        elif src > prev_stop:
            out_stop[i] = src - loss
        else:
            out_stop[i] = src + loss
            
        prev_pos = out_pos[i-1]
        if src_1 < prev_stop and src > prev_stop:
            out_pos[i] = 1
        elif src_1 > prev_stop and src < prev_stop:
            out_pos[i] = -1
        else:
            out_pos[i] = prev_pos
            
        if src > out_stop[i] and src_1 <= prev_stop:
            buy[i] = True
        elif src < out_stop[i] and src_1 >= prev_stop:
            sell[i] = True
            
    return buy, sell, out_pos

def compute_ut_bot(close: pd.Series, high: pd.Series, low: pd.Series, a: float = 1.0, c: int = 10) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    UT Bot Alerts (QuantNomad) indikatörünün Pandas karsiligi.
    a: Key Value (Duyarlilik/Hassasiyet carpani, varsayilan = 1.0)
    c: ATR periyodu (Varsayilan = 10)
    """
    import ta
    xATR = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=c, fillna=True).average_true_range()
    nLoss = a * xATR
    
    close_arr = close.to_numpy()
    loss_arr = nLoss.to_numpy()
    
    buy, sell, out_pos = _ut_bot_numba(close_arr, loss_arr)
            
    return pd.Series(buy, index=close.index), pd.Series(sell, index=close.index), pd.Series(out_pos, index=close.index)


@st.cache_data(ttl=1800)
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    import ta
    out = normalize(df)
    
    out["ema20"] = ta.trend.EMAIndicator(close=out["close"], window=20, fillna=True).ema_indicator()
    out["ema50"] = ta.trend.EMAIndicator(close=out["close"], window=50, fillna=True).ema_indicator()
    out["sma20"] = ta.trend.SMAIndicator(close=out["close"], window=20, fillna=True).sma_indicator()
    out["sma50"] = ta.trend.SMAIndicator(close=out["close"], window=50, fillna=True).sma_indicator()
    out["sma200"] = ta.trend.SMAIndicator(close=out["close"], window=200, fillna=True).sma_indicator()
    out["gap_pct"] = ((out["open"] - out["close"].shift(1)) / out["close"].shift(1).replace(0, math.nan)) * 100
    
    out["rsi"] = ta.momentum.RSIIndicator(close=out["close"], window=14, fillna=True).rsi()
    
    macd_obj = ta.trend.MACD(close=out["close"], window_slow=26, window_fast=12, window_sign=9, fillna=True)
    out["macd"] = macd_obj.macd()
    out["macd_sig"] = macd_obj.macd_signal()
    out["macd_hist"] = macd_obj.macd_diff()
    
    atr_obj = ta.volatility.AverageTrueRange(high=out["high"], low=out["low"], close=out["close"], window=14, fillna=True)
    out["atr"] = atr_obj.average_true_range()
    out["atr_pct"] = (out["atr"] / out["close"].replace(0, math.nan)) * 100
    
    adx_obj = ta.trend.ADXIndicator(high=out["high"], low=out["low"], close=out["close"], window=14, fillna=True)
    out["adx"] = adx_obj.adx()
    out["plus_di"] = adx_obj.adx_pos()
    out["minus_di"] = adx_obj.adx_neg()
    
    out["vol_ma20"] = ta.trend.SMAIndicator(close=out["volume"], window=20, fillna=True).sma_indicator()
    out["vol_spike"] = out["volume"] / out["vol_ma20"].replace(0, math.nan)
    out["support_120"] = out["low"].rolling(120).min()
    # Kisa vadeli direnc (20 bar), orta vade (60 bar) ve 52-haftalik direnc (260 bar)
    out["res_20"]  = out["high"].shift(1).rolling(20).max()
    out["res_60"]  = out["high"].shift(1).rolling(60).max()
    out["res_260"] = out["high"].shift(1).rolling(260).max()
    out["breakout_up"]  = out["close"] > out["res_20"]
    out["breakout_60"]  = out["close"] > out["res_60"]
    out["breakout_52w"] = out["close"] > out["res_260"]
    # Bollinger Bantlari: fiyatin bant icindeki konumu (0=alt, 1=ust) ve Genisligi (Daralma/VCP icin)
    bb_std = out["close"].rolling(20).std()
    out["bb_lower"] = out["sma20"] - 2 * bb_std
    out["bb_upper"] = out["sma20"] + 2 * bb_std
    out["bb_width"] = ((out["bb_upper"] - out["bb_lower"]) / out["sma20"].replace(0, math.nan)) * 100
    out["bb_pct"] = (
        (out["close"] - out["bb_lower"]) /
        (out["bb_upper"] - out["bb_lower"]).replace(0, math.nan)
    ).clip(0, 1)
    
    # Bollinger Squeeze (Son 50 barın en dar %20'lik dilimine girmişse = Daralma/Sıkışma var)
    out["bb_squeeze"] = out["bb_width"] < out["bb_width"].rolling(50).quantile(0.2)
    
    # EMA20 egimi: 5 barlık yuzdelik degisim (trend gucunu olcer)
    out["ema20_slope"] = out["ema20"].pct_change(5) * 100
    # 20-bar fiyat momentum (ROC)
    out["roc20"] = out["close"].pct_change(20) * 100

    # Ekstra parametreler (Likidite & Aralık)
    out["close_vs_sma50"] = ((out["close"] - out["sma50"]) / out["sma50"].replace(0, math.nan)) * 100
    out["close_vs_sma200"] = ((out["close"] - out["sma200"]) / out["sma200"].replace(0, math.nan)) * 100
    out["range_pct"] = ((out["high"] - out["low"]) / out["close"].replace(0, math.nan)) * 100
    out["avg_turnover_20"] = out["vol_ma20"] * out["close"]  # 20 günlük Ortalama İşlem Hacmi (Lot x Fiyat)

    # Son 5 bar ardışık dip yükselterek ilerliyor mu?
    out["higher_lows_5"] = (
        (out["low"] > out["low"].shift(1)) &
        (out["low"].shift(1) > out["low"].shift(2)) &
        (out["low"].shift(2) > out["low"].shift(3)) &
        (out["low"].shift(3) > out["low"].shift(4))
    )

    # Kurumsal giriş onaylı bar (Büyük gep, dev hacim, kırılım ve pozitif kapanış)
    out["inst_bar"] = (
        (out["gap_pct"] > 1.5) &
        (out["vol_spike"] >= 1.8) &
        (out["close"] > out["open"]) &
        (out["close"] > out["res_20"])
    )

    out["ut_buy"], out["ut_sell"], out["ut_pos"] = compute_ut_bot(out["close"], out["high"], out["low"], a=1.0, c=10)

    return out


# FIX: _safe_get() KeyError handling düzelt
def _safe_get(s: pd.Series, key: str, default: object = None):
    try:
        val = s[key]
        return val if pd.notna(val) else default
    except (KeyError, TypeError):
        return default

def score_symbol(last: pd.Series, prev: pd.Series, conf_last: pd.Series, market: str = "NASDAQ") -> Dict[str, object]:
    mtf_ok    = bool(_safe_get(conf_last, "ema20", 0) > _safe_get(conf_last, "ema50", 0) and _safe_get(conf_last, "macd_hist", 0) > 0)
    regime_ok = bool((_safe_get(last, "adx", 0) >= 18) and (1.0 <= _safe_get(last, "atr_pct", 0) <= 9.0))

    vol_spike_val = float(_safe_get(last, "vol_spike", 0.0))
    ema20_slope   = float(_safe_get(last, "ema20_slope", 0.0))
    roc20         = float(_safe_get(last, "roc20", 0.0))
    bb_pct        = float(_safe_get(last, "bb_pct", 0.5))
    rsi_val       = float(_safe_get(last, "rsi", 50.0))
    adx_val       = float(_safe_get(last, "adx", 0.0))
    atr_pct_val   = float(_safe_get(last, "atr_pct", 5.0))
    macd_curr     = float(_safe_get(last, "macd_hist", 0.0))
    macd_prev     = float(_safe_get(prev, "macd_hist", 0.0))
    prev_rsi      = float(_safe_get(prev, "rsi", 50.0))
    
    b52w          = bool(_safe_get(last, "breakout_52w", False))
    breakout_60   = bool(_safe_get(last, "breakout_60", False))
    inst_bar      = bool(_safe_get(last, "inst_bar", False))
    ut_buy        = bool(_safe_get(last, "ut_buy", False))
    ut_pos        = int(_safe_get(last, "ut_pos", 0))
    
    bb_width_val  = float(_safe_get(last, "bb_width", 10.0))
    gap_pct_val   = float(_safe_get(last, "gap_pct", 0.0))
    sma50_val     = float(_safe_get(last, "sma50", 0.0))
    sma200_val    = float(_safe_get(last, "sma200", 0.0))
    close_val     = float(_safe_get(last, "close", 0.0))
    
    # "Almış başını gitmiş" hisseleri tespit etmek için ortalamadan uzaklık
    ema20_val     = float(_safe_get(last, "ema20", 0.0))
    ema20_dist    = ((close_val - ema20_val) / ema20_val) * 100 if ema20_val > 0 else 0.0

    # Kesin Crossover ve Sıçrama Yakalayıcılar (Sniper Filtreleri)
    bb_lower_curr = float(_safe_get(last, "bb_lower", 0.0))
    bb_lower_prev = float(_safe_get(prev, "bb_lower", 0.0))
    prev_close    = float(_safe_get(prev, "close", 0.0))
    sma20_val     = float(_safe_get(last, "sma20", 0.0))
    avg_turnover  = float(_safe_get(last, "avg_turnover_20", 0.0))
    
    # Günlük Getiri (Tavan / Taban kontrolü için)
    daily_return = ((close_val - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0

    macd_cross_up  = (macd_curr > 0) and (macd_prev <= 0)
    bb_lower_cross = (close_val > bb_lower_curr) and (prev_close <= bb_lower_prev)
    
    # ── LİKİDİTE KONTROLÜ (Sığ Hisseler Risk Yaratır) ──
    # BIST'te en az 30-50 milyon TL civarı günlük hacim aranmalı (Örnek olarak 30M alıyoruz)
    # Market varsayımı üzerinden kabaca likidite sınır değerini belirliyoruz.
    min_liquidity = 30_000_000 if market == "BIST" else 5_000_000  # ABD için zaten lot*fiyat çok büyük olur.
    is_liquid = avg_turnover >= min_liquidity

    # ── TREND SKORU (max ~99) ──────────────────────────────────────────────────
    trend = 0.0
    trend += 20 if ema20_val > sma50_val else 0            # Altin kesisim bolgesi (kısa vade)
    trend += 10 if close_val > sma20_val else 0            # Fiyat kisa ortalama ustunde
    trend += 8  if macd_curr > 0 else 0                    # MACD pozitif
    trend += 8  if mtf_ok else 0                            # Ust zaman dilimi teyidi
    trend += 6  if ema20_slope > 0.5 else 0                # EMA20 belirgin yukari egim (>%0.5/5bar)
    # Kurumsal Trend Filtreleri
    trend += 15 if (sma200_val > 0 and close_val > sma200_val) else 0    # Fiyat 200 Gunluk Ortalama ustu
    trend += 10 if (sma50_val > 0 and sma200_val > 0 and sma50_val > sma200_val) else 0 # Uzun Vade Golden Cross
    trend += 10 if (sma50_val > 0 and close_val > sma50_val) else 0      # Fiyat 50 Gunluk Ortalama ustu

    # ── GÜÇLÜ DİP AVCISI (BOTTOM HUNTER) SKORU (Max: 100) ────────────────────
    support_120_val = float(_safe_get(last, "support_120", 0.0))
    ema20_prev = float(_safe_get(prev, "ema20", 0.0))
    
    is_rsi_oversold = rsi_val <= 30
    is_rsi_rising = (rsi_val > prev_rsi) and (rsi_val < 50)
    is_price_above_ma20 = (close_val > ema20_val) and (prev_close <= ema20_prev)
    is_near_bottom = (support_120_val > 0) and (((close_val - support_120_val) / support_120_val) * 100 <= 6.0)
    is_volume_up = (vol_spike_val >= 1.5)

    dip = 0.0
    dip += 20 if is_rsi_oversold else 0                            # RSI Oversold (< 30) - Hisse çok satılı
    dip += 15 if is_rsi_rising else 0                              # RSI Yükselişe Geçti
    dip += 25 if macd_cross_up else 0                              # MACD Crossover - Momentum değişimi
    dip += 15 if is_price_above_ma20 else 0                        # Fiyat MA20 Üstünde
    dip += 20 if is_near_bottom else 0                             # Dip Seviyesi - Tarihi desteğe yakınlık
    dip += 5 if is_volume_up else 0                                # Hacim Artışı - Alıcı ilgisi
    
    dip_signals = []
    if is_rsi_oversold: dip_signals.append("✓ RSI < 30")
    if is_rsi_rising: dip_signals.append("✓ RSI Yükseliyor")
    if macd_cross_up: dip_signals.append("✓ MACD Kesti")
    if is_price_above_ma20: dip_signals.append("✓ MA20 Kırıldı")
    if is_near_bottom: dip_signals.append("✓ Son Dönem Dibi")
    if is_volume_up: dip_signals.append("✓ Hacim Patladı")
    
    dip_signal_str = " | ".join(dip_signals) if dip_signals else "-"
    is_solid_bottom = dip >= 40  # >= 40 puan bir satın alma fırsatı / Özel durum yaratır.

    # ── BREAKOUT SKORU (max ~97) ──────────────────────────────────────────────
    breakout_up = bool(_safe_get(last, "breakout_up", False))
    
    breakout = 0.0
    breakout += 18 if breakout_up else 0                   # 20-bar yerel direnc kirisi
    breakout += 15 if (breakout_up and bb_width_val < 8.0) else 0 # VCP (Daralma): Sıkışık banttan taze kırılım!
    breakout += 12 if b52w else 0                           # 52-haftalik zirve kirisi (guclu sinyal!)
    breakout += 15 if breakout_60 else 0
    breakout += 12 if gap_pct_val > 2.0 else 0 
    breakout +=  8 if mtf_ok else 0                        # MTF teyidi

    # ── MOMENTUM SKORU (max ~79) — eski "Tavan" yerine duzgun momentum olcumu ─
    momentum = 0.0
    momentum += 25 if macd_cross_up else 0                                  # MACD TAM BUGUN YUKARI KESTI (Taze Momentum)
    momentum += 16 if (macd_curr > 0 and macd_curr > macd_prev) else 0      # MACD histogrami genisliyor
    momentum += 10 if (50 <= rsi_val <= 70) else 0                           # Boga bolgesi, asiri alimda degil
    momentum +=  8 if mtf_ok else 0                                          # Ust TF trendi destekliyor
    momentum +=  8 if roc20 > 3.0 else 0                                     # 20 barda fiyat >%3 artti

    trend    = clamp(trend)
    dip      = clamp(dip)
    breakout = clamp(breakout)
    momentum = clamp(momentum)

    # ── SMART MONEY SKORU ──
    smart_money = 0.0
    smart_money += 20 if inst_bar else 0
    smart_money += 20 if ut_buy else 0  # UT Bot'un milimetrik YESIL'e dondugu an
    smart_money += 15 if (vol_spike_val >= 2.0) else 0
    smart_money += 10 if (vol_spike_val >= 1.5) else 0
    smart_money += 10 if _safe_get(last, "higher_lows_5", False) else 0
    smart_money += 10 if adx_val >= 20 else 0
    smart_money = clamp(smart_money)

    # ── MARKET REGIME ADAPTATION (Trend vs Choppy) ──
    market_regime = "TREND" if adx_val >= 20 else "CHOP"
    
    # Swing trader (Kısa Vade/Hız) odaklı yeni ağırlıklar
    if market_regime == "TREND":
        # Trend varsa Momentum ve Breakout candır
        w_trend, w_dip, w_breakout, w_momentum, w_sm = 0.15, 0.05, 0.30, 0.30, 0.20
    else: 
        # Testere piyasasıysa Dip ve Smart Money (Kurumsal alım) candır
        w_trend, w_dip, w_breakout, w_momentum, w_sm = 0.10, 0.35, 0.15, 0.20, 0.20

    general  = clamp((trend * w_trend) + (dip * w_dip) + (breakout * w_breakout) + (momentum * w_momentum) + (smart_money * w_sm))

    # ── RISK SKORU (dusuk = iyi) ──
    risk = 15.0
    risk += 15 if not regime_ok else 0        # Rejim uygunsuz (ADX veya ATR bant disi)
    
    # ALMIŞ BAŞINI GİTMİŞ HİSSE CEZALARI
    risk += 25 if ema20_dist > 15.0 else 0    
    risk += 15 if ema20_dist > 8.0 else 0     
    risk += 20 if rsi_val > 70 else 0         
    
    # GÜNLÜK TAVAN/TABAN RİSKİ
    risk += 30 if daily_return > 8.0 else 0   
    risk += 15 if daily_return > 6.0 and daily_return <= 8.0 else 0 
    risk += 35 if daily_return < -4.0 else 0  
    risk += 15 if daily_return < -2.5 and daily_return >= -4.0 else 0
    
    risk +=  8 if atr_pct_val > 7.0 else 0   
    risk +=  8 if adx_val < 15 else 0         
    risk += 15 if (sma200_val > 0 and close_val < sma200_val) else 0 
    
    # LİKİDİTE RİSKİ
    risk += 35 if not is_liquid else 0
    
    # HACİMSİZ GAP-UP RİSKİ (Boşluk var ama hacim yoksa tuzak olabilir)
    risk += 40 if gap_pct_val > 2.0 and vol_spike_val < 1.0 else 0
    
    # PUMP & DUMP FİLTRESİ
    is_pump_dump = (rsi_val > 75) and (macd_curr < macd_prev) and (daily_return > 3.0)
    risk += 50 if is_pump_dump else 0

    risk += 10 if gap_pct_val < -2.0 else 0   
    risk = clamp(risk)

    # ── GUVEN SKORU ───────────────────────────────────────────────────────────
    confidence = clamp(
        20
        + (20 if mtf_ok else 0)             # Ust TF onayladiysa guclu katki
        + (18 if regime_ok else 0)           # Rejim uygun (ADX + volatilite)
        + (15 if ema20_slope > 0 else 0)    # EMA20 yukari yonlu egim
    )

    ut_recent = ut_buy or bool(prev.get("ut_buy", False))
    ut_long   = (ut_pos == 1)

    if market == "NASDAQ":
        buy_general = 35
        buy_conf = 45
        buy_risk = 55
        buy_sm = 0   # Smart money artık opsiyonel bonus
    else:  # BIST
        buy_general = 30
        buy_conf = 40
        buy_risk = 60
        buy_sm = 0

    # ── SİNYAL ESIKLERI ───────────────────────────────────────────────────────
    # AL SİNYALİ İÇİN 3 FARKLI YAKLAŞIM:
    
    # 1. Taze Sinyal (Erken Giriş): UT Bot henüz AL vermişse biraz daha esnek gir
    is_fresh_buy = ut_recent and general >= (buy_general * 0.8) and risk <= buy_risk
    
    # 2. Dip Avcısı (Bottom Fishing): Dip puanı tavan yapmışsa (Oversold dönüşü)
    is_bottom_buy = is_solid_bottom and risk <= (buy_risk + 10)
    
    # 3. Güçlü Trend (Trend Following): Halihazırda trenddeyse genel skorları sağlam olmalı
    is_trend_buy = ut_long and general >= buy_general and confidence >= buy_conf and smart_money >= buy_sm and risk <= buy_risk

    if is_fresh_buy:
        signal = "AL"
        action = "AL (Erken Fırsat)"
    elif is_bottom_buy:
        signal = "AL"
        action = "AL (Dip Avcısı)"
    elif is_trend_buy:
        signal = "AL"
        action = "AL (Güçlü Trend)"
    elif ut_long and general >= 20 and risk <= 65:
        signal = "BEKLE"
        action = "Trend Sürüyor"
    elif general >= 15 and risk <= 60:
        signal = "BEKLE"
        action = "Onay Bekliyor"
    else:
        signal = "SAT"
        action = "Zayıf Görünüm"

    # ── GIRIS / STOP / HEDEF (Gelişmiş Trend Takibi İçin Güncellendi) ──────
    atr_val = float(_safe_get(last, "atr", 0.0))
    stop    = max(0.0, close_val - (2.0 * atr_val)) # Stop mesafesi nefes alması için 2.0 ATR'ye çekildi
    target  = close_val + (4.0 * atr_val)           # Hedef 4.0 ATR'ye çekilerek R/R > 1:2 yapıldı
    rr      = (target - close_val) / (close_val - stop) if (close_val > stop and atr_val > 0) else 0.0

    # ── KALİTE SKORU — siralama icin bilesik metrik ───────────────────────────
    # Kalite hesaplamasından "Smart Money" çifte sayımı kaldırıldı (Skor'un içerisinde yeterince etkisi var)
    # Risk katsayısı 0.40'tan 0.50'ye çekilerek riskli kağıtlar sıralamada daha da aşağı itildi.
    kalite = general - (risk * 0.50) + (confidence * 0.25)
    
    # TREN KAÇTI (OVER-EXTENDED) CEZASI
    # Eğer fiyat EMA20'den (Kısa Vade Ortalama) %12+ kopuksa veya RSI 75'i aştıysa bu hisse aşırı şişkindir.
    is_overextended = (ema20_dist > 12.0) or (rsi_val >= 75)
    if is_overextended:
        kalite *= 0.60  # Puanı %40 oranında acımasızca tırpanla
        
    kalite = clamp(kalite)

    durumlar = []
    if is_solid_bottom:
        durumlar.append("🚨 DİPTEN DÖNÜŞ (40+PUAN)")
    if is_overextended:
        durumlar.append("⚠️ AŞIRI ŞİŞKİN (Tren Kaçmış Olabilir)")
    
    ozel_durum_str = " | ".join(durumlar) if durumlar else "-"

    return {
        "Kalite":        round(kalite, 1),
        "Günlük %":      f"%{round(daily_return, 2)}",
        "Skor":          round(general, 1),
        "Smart Money Skor": round(smart_money, 1),
        "Kurumsal Giriş": "🟢 Güçlü" if smart_money >= 70 else ("🟡 İzlenir" if smart_money >= 45 else "Zayıf"),
        "Trend Skor":    round(trend, 1),
        "Dip Skor":      round(dip, 1),
        "Breakout Skor": round(breakout, 1),
        "Momentum Skor": round(momentum, 1),
        "Dusus Riski":   round(risk, 1),
        "Guven":         round(confidence, 1),
        "Sinyal":        signal,
        "Aksiyon":       action,
        "R/R":           round(rr, 2),
        "Likidite":      "✅ Uygun" if is_liquid else "🚫 Çok Sığ",
        "UT Bot":        "🟢 YESİL" if ut_pos == 1 else "🔴 KIRMIZI",
        "MACD Durumu":   "🔥 Taze Kesti" if macd_cross_up else "-",
        "Bollinger":     "🟢 Dipten Zıpladı" if bb_lower_cross else "-",
        "Kurumsal SMA200": "Üstünde" if (sma200_val > 0 and close_val > sma200_val) else ("Altında" if sma200_val > 0 else "N/A"),
        "Gap":           f"%{round(gap_pct_val, 2)}",
        "Teyit":         "Evet" if mtf_ok else "Hayir",
        "Özel Durum":    ozel_durum_str,
        "Dip Sinyalleri": dip_signal_str,
    }


def signal_style(v: str) -> str:
    if v == "AL":
        return "background-color:#dcfce7;color:#166534;font-weight:700;"
    if v == "BEKLE":
        return "background-color:#fef3c7;color:#92400e;font-weight:700;"
    return "background-color:#fee2e2;color:#991b1b;font-weight:700;"


def action_style(v: str) -> str:
    if "AL" in v:
        return "background-color:#dcfce7;color:#166534;font-weight:700;"
    return "background-color:#fef3c7;color:#92400e;font-weight:700;"


def interval_obj(key: str):
    from tvDatafeed import Interval
    mp = {"4h": Interval.in_4_hour, "1d": Interval.in_daily, "1w": Interval.in_weekly}
    return mp[key]


def fetch_hist(tv, symbol: str, exchange: str, interval, bars: int, retries: int = 3):
    """TvDatafeed'den veri ceker; basarisiz her denemede ustels geri cekilme uygular."""
    last_err: Exception = RuntimeError("bilinmeyen hata")
    for i in range(retries):
        try:
            d = tv.get_hist(symbol=symbol, exchange=exchange, interval=interval, n_bars=bars)
            if d is not None and not d.empty:
                return d
            # API cagri basarili ama bos veri dondu; aciklayici mesajla yeniden dene
            last_err = RuntimeError(f"API bos DataFrame dondu (deneme {i + 1}/{retries})")
        except Exception as e:
            # Orijinal exception tipini ve mesajini koru
            last_err = RuntimeError(f"{type(e).__name__}: {e} (deneme {i + 1}/{retries})")
        # Ustels geri cekilme: 1s, 2s, 4s + rastgele jitter
        bekleme = (1.0 * (2 ** i)) + random.uniform(0.2, 0.8)
        time.sleep(bekleme)
    raise last_err


@st.cache_resource(ttl=3600*24, show_spinner="🤖 Yapay Zeka Modeli Eğitiliyor... (İlk Taramaya Özel Bekleyiniz)")
def get_ai_model(market: str, tf_name: str, tv=None) -> tuple:
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        return None, None
        
    if tv is None:
        from tvDatafeed import TvDatafeed
        tv = TvDatafeed()
    tf = TIMEFRAME_OPTIONS[tf_name]
    
    # Hedef endeks
    sym = "QQQ" if market == "NASDAQ" else "XU100"
    
    try:
        df = fetch_hist(tv, sym, market, interval_obj(tf["base"]), 2500, retries=3)
    except Exception:
        return None, None
        
    if df is None or df.empty:
        return None, None
        
    df = add_indicators(df)
    
    # Hedef Değişken (Y): 5 Bar Sonra Fiyat %2+ Artıyor mu?
    df["target"] = (df["close"].shift(-5) > (df["close"] * 1.02)).astype(int)
    
    df["ema20_dist"] = (df["close"] - df["ema20"]) / df["ema20"] * 100
    df["sma50_dist"] = (df["close"] - df["sma50"]) / df["sma50"] * 100
    
    feature_cols = [
        "rsi", "macd_hist", "adx", "atr_pct", 
        "bb_width", "roc20", "ema20_slope", 
        "vol_spike", "ema20_dist", "sma50_dist"
    ]
    
    df = df.dropna(subset=feature_cols + ["target"])
    if len(df) < 100:
        return None, None
        
    X = df[feature_cols]
    y = df["target"]
    
    # 100 Agacli bir Random Forest
    model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1)
    model.fit(X, y)
    
    return model, feature_cols


def run_scan(
    symbols: List[str],
    exchange: str,
    tf_name: str,
    delay_ms: int,
    workers: int = 1,
    gui: bool = True,
) -> Tuple[pd.DataFrame, List[str]]:
    tf   = TIMEFRAME_OPTIONS[tf_name]
    rows: List[Dict[str, object]] = []
    errs: List[str] = []

    if gui:
        p = st.progress(0)
        t = st.empty()
    else:
        p, t = None, None

    done_count = [0]  # mutablб sayac (thread-safe icin liste)

    # === YAPAY ZEKA MODELİNİ YÜKLE / EĞİT ===
    from tvDatafeed import TvDatafeed
    tv_shared = TvDatafeed()
    ai_model, ai_features = get_ai_model(exchange, tf_name, tv=tv_shared)

    # FIX: Per-worker delay ekle
    def scan_one(sym: str, tv_instance, worker_id: int = 0) -> Optional[Dict[str, object]]:
        try:
            tv = tv_instance
            base_raw = fetch_hist(tv, sym, exchange, interval_obj(tf["base"]), tf["bars"], retries=3)
            conf_raw = fetch_hist(tv, sym, exchange, interval_obj(tf["confirm"]), tf["confirm_bars"], retries=3)
            base = add_indicators(base_raw)
            conf = add_indicators(conf_raw)

            vb = base.dropna(subset=["close", "ema20", "ema50", "sma20", "rsi", "macd_hist", "atr", "atr_pct", "adx"])
            vc = conf.dropna(subset=["close", "ema20", "ema50", "macd_hist"])
            if vb.empty or vc.empty:
                return {"_err": f"{sym}: yeterli veri yok"}

            # Numba Hızlandırması Sebebiyle Vectorized / Array Operations (Performans İçin iloc[-1] yerine tail(1) dict donusumu)
            last = vb.iloc[-1]
            prev = vb.iloc[-2] if len(vb) > 1 else last
            conf_last = vc.iloc[-1]
            s = score_symbol(last, prev, conf_last, exchange)

            # --- YAPAY ZEKA TAHMİNİ ---
            ai_prob = 0.0
            if ai_model is not None and ai_features is not None:
                feat_dict = {}
                for col in ai_features:
                    if col == "ema20_dist":
                        feat_dict[col] = float((last["close"] - last["ema20"]) / last["ema20"]) * 100 if last["ema20"] > 0 else 0.0
                    elif col == "sma50_dist":
                        feat_dict[col] = float((last["close"] - last["sma50"]) / last["sma50"]) * 100 if last["sma50"] > 0 else 0.0
                    else:
                        feat_dict[col] = float(_safe_get(last, col, 0.0))
                
                # Model predict_proba -> [Negatif İhtimali, Pozitif İhtimali]
                X_input = np.array([[feat_dict[c] for c in ai_features]])
                prob_res = ai_model.predict_proba(X_input)[0]
                if len(prob_res) > 1:
                    ai_prob = prob_res[1] * 100

            return {
                "Hisse": sym,
                "AI Tahmin": f"%{round(ai_prob, 1)}" if ai_model else "-",
                **s,
                "RSI":         round(float(last["rsi"]), 2),
                "ADX":         round(float(last["adx"]), 2),
                "ATR%":        round(float(last["atr_pct"]), 2),
                "Hacim Spike": round(float(_safe_get(last, "vol_spike", 0.0)), 2),
                "Hacim Patlamasi": "💥 EVET" if float(_safe_get(last, "vol_spike", 0.0)) >= 2.5 else "Hayır",
                "Bollinger Genisligi": round(float(_safe_get(last, "bb_width", 10.0)), 2),
                "Daralma (Squeeze)": "🗜 İzlenir" if bool(_safe_get(last, "bb_squeeze", False)) else "-",
                "Likidite (TL)": round(float(_safe_get(last, "close", 0.0) * _safe_get(last, "vol_ma20", 0.0)), 0),
            }
        except Exception as e:
            return {"_err": f"{sym}: {e}"}
        finally:
            # Bot tespitini zorlaştırmak için her istekten sonra rastgele küçük gecikmeler ekle (Jitter)
            if workers == 1:
                # Serial mode: delay + jitter
                time.sleep((max(delay_ms, 0) / 1000) + random.uniform(0.1, 0.4))
            else:
                # Parallel mode: per-worker offset + jitter
                # Per-worker delay: worker_id'ye göre kaydırarak aynı anda yüklenmeyi önle
                per_worker_delay = 0.4 + (worker_id * 0.2) + random.uniform(0.05, 0.3)
                time.sleep(per_worker_delay)

    if workers > 1:
        # Paralel mod: ThreadPoolExecutor ile coklu baglanti
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            # Worker ID'ler ile task'ları eşle
            futures = {ex.submit(scan_one, sym, tv_shared, i % workers): sym for i, sym in enumerate(symbols)}
            for i, fut in enumerate(concurrent.futures.as_completed(futures), start=1):
                sym    = futures[fut]
                try:
                    result = fut.result()
                    if result is None:
                        pass
                    elif "_err" in result:
                        errs.append(result["_err"])
                    else:
                        rows.append(result)
                except Exception as e:
                    errs.append(f"{sym}: {str(e)}")
                if gui and t and p:
                    t.write(f"Tamamlandi: {sym} ({i}/{len(symbols)})")
                    p.progress(i / max(1, len(symbols)))
    else:
        # Sira li mod: tek bagla nti, gecikme uygulanir
        for i, sym in enumerate(symbols, start=1):
            if gui and t:
                t.write(f"Taraniyor: {sym} ({i}/{len(symbols)})")
            result = scan_one(sym, tv_shared, worker_id=0)
            if result is None:
                pass
            elif "_err" in result:
                errs.append(result["_err"])
            else:
                rows.append(result)
            if gui and p:
                p.progress(i / max(1, len(symbols)))

    if gui and t and p:
        t.empty()
        p.empty()

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by=["Kalite", "Skor", "Guven"], ascending=False).reset_index(drop=True)
    return df, errs


# FIX: Return type ve Market string düzeltildi
def run_backtest(symbol: str, exchange: str, tf_name: str, initial_capital: float = 10000.0) -> Tuple[pd.DataFrame, dict, pd.DataFrame, object]:
    from tvDatafeed import TvDatafeed
    tv = TvDatafeed()
    tf = TIMEFRAME_OPTIONS[tf_name]
    
    with st.spinner(f"{symbol} için geçmiş veriler indiriliyor ve simülasyon hesaplanıyor..."):
        try:
            base_raw = fetch_hist(tv, symbol, exchange, interval_obj(tf["base"]), 1500, retries=3)
            conf_raw = fetch_hist(tv, symbol, exchange, interval_obj(tf["confirm"]), 1500, retries=3)
        except Exception as e:
            st.error(f"Veri çekme hatası: {e}")
            return pd.DataFrame(), {}, pd.DataFrame(), None
        
        if base_raw is None or base_raw.empty:
            st.error("Sembol verisi bulunamadı.")
            return pd.DataFrame(), {}, pd.DataFrame(), None
            
        base = add_indicators(base_raw)
        conf = add_indicators(conf_raw)
        
        base.index = base.index.tz_localize(None) if base.index.tz is not None else base.index
        conf.index = conf.index.tz_localize(None) if conf.index.tz is not None else conf.index
        
        conf_aligned = conf.reindex(base.index).ffill()
        
        trades = []
        equity = initial_capital
        position = 0
        entry_price = 0.0
        stop_loss = 0.0
        target = 0.0
        win_count = 0
        loss_count = 0
        bars_held = 0 # Zaman stopu için sayaç
        
        start_idx = 260
        if len(base) <= start_idx:
            st.error("Yeterli geçmiş veri yok (en az 260 mum gerekiyor).")
            return pd.DataFrame(), {}, pd.DataFrame()
            
        for i in range(start_idx, len(base)):
            # Numba tabanli hızlı vektor hesapla satırlar üzerinden
            last = base.iloc[i]
            prev = base.iloc[i-1]
            conf_last = conf_aligned.iloc[i]
            
            if position > 0:
                bars_held += 1
                
                # Fiyatlara hizli ve direk erisim
                last_low = last["low"]
                last_high = last["high"]
                last_close = last["close"]
                last_ema20 = last["ema20"]
                
                if last_low <= stop_loss:
                    profit = (stop_loss - entry_price) * position
                    equity += profit + (position * entry_price)
                    trades.append({"Tarih": last.name, "Tip": "SAT (Stop)", "Fiyat": round(stop_loss,2), "Kar/Zarar": round(profit,2), "Bakiye": round(equity,2), "MACD": "-", "RSI": "-", "Bollinger": "-"})
                    if profit > 0: win_count += 1
                    else: loss_count += 1
                    position = 0
                elif last_high >= target:
                    profit = (target - entry_price) * position
                    equity += profit + (position * entry_price)
                    trades.append({"Tarih": last.name, "Tip": "SAT (Hedef)", "Fiyat": round(target,2), "Kar/Zarar": round(profit,2), "Bakiye": round(equity,2), "MACD": "-", "RSI": "-", "Bollinger": "-"})
                    win_count += 1
                    position = 0
                elif bars_held >= 15 or float(last_close) < float(last_ema20): # 15 Bar veya EMA20 Altı Trend İflası
                    is_ema_stop = float(last_close) < float(last_ema20)
                    cikis_sebebi = "SAT (EMA20 Kırıldı)" if is_ema_stop else "SAT (Zaman Aşımı)"
                    profit = (last_close - entry_price) * position
                    equity += profit + (position * entry_price)
                    trades.append({"Tarih": last.name, "Tip": cikis_sebebi, "Fiyat": round(last_close,2), "Kar/Zarar": round(profit,2), "Bakiye": round(equity,2), "MACD": "-", "RSI": "-", "Bollinger": "-"})
                    if profit > 0: win_count += 1
                    else: loss_count += 1
                    position = 0
                continue
                
            s = score_symbol(last, prev, conf_last, exchange)
            if s["Sinyal"] == "AL":
                entry_price = float(last["close"])
                atr_val = float(last["atr"]) if pd.notna(last["atr"]) else 0.0
                if atr_val == 0: continue
                
                stop_loss = entry_price - (2.0 * atr_val)
                target = entry_price + (4.0 * atr_val)
                position = equity / entry_price
                equity = 0
                bars_held = 0
                
                trades.append({
                    "Tarih": last.name, "Tip": "AL", "Fiyat": round(entry_price,2), 
                    "Hedef": round(target,2), "Stop": round(stop_loss,2), "Bakiye": round((position * entry_price),2),
                    "MACD": s.get("MACD Durumu", "-"), "RSI": round(float(last["rsi"]),1), "Bollinger": s.get("Bollinger", "-")
                })

        if position > 0:
            last_price = base.iloc[-1]["close"]
            profit = (last_price - entry_price) * position
            equity += profit + (position * entry_price)
            trades.append({"Tarih": base.index[-1], "Tip": "SAT (Kapanış)", "Fiyat": round(last_price,2), "Kar/Zarar": round(profit,2), "Bakiye": round(equity,2), "MACD": "-", "RSI": "-", "Bollinger": "-"})
            if profit > 0: win_count += 1
            else: loss_count += 1
            
        total_trades = win_count + loss_count
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
        
        profits = [t["Kar/Zarar"] for t in trades if "Kar/Zarar" in t]
        gross_profit = sum(x for x in profits if x > 0)
        gross_loss = abs(sum(x for x in profits if x < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        avg_profit = gross_profit / win_count if win_count > 0 else 0.0
        avg_loss = gross_loss / loss_count if loss_count > 0 else 0.0
        expectancy = (win_rate/100 * avg_profit) - ((1 - win_rate/100) * avg_loss)
        
        max_drawdown = 0.0
        peak = initial_capital
        
        for t in trades:
            if "Bakiye" in t:
                eq = t["Bakiye"]
                if eq > peak: 
                    peak = eq
                dd = (peak - eq) / peak * 100
                if dd > max_drawdown: 
                    max_drawdown = dd
        
        stats = {
            "Başlangıç Sermayesi ($)": initial_capital,
            "Final Bakiye ($)": round(equity, 2),
            "Toplam Getiri (%)": round(((equity - initial_capital) / initial_capital) * 100, 2),
            "Toplam İşlem": total_trades,
            "Kazanma Oranı (%)": round(win_rate, 2),
            "Kazançlı İşlem": win_count,
            "Zararlı İşlem": loss_count,
            "Profit Factor": round(profit_factor, 2),
            "Ortalama Kazanç ($)": round(avg_profit, 2),
            "Ortalama Zarar ($)": round(avg_loss, 2),
            "Max Drawdown (%)": round(max_drawdown, 2),
            "Expectancy ($)": round(expectancy, 2)
        }
        
        # --- VectorBT Portfolio Construction ---
        portfolio = None
        try:
            import vectorbt as vbt
            
            # create size and price arrays
            vbt_size = pd.Series(0.0, index=base.index)
            vbt_price = pd.Series(np.nan, index=base.index)
            
            # Parse trades to populate arrays
            for td in trades:
                t_date = td["Tarih"]
                if t_date in base.index:
                    if td["Tip"] == "AL":
                        vbt_size.loc[t_date] = initial_capital / td["Fiyat"] # pseudo size
                        vbt_price.loc[t_date] = td["Fiyat"]
                    elif "SAT" in td["Tip"]:
                        # Sell all accumulated previous size
                        prev_size = vbt_size.loc[:t_date].sum()
                        if prev_size > 0:
                            vbt_size.loc[t_date] = -prev_size
                            vbt_price.loc[t_date] = td["Fiyat"]
                            
            # Build portfolio
            portfolio = vbt.Portfolio.from_orders(
                close=base["close"],
                size=vbt_size,
                price=vbt_price.fillna(base["close"]),
                init_cash=initial_capital,
                freq="1D",
                fees=0.001
            )
        except Exception as e:
            st.error(f"VectorBT Grafiği oluşturulamadı: {e}")
        
        return pd.DataFrame(trades), stats, base, portfolio

if __name__ == "__main__":
    init_gui()
