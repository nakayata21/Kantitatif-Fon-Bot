"""
GitHub Action için Mobile API Webhook Sender
Tarama sonuçlarını JSON formatına çevirip mobil API'ye gönderir
"""
import os
import json
import pandas as pd
import requests
from datetime import datetime
import pytz

TR_TZ = pytz.timezone("Europe/Istanbul")

# API ayarları - GitHub Secrets'tan okunmalı veya environment variable olarak verilmeli
MOBILE_API_URL = os.environ.get("MOBILE_API_URL", "http://localhost:8000/api/mobile/webhook")
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "")  # Opsiyonel güvenlik için


def convert_df_to_mobile_format(df: pd.DataFrame, market: str, status: str) -> dict:
    """
    DataFrame'i mobil uygulama için optimize edilmiş JSON formatına çevirir
    """
    results = []
    
    for _, row in df.iterrows():
        result = {
            "hisse": str(row.get("Hisse", row.get("symbol", "UNKNOWN"))),
            "fiyat": float(row.get("Fiyat", 0.0)) if pd.notna(row.get("Fiyat")) else 0.0,
            "sinyal": str(row.get("Sinyal", "BEKLE")),
            "aksiyon": str(row.get("Aksiyon", "-")),
            "kalite": float(row.get("Kalite", 0.0)) if pd.notna(row.get("Kalite")) else 0.0,
            "hedef_1": float(row.get("Hedef 1", 0.0)) if pd.notna(row.get("Hedef 1")) else None,
            "hedef_1_pct": float(row.get("Hedef 1 %", 0.0)) if pd.notna(row.get("Hedef 1 %")) else None,
            "stop_loss": float(row.get("Stop Loss", 0.0)) if pd.notna(row.get("Stop Loss")) else None,
            "stop_pct": float(row.get("Stop %", 0.0)) if pd.notna(row.get("Stop %")) else None,
            "rr_orani": float(row.get("R/R", 0.0)) if pd.notna(row.get("R/R")) else None,
            "ozel_durum": str(row.get("Özel Durum", "-")),
            "ultimate_sinyal": bool(row.get("UT_Plus_Div", False)),
            "ai_tahmin": float(row.get("AI Tahmin", 0.0).replace("%", "")) if pd.notna(row.get("AI Tahmin")) and isinstance(row.get("AI Tahmin"), str) else (float(row.get("AI Tahmin", 0.0)) if pd.notna(row.get("AI Tahmin")) else 0.0),
            "hacim_spike": float(row.get("Hacim Spike", 0.0)) if pd.notna(row.get("Hacim Spike")) else 0.0,
            "trend_skor": float(row.get("Trend Skor", 0.0)) if pd.notna(row.get("Trend Skor")) else 0.0,
            "dip_skor": float(row.get("Dip Skor", 0.0)) if pd.notna(row.get("Dip Skor")) else 0.0,
            "momentum_skor": float(row.get("Momentum Skor", 0.0)) if pd.notna(row.get("Momentum Skor")) else 0.0,
            "market_regime": str(row.get("market_regime", "MIXED")),
            "pe_ratio": float(row.get("pe_ratio")) if pd.notna(row.get("pe_ratio")) and str(row.get("pe_ratio")) != "nan" else None,
            "pb_ratio": float(row.get("pb_ratio")) if pd.notna(row.get("pb_ratio")) and str(row.get("pb_ratio")) != "nan" else None,
            "isy_grade": str(row.get("isy_grade", "-"))
        }
        results.append(result)
    
    # Özet istatistikler
    buy_signals = [r for r in results if r["sinyal"] == "AL"]
    summary = {
        "total_symbols": len(results),
        "buy_count": len(buy_signals),
        "avg_quality": sum(r["kalite"] for r in results) / len(results) if results else 0,
        "top_quality_symbol": max(results, key=lambda x: x["kalite"])["hisse"] if results else None,
        "ultimate_count": sum(1 for r in results if r["ultimate_sinyal"])
    }
    
    return {
        "market": market,
        "status": status,
        "scan_time": datetime.now(TR_TZ).isoformat(),
        "results": results,
        "summary": summary
    }


def send_to_mobile_api(df: pd.DataFrame, market: str, status: str, ai_commentary: str = None) -> dict:
    """
    Tarama sonuçlarını mobil API'ye gönderir
    """
    payload = convert_df_to_mobile_format(df, market, status)
    
    if ai_commentary:
        payload["ai_commentary"] = ai_commentary
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Opsiyonel API key güvenliği
    if API_SECRET_KEY:
        headers["X-API-Key"] = API_SECRET_KEY
    
    try:
        response = requests.post(MOBILE_API_URL, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ Mobil API'ye başarıyla gönderildi: {market}")
            return {"success": True, "response": response.json()}
        else:
            print(f"❌ Mobil API hatası ({response.status_code}): {response.text}")
            return {"success": False, "error": f"HTTP {response.status_code}", "details": response.text}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Bağlantı hatası: {str(e)}")
        return {"success": False, "error": "Connection failed", "details": str(e)}


def save_scan_results_json(df: pd.DataFrame, market: str, status: str, output_path: str = "mobile_scan_results.json"):
    """
    Tarama sonuçlarını JSON dosyasına kaydeder (GitHub Actions artifact olarak kullanılabilir)
    """
    payload = convert_df_to_mobile_format(df, market, status)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    
    print(f"📄 Tarama sonuçları {output_path} dosyasına kaydedildi")
    return output_path


if __name__ == "__main__":
    # Test için örnek kullanım
    print("Mobile API Sender Test Modu")
    print("Bu modül github_scan_action.py içinden çağrılmalıdır")
