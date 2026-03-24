import os
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
            
            msg += f"🔍 *Metrikler:* Vol: x{row.get('Hacim Spike', 0)} | {row.get('Özel Durum', '-')}\n\n"
            
    return msg
