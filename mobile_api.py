"""
Mobile API Module - GitHub Actions ile mobil uygulama arasındaki köprü
GitHub Actions tarama sonuçlarını bu API'ye POST eder, mobil uygulama GET ile çeker.
"""
import os
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import pytz

TR_TZ = pytz.timezone("Europe/Istanbul")

router = APIRouter(prefix="/api/mobile", tags=["mobile"])

# Tarama sonuçlarını geçici olarak bellekte tutuyoruz (production için Redis/DB önerilir)
MOBILE_SCAN_CACHE: Dict[str, Any] = {
    "BIST": {"results": [], "timestamp": None, "status": "pending"},
    "NASDAQ": {"results": [], "timestamp": None, "status": "pending"},
    "CRYPTO": {"results": [], "timestamp": None, "status": "pending"}
}


class ScanResult(BaseModel):
    """Tek hisse/sembol için tarama sonucu"""
    hisse: str
    fiyat: float = 0.0
    sinyal: str = "BEKLE"  # AL, SAT, BEKLE
    aksiyon: str = "-"
    kalite: float = 0.0
    hedef_1: Optional[float] = None
    hedef_1_pct: Optional[float] = None
    stop_loss: Optional[float] = None
    stop_pct: Optional[float] = None
    rr_orani: Optional[float] = None
    ozel_durum: str = "-"
    ultimate_sinyal: bool = False
    ai_tahmin: float = 0.0
    hacim_spike: float = 0.0
    trend_skor: float = 0.0
    dip_skor: float = 0.0
    momentum_skor: float = 0.0
    market_regime: str = "MIXED"
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    isy_grade: str = "-"


class WebhookPayload(BaseModel):
    """GitHub Actions'tan gelecek webhook payload"""
    market: str  # BIST, NASDAQ, CRYPTO
    status: str  # OPEN, CLOSED, PRE_MARKET
    scan_time: str
    results: List[Dict[str, Any]]
    summary: Optional[Dict[str, Any]] = None
    ai_commentary: Optional[str] = None


@router.post("/webhook")
async def receive_scan_results(payload: WebhookPayload):
    """
    GitHub Actions'tan gelen tarama sonuçlarını alır ve cache'e kaydeder.
    GitHub Action bu endpoint'i POST ederek yeni tarama sonuçlarını gönderir.
    """
    market = payload.market.upper()
    
    if market not in ["BIST", "NASDAQ", "CRYPTO"]:
        raise HTTPException(status_code=400, detail=f"Geçersiz market: {market}")
    
    # Verileri cache'e kaydet
    MOBILE_SCAN_CACHE[market] = {
        "results": payload.results,
        "timestamp": payload.scan_time,
        "status": payload.status,
        "summary": payload.summary,
        "ai_commentary": payload.ai_commentary,
        "received_at": datetime.now(TR_TZ).isoformat()
    }
    
    buy_count = sum(1 for r in payload.results if r.get("sinyal") == "AL")
    
    return {
        "success": True,
        "message": f"{market} için {len(payload.results)} sembol işlendi, {buy_count} AL sinyali",
        "market": market,
        "timestamp": payload.scan_time
    }


@router.get("/scan-results")
async def get_scan_results(market: Optional[str] = None):
    """
    Mobil uygulamanın son tarama sonuçlarını almak için kullanacağı endpoint.
    market parametresi verilmezse tüm piyasaların sonuçlarını döner.
    """
    if market:
        market = market.upper()
        if market not in MOBILE_SCAN_CACHE:
            raise HTTPException(status_code=404, detail=f"Market bulunamadı: {market}")
        
        cache_data = MOBILE_SCAN_CACHE[market]
        if not cache_data["timestamp"]:
            return {
                "market": market,
                "status": "pending",
                "message": "Henüz tarama yapılmadı",
                "results": [],
                "timestamp": None
            }
        
        return {
            "market": market,
            "status": cache_data["status"],
            "timestamp": cache_data["timestamp"],
            "received_at": cache_data.get("received_at"),
            "summary": cache_data.get("summary"),
            "ai_commentary": cache_data.get("ai_commentary"),
            "result_count": len(cache_data["results"]),
            "buy_signals": sum(1 for r in cache_data["results"] if r.get("sinyal") == "AL"),
            "results": cache_data["results"]
        }
    
    # Tüm piyasaları döner
    response = {}
    for mkt in ["BIST", "NASDAQ", "CRYPTO"]:
        cache_data = MOBILE_SCAN_CACHE[mkt]
        response[mkt] = {
            "status": cache_data["status"],
            "timestamp": cache_data["timestamp"],
            "result_count": len(cache_data["results"]),
            "buy_signals": sum(1 for r in cache_data["results"] if r.get("sinyal") == "AL"),
            "results": cache_data["results"] if cache_data["timestamp"] else []
        }
    
    return response


@router.get("/health")
async def health_check():
    """API'nin canlı olduğunu kontrol eder"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(TR_TZ).isoformat(),
        "markets_available": list(MOBILE_SCAN_CACHE.keys())
    }


@router.get("/last-update")
async def get_last_update_times():
    """Her piyasa için son güncelleme zamanlarını döner"""
    updates = {}
    for market, data in MOBILE_SCAN_CACHE.items():
        updates[market] = {
            "last_scan": data["timestamp"],
            "received_at": data.get("received_at"),
            "status": data["status"],
            "symbol_count": len(data["results"])
        }
    return updates
