from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import pandas as pd
import json
import concurrent.futures
import time
import os
from pydantic import BaseModel

try:
    from streamlit_app import run_scan
    from constants import DEFAULT_BIST_HISSELER, DEFAULT_NASDAQ_HISSELER, DEFAULT_CRYPTO_SYMBOLS, TIMEFRAME_OPTIONS
    from data_fetcher import get_ai_model, check_index_health, interval_obj, fetch_hist
    from indicators import add_indicators, calculate_price_targets
    from scoring import score_symbol
    from reporting import format_telegram_message
    from utils import _safe_get, send_telegram_message
    from db_manager import save_scan_results
    from tvDatafeed import TvDatafeed
except ImportError:
    pass # hata almamak için

app = FastAPI(title="Gelişmiş Hisse Tarayıcı API")

# HTML dosyanızın bulunduğu klasörü templateler için tanımlıyoruz
templates = Jinja2Templates(directory="frontend")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # index.html dosyasını direkt olarak kullanıcıya sunuyoruz
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/symbols")
async def get_symbols():
    return {
        "BIST": DEFAULT_BIST_HISSELER,
        "NASDAQ": DEFAULT_NASDAQ_HISSELER,
        "CRYPTO": DEFAULT_CRYPTO_SYMBOLS
    }

@app.get("/api/scan")
async def run_scan_api(
    exchange: str = Query("BIST"), 
    tf_name: str = Query("Gunluk"),
    symbols_str: str = Query(""),
    delay_ms: int = Query(500),
    workers: int = Query(5)
):
    if exchange == "BIST":
        symbols_list = DEFAULT_BIST_HISSELER
    elif exchange == "NASDAQ":
        symbols_list = DEFAULT_NASDAQ_HISSELER
    elif exchange == "CRYPTO":
        symbols_list = DEFAULT_CRYPTO_SYMBOLS
    else:
        symbols_list = []
        
    if symbols_str.strip():
        symbols_list = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]

    if tf_name == "Gunluk Haftalik":
        tf_name = "Gunluk + Haftalik"

    tv = TvDatafeed()
    tf = TIMEFRAME_OPTIONS[tf_name]
    ai_model, ai_features = get_ai_model(exchange, tf_name, _tv=tv)
    index_healthy = check_index_health(tv, exchange, tf_name)
    tv_exchange = "BINANCE" if exchange == "CRYPTO" else exchange

    def scan_one(sym, worker_id=0):
        try:
            if delay_ms > 0:
                time.sleep((delay_ms / 1000.0) + (worker_id * 0.1))
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
                   "Bollinger Genisligi": round(float(_safe_get(last, "bb_width", 0.0)), 2),
                   "Daralma (Squeeze)": "🗜 İzlenir" if bool(_safe_get(last, "bb_squeeze", False)) else "-"}
            if targets: res.update(targets)
            # JSON formatında serialize edilirken fillna() benzeri sorun çıkmaması için tüm string dışı NaNs atılmalı ama şimdilik geç
            import math
            for k, v in res.items():
                if isinstance(v, float) and math.isnan(v):
                    res[k] = ""
            return res
        except Exception as e: return {"_err": f"{sym}: {str(e)}"}

    import asyncio
    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'total': len(symbols_list)})}\n\n"
        
        loop = asyncio.get_event_loop()
        completed = 0
        all_results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            tasks = [loop.run_in_executor(ex, scan_one, sym, i % workers) for i, sym in enumerate(symbols_list)]
            
            for coro in asyncio.as_completed(tasks):
                r = await coro
                completed += 1
                if "_err" not in r:
                    all_results.append(r)
                    yield f"data: {json.dumps({'type': 'result', 'data': r, 'completed': completed})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'msg': r['_err'], 'completed': completed})}\n\n"
                    
        # Send telegram message at the end if configured and we have results
        if len(all_results) > 0:
            df = pd.DataFrame(all_results)
            
            # DB'ye Kaydet (Streamlit sürümündeki gibi)
            try:
                save_scan_results(df, exchange, tf_name)
            except Exception as e:
                print(f"DB Kayıt Hatası: {e}")

            if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
                buy_signals = df[df.get("Sinyal", "") == "AL"]
                if not buy_signals.empty:
                    try:
                        msg = format_telegram_message(exchange, df, "OPEN")
                        send_telegram_message(os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID"), msg)
                    except Exception as e:
                        print(f"Telegram error: {e}")

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

class AIRequest(BaseModel):
    query: str
    data: list

@app.post("/api/ai_chat")
async def ai_chat_api(req: AIRequest):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key: return {"error": "API anahtarı eksik"}
    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        
        df = pd.DataFrame(req.data)
        display_cols = ["Hisse", "Kalite", "Sinyal", "Düşüş Riski", "Guven", "Özel Durum", "Aksiyon", "Trend Skor", "Dip Skor", "Momentum Skor", "R/R"]
        df_cols = [c for c in display_cols if c in df.columns]
        
        context_df = df[df_cols].head(30) if not df.empty else df
        csv_data = context_df.to_csv(index=False)
        
        system_prompt = "Sen uzman bir algoritma/veri analiz danışmanısın. Kullanıcıya verilen hisse tablosu (CSV) üzerinden net, kısa ve teknik terimleri aşırı kullanmadan sıralama ve analizler çıkar. Yalnızca tabloda olan hisseleri kullan. Cevaplarını markdown veya düz metin ile ver."
        user_msg = f"Şu anki tarama tablosu:\n{csv_data}\n\nKullanıcının Sorusu: {req.query}"

        response = client.chat.completions.create(
            model="nvidia/nemotron-4-340b-instruct:free",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            max_tokens=1500,
            temperature=0.3,
        )
        return {"answer": response.choices[0].message.content.strip()}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
