import os
import pandas as pd
from datetime import datetime
import pytz

TR_TZ = pytz.timezone("Europe/Istanbul")

def format_telegram_message(market, df_res, status):
    if df_res is None or df_res.empty:
        return f"❌ {market} piyasasında fırsat bulunamadı."
    
    # Sinyal sütunu garantisi
    if "Sinyal" not in df_res.columns:
        df_res["Sinyal"] = "BEKLE"
        
    buy_signals = df_res[df_res["Sinyal"] == "AL"]
    status_text = "🟢 Piyasa Açık (Canlı)" if status == "OPEN" else "🕒 Piyasa Kapalı/Açılmak Üzere"
    
    if buy_signals.empty: 
        # AL sinyali yoksa kaliteye göre en iyi 5 beklemedeki hisseyi göster
        if "Kalite" in df_res.columns:
            top_watchlist = df_res.sort_values(by="Kalite", ascending=False).head(5)
        else:
            top_watchlist = df_res.head(5)
            
        msg = f"🛰️ *{market} SCANNER* ({datetime.now(TR_TZ).strftime('%H:%M')})\n"
        msg += f"⏱ Durum: {status_text}\n\n"
        msg += f"⚠️ *Onaylı AL sinyali yok, ancak en yüksek kaliteli adaylar:*\n\n"
        
        for _, row in top_watchlist.iterrows():
            kalite = row.get("Kalite", 0)
            hisse = row.get("Hisse") or row.get("symbol") or "Bilinmeyen"
            aksiyon = row.get("Aksiyon", "-")
            msg += f"👀 *{hisse}* | Puan: {kalite} | {aksiyon}\n"
        
        return msg
    
    # En iyi 8
    top_buys = buy_signals.sort_values(by="Kalite", ascending=False).head(8) if "Kalite" in buy_signals.columns else buy_signals.head(8)
    
    msg = f"🛰️ *{market} QUANT DECISION ENGINE* ({datetime.now(TR_TZ).strftime('%H:%M')})\n"
    msg += f"⏱ Durum: {status_text}\n\n"
    
    # ULTIMATE FUSION (UT Bot + Uyumsuzluk)
    if "UT_Plus_Div" in df_res.columns:
        ultimates = df_res[df_res["UT_Plus_Div"] == True]
        if not ultimates.empty:
            ult_top = ultimates.sort_values(by="Kalite", ascending=False).head(3) if "Kalite" in ultimates.columns else ultimates.head(3)
            msg += "🚀 *ULTIMATE REVERSAL (DOUBLE CONFIRMED)*\n"
            for _, row in ult_top.iterrows():
                hisse = row.get("Hisse") or row.get("symbol") or "Bilinmeyen"
                kalite = row.get("Kalite", 0)
                hed1 = row.get("Hedef 1", "-")
                msg += f"🔥 *{hisse}* | Puan: {kalite}/100 | Hedef 1: {hed1}\n"
            msg += "*(UT Bot + Pozitif Uyumsuzluk Aynı Anda Verildi!)*\n\n"
    
    # Gruplandırma
    groups = {"Kısa": [], "Orta": [], "Uzun": []}
    for _, row in top_buys.iterrows():
        vade = row.get("Vade", "Kısa")
        if vade not in groups: vade = "Kısa"
        groups[vade].append(row)
    
    for vade_tip, items in groups.items():
        if not items: continue
        
        vade_label = "⏳ KISA VADE" if vade_tip == "Kısa" else ("📅 ORTA VADE" if vade_tip == "Orta" else "🏆 UZUN VADE")
        msg += f"══ {vade_label} ══\n\n"
        
        for row in items:
            hisse = row.get("Hisse") or row.get("symbol") or "Bilinmeyen"
            engine = row.get('Engine', 'SAFE')
            decision = row.get('Decision', 'NO TRADE')
            
            # Engine Label
            engine_str = "⚡ OPPORTUNITY" if engine == "OPPORTUNITY" else "🛡️ SAFE"
                
            msg += f"{engine_str} | *{hisse}*\n"
            msg += f"🎯 *Decision:* {decision} ({row.get('Elite Derece', 'STANDART')})\n"
            msg += f"📊 *Setup:* {row.get('Skor', 0)}/100 | *Trade Puanı:* {row.get('Kalite', 0)}/100\n"
            msg += f"🚀 *Plan:* {row.get('Aksiyon', '-')}\n"
            
            # Fiyat ve Risk (Kısa format)
            tp_pct = row.get('Hedef 1 %', 0)
            msg += f"💼 Giriş: {row.get('Fiyat', 0)} | SL: {row.get('Stop Loss', 0)} (%{row.get('Stop %', 0)})\n"
            if tp_pct and float(tp_pct) > 0:
                msg += f"💰 Hedef 1 (Kar Al): +%{tp_pct} ({row.get('Hedef 1', 0)})\n"
            
            msg += f"🔍 *Teknik:* Vol: x{row.get('Hacim Spike', 0)} | {row.get('Özel Durum', '-')}\n"
            
            sig_p = row.get("Sinyal Fiyatı", "-")
            if sig_p != "-":
                msg += f"💡 *Sinyal:* {sig_p} ({row.get('Sinyal Mesafesi', '-')} Mesafe | {row.get('Sinyal Zamanı', '-')})\n"
            
            # Temel Analiz Verileri (Eğer Varsa)
            pe = row.get("pe_ratio")
            pb = row.get("pb_ratio")
            grade = row.get("isy_grade")
            
            fund_parts = []
            try:
                if pd.notna(pe) and pe is not None and str(pe) != "nan":
                    val = float(str(pe).replace(",", "."))
                    fund_parts.append(f"F/K: {round(val, 1)}")
                if pd.notna(pb) and pb is not None and str(pb) != "nan":
                    val = float(str(pb).replace(",", "."))
                    fund_parts.append(f"PD/DD: {round(val, 1)}")
            except: pass
            
            if grade and str(grade) != "nan" and grade != "-":
                fund_parts.append(f"Not: {grade}")
                
            if fund_parts:
                msg += f"🏢 *Temel:* {' | '.join(fund_parts)}\n"
            
            # Takas Bilgisi
            takas_karar = row.get("Takas Karari", "-")
            if takas_karar not in ("-", "VERİ BEKLENİYOR", None):
                msg += f"📦 *Takas:* {takas_karar} (Puan: {row.get('Takas Puani', 0)})\n"
            
            msg += "\n"
            
    # Güçlü UT Bot Sinyalleri (Sadece Tek Başına Olanlar)
    if "UT_Bot_Al" in df_res.columns:
        # UT_Plus_Div varsa onu kullan yoksa False varsay
        has_plus = df_res["UT_Plus_Div"] if "UT_Plus_Div" in df_res.columns else [False] * len(df_res)
        ut_only = df_res[(df_res["UT_Bot_Al"] == True) & (has_plus == False)]
        if not ut_only.empty:
            msg += "🤖 *GÜÇLÜ UT BOT YAKALAMALARI*\n"
            ut_stocks = ut_only.sort_values(by="Kalite", ascending=False).head(5) if "Kalite" in ut_only.columns else ut_only.head(5)
            for _, row in ut_stocks.iterrows():
                hisse = row.get("Hisse") or row.get("symbol") or "Bilinmeyen"
                kalite = row.get("Kalite", 0)
                msg += f"👉 *{hisse}* | Puan: {kalite}/100 | Hedef 1: {row.get('Hedef 1', '-')}\n"
            msg += "\n"
            
    # Pozitif Uyumsuzluk Sinyalleri (Sadece Tek Başına Olanlar)
    if "has_bullish_div" in df_res.columns:
        has_plus = df_res["UT_Plus_Div"] if "UT_Plus_Div" in df_res.columns else [False] * len(df_res)
        div_only = df_res[(df_res["has_bullish_div"] == True) & (has_plus == False)]
        if not div_only.empty:
            msg += "🐂 *POZİTİF UYUMSUZLUK (RADAR)*\n"
            div_stocks = div_only.sort_values(by="Kalite", ascending=False).head(5) if "Kalite" in div_only.columns else div_only.head(5)
            for _, row in div_stocks.iterrows():
                hisse = row.get("Hisse") or row.get("symbol") or "Bilinmeyen"
                kalite = row.get("Kalite", 0)
                msg += f"👉 *{hisse}* | Puan: {kalite}/100\n"
            msg += "\n"
    
    # Wyckoff & VSA Akümülasyon
    acc_signals = []
    if "is_spring" in df_res.columns:
        springs = df_res[df_res["is_spring"] == True]
        if not springs.empty: acc_signals.append(f"⚡ *SPRING:* {', '.join(springs.get('Hisse', springs.get('symbol', [])).head(3).tolist())}")
    
    if "stopping_volume" in df_res.columns:
        st_vols = df_res[df_res["stopping_volume"] == True]
        if not st_vols.empty: acc_signals.append(f"🛡️ *STOP VOL:* {', '.join(st_vols.get('Hisse', st_vols.get('symbol', [])).head(3).tolist())}")

    if acc_signals:
        msg += "🧩 *AKÜMÜLASYON ANALİZİ*\n"
        msg += "\n".join(acc_signals) + "\n\n"
            
    return msg
