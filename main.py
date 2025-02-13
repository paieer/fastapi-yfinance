from fastapi import FastAPI
import yfinance as yf

app = FastAPI()

@app.get("/tickers/{symbol}")
async def get_stock_info(symbol: str):
    dat = yf.Ticker(symbol)
    info = dat.info
    if 'symbol' not in info:
        return {"error": "无效的股票代码", "symbol": symbol}, 404
    return info
