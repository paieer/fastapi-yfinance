from fastapi import FastAPI, Depends, HTTPException, Header
import yfinance as yf
import os
import random
import string
import json
from datetime import datetime
import redis
import base64
# from dotenv import load_dotenv
# # 加载 .env 文件中的环境变量
# load_dotenv()

app = FastAPI()

redis_url = os.getenv("REDIS_URL")
r = redis.from_url(redis_url)
try:
    r.ping()
    print("Successfully connected to Redis!")
except redis.exceptions.ConnectionError as e:
    print(f"Could not connect to Redis: {e}")

CACHE_EXPIRATION = int(os.getenv("CACHE_EXPIRATION", 3600))  # Default to 1 hour if not specified
SESSION_PROXY= os.getenv("SESSION_PROXY", "").strip() or None
SESSION_A= os.getenv("SESSION_A", "").strip() or None
SESSION_B= os.getenv("SESSION_B", "").strip() or None

HTTP_PROXY = os.getenv("HTTP_PROXY", "").strip() or None
VALID_API_KEY = os.getenv("API_KEY", "default-secret-key").strip()

def validate_date_format(date_str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def generate_random_string(length=8):
            letters_and_digits = string.ascii_letters + string.digits
            return ''.join(random.choice(letters_and_digits) for i in range(length))

async def verify_api_key(api_key: str = Header(..., alias="X-API-Key")):
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )
    return api_key

@app.get("/tickers/{symbol}", dependencies=[Depends(verify_api_key)])
async def get_stock_info(symbol: str):
    cache_key = f"stock_info:{symbol}"
    cached_data = r.get(cache_key)
    if cached_data:
        return {
            "status": True,
            "symbol": symbol,
            "result": json.loads(cached_data),
            "cache": "hit"
        }
    
    try:
        random_string = generate_random_string()
        if SESSION_PROXY == "TRUE":
            Proxy = SESSION_A + random_string + SESSION_B 
            ticker = yf.Ticker(symbol, proxy=Proxy)
        else:
            ticker = yf.Ticker(symbol, proxy=HTTP_PROXY)
            
        result = ticker.info
        # 处理无效的股票代码或空数据
        if not result or 'symbol' not in result:
            return {
                "status": False,
                "error": "Invalid stock symbol",
                "symbol": symbol
            }
        
        r.setex(cache_key, CACHE_EXPIRATION, json.dumps(result))
        return {
            "status": True,
            "symbol": symbol,
            "result": result
        }
        
    except Exception as e:
        # 处理所有可能的异常（网络错误、解析错误等）
        return {
            "status": False,
            "error": f"API request failed: {str(e)}",
            "symbol": symbol
        }

@app.get("/history/{symbol}", dependencies=[Depends(verify_api_key)])
async def history_stock_data(symbol: str, start: str, end: str):
    # Validate date format
    if not validate_date_format(start) or not validate_date_format(end):
        return {
            "status": False,
            "error": "Invalid date format. Please use yyyy-MM-dd.",
            "symbol": symbol
        }

    # Validate date range
    start_date = datetime.strptime(start, "%Y-%m-%d")
    end_date = datetime.strptime(end, "%Y-%m-%d")
    if end_date <= start_date:
        return {
            "status": False,
            "error": "End date must be greater than start date.",
            "symbol": symbol
        }

    try:
        random_string = generate_random_string()
        if SESSION_PROXY == "TRUE":
            Proxy = SESSION_A + random_string + SESSION_B 
            ticker = yf.Ticker(symbol, proxy=Proxy)
            df = ticker.history(start=start, end=end, proxy=Proxy)
        else:
            ticker = yf.Ticker(symbol, proxy=HTTP_PROXY)
            df = ticker.history(start=start, end=end, proxy=HTTP_PROXY)

        if df.empty:
            return {
                "status": False,
                "error": "No data found for the given symbol and date range.",
                "symbol": symbol
            }
        
        result = json.loads(df.to_json(orient="index"))

        return {
            "status": True,
            "symbol": symbol,
            "result": result
        }
        
    except Exception as e:
        return {
            "status": False,
            "error": f"API request failed: {str(e)}",
            "symbol": symbol
        }

@app.get("/periods/{symbol}/{periods}", dependencies=[Depends(verify_api_key)])
async def periods_stock_data(symbol: str, periods: str):
    # Validate period value
    valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y']
    if periods not in valid_periods:
        return {
            "status": False,
            "error": f"Invalid period. Must be one of: {', '.join(valid_periods)}",
            "symbol": symbol
        }
    
    cache_key = f"stock_periods:{symbol}:{periods}"
    cached_data = r.get(cache_key)
    if cached_data:
        return {
            "status": True,
            "symbol": symbol,
            "result": cached_data.decode(),
            "cache": "hit"
        }
        
    try:
        random_string = generate_random_string()
        if SESSION_PROXY == "TRUE":
            Proxy = SESSION_A + random_string + SESSION_B 
            df = yf.download(symbol,period=periods,rounding=True,timeout=15,proxy=Proxy)
        else:
            df = yf.download(symbol,period=periods,rounding=True,timeout=15,proxy=HTTP_PROXY)

        if df.empty:
            return {
                "status": False,
                "error": "No data found for the given symbol and period.",
                "symbol": symbol
            }
        
        result = df.to_csv()
        result = base64.urlsafe_b64encode(result.encode()).decode()

        r.setex(cache_key, CACHE_EXPIRATION, result)
        return {
            "status": True,
            "symbol": symbol,
            "result": result
        }
        
    except Exception as e:
        return {
            "status": False,
            "error": f"API request failed: {str(e)}",
            "symbol": symbol
        }