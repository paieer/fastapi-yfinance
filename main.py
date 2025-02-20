from fastapi import FastAPI, Depends, HTTPException, Header
import yfinance as yf
import os

# from dotenv import load_dotenv
# # 加载 .env 文件中的环境变量
# load_dotenv()

app = FastAPI()

HTTP_PROXY = os.getenv("HTTP_PROXY", "")
VALID_API_KEY = os.getenv("API_KEY", "default-secret-key")

async def verify_api_key(api_key: str = Header(..., alias="X-API-Key")):
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )
    return api_key

@app.get("/tickers/{symbol}", dependencies=[Depends(verify_api_key)])
async def get_stock_info(symbol: str):
    try:
        
        if HTTP_PROXY !="":
            dat = yf.Ticker(symbol).history(proxy=HTTP_PROXY)
        else:
            dat = yf.Ticker(symbol)
        info = dat.info
        
        # 处理无效的股票代码或空数据
        if not info or 'symbol' not in info:
            return {
                "status": False,
                "error": "Invalid stock symbol",
                "symbol": symbol
            }, 404
            
        return {
            "status": True,
            "symbol": symbol,
            "result": info
        }
        
    except Exception as e:
        # 处理所有可能的异常（网络错误、解析错误等）
        return {
            "status": False,
            "error": f"API request failed: {str(e)}",
            "symbol": symbol
        }, 500
