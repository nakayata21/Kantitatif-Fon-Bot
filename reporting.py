import os
import pandas as pd
from datetime import datetime
import pytz

TR_TZ = pytz.timezone("Europe/Istanbul")

def format_telegram_message(market, df_res, status):
    if df_res.empty: return f"❌ {market} piyasasında fırsat bulunamadı."
    
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    status_text = "🟢 Piyasa Açık (Canlı)" if status == "OPEN" else "🕒 Piyasa Kapalı/Açılmak Üzere"
    
    if buy_signals.empty: 
        # AL sinyali yoksa kaliteye göre en iyi 5 beklemedeki hisseyi göster
        top_watchlist = df_res.sort_values(by="Kalite", ascending=False).head(5)
        msg = f"🛰️ *{market} SCANNER* ({datetime.now(TR_TZ).strftime('%H:%M')})\n"
        msg += f"⏱ Durum: {status_text}\n\n"
        msg += f"⚠️ *Onaylı AL sinyali yok, ancak en yüksek kaliteli adaylar:*\n\n"
        
        for _, row in top_watchlist.iterrows():
            msg += f"👀 *{row['Hisse']}* | Puan: {row['Kalite']} | {row.get('Aksiyon', '-')}\n"
        
        return msg
    
    # En iyi 8
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(8)
    
    msg = f"🛰️ *{market} QUANT DECISION ENGINE* ({datetime.now(TR_TZ).strftime('%H:%M')})\n"
    msg += f"⏱ Durum: {status_text}\n\n"
    
    # ULTIMATE FUSION (UT Bot + Uyumsuzluk)
    if "UT_Plus_Div" in df_res.columns:
        ultimates = df_res[df_res["UT_Plus_Div"] == True].sort_values(by="Kalite", ascending=False).head(3)
        if not ultimates.empty:
            msg += "🚀 *ULTIMATE REVERSAL (DOUBLE CONFIRMED)*\n"
            for _, row in ultimates.iterrows():
                msg += f"🔥 *{row['Hisse']}* | Puan: {row['Kalite']}/100 | Hedef 1: {row.get('Hedef 1', '-')}\n"
            msg += "*(UT Bot + Pozitif Uyumsuzluk Aynı Anda Verildi!)*\n\n"
    
    # Gruplandırma
    groups = {"Kısa": [], "Orta": [], "Uzun": []}
    for _, row in top_buys.iterrows():
        vade = row.get("Vade", "Kısa")
        groups[vade].append(row)
    
    for vade_tip, items in groups.items():
        if not items: continue
        
        vade_label = "⏳ KISA VADE" if vade_tip == "Kısa" else ("📅 ORTA VADE" if vade_tip == "Orta" else "🏆 UZUN VADE")
        msg += f"══ {vade_label} ══\n\n"
        
        for row in items:
            engine = row.get('Engine', 'SAFE')
            decision = row.get('Decision', 'NO TRADE')
            
            # Engine Label
            engine_str = "⚡ OPPORTUNITY" if engine == "OPPORTUNITY" else "🛡️ SAFE"
                
            msg += f"{engine_str} | *{row['Hisse']}*\n"
            msg += f"🎯 *Decision:* {decision} ({row.get('Elite Derece', 'STANDART')})\n"
            msg += f"📊 *Setup:* {row.get('Skor', 0)}/100 | *Trade Puanı:* {row.get('Kalite', 0)}/100\n"
            msg += f"🚀 *Plan:* {row.get('Aksiyon', '-')}\n"
            
            # Fiyat ve Risk (Kısa format)
            tp_pct = row.get('Hedef 1 %', 0)
            msg += f"💼 Giriş: {row.get('Fiyat', 0)} | SL: {row.get('Stop Loss', 0)} (%{row.get('Stop %', 0)})\n"
            if tp_pct > 0:
                msg += f"💰 Hedef 1 (Kar Al): +%{tp_pct} ({row.get('Hedef 1', 0)})\n"
            
            msg += f"🔍 *Teknik:* Vol: x{row.get('Hacim Spike', 0)} | {row.get('Özel Durum', '-')}\n"
            
            # Temel Analiz Verileri (Eğer Varsa)
            pe = row.get("pe_ratio")
            pb = row.get("pb_ratio")
            grade = row.get("isy_grade")
            
            fund_parts = []
            if pd.notna(pe) and pe is not None and str(pe) != "nan":
                fund_parts.append(f"F/K: {round(float(pe), 1)}")
            if pd.notna(pb) and pb is not None and str(pb) != "nan":
                fund_parts.append(f"PD/DD: {round(float(pb), 1)}")
            if grade and str(grade) != "nan" and grade != "-":
                fund_parts.append(f"Not: {grade}")
                
            if fund_parts:
                msg += f"🏢 *Temel:* {' | '.join(fund_parts)}\n"
            
            msg += "\n"
            
    # Güçlü UT Bot Sinyalleri (Sadece Tek Başına Olanlar)
    if "UT_Bot_Al" in df_res.columns:
        # ULTIMATE olmayan, sadece UT Bot AL verenler
        ut_only = df_res[(df_res["UT_Bot_Al"] == True) & (df_res.get("UT_Plus_Div", False) == False)]
        if not ut_only.empty:
            msg += "🤖 *GÜÇLÜ UT BOT YAKALAMALARI*\n"
            ut_stocks = ut_only.sort_values(by="Kalite", ascending=False).head(5)
            for _, row in ut_stocks.iterrows():
                msg += f"👉 *{row['Hisse']}* | Puan: {row['Kalite']}/100 | Hedef 1: {row.get('Hedef 1', '-')}\n"
            msg += "\n"
            
    # Pozitif Uyumsuzluk Sinyalleri (Sadece Tek Başına Olanlar)
    if "has_bullish_div" in df_res.columns:
        # ULTIMATE olmayan, sadece Uyumsuzluk verenler
        div_only = df_res[(df_res["has_bullish_div"] == True) & (df_res.get("UT_Plus_Div", False) == False)]
        if not div_only.empty:
            msg += "🐂 *POZİTİF UYUMSUZLUK (RADAR)*\n"
            div_stocks = div_only.sort_values(by="Kalite", ascending=False).head(5)
            for _, row in div_stocks.iterrows():
                msg += f"👉 *{row['Hisse']}* | Puan: {row['Kalite']}/100\n"
            msg += "\n"
            
    return msg
