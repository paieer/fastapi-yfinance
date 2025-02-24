from fastapi import FastAPI, Depends, HTTPException, Header
import requests
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
            df = yf.download(symbol,period=periods,rounding=True,proxy=Proxy)
        else:
            df = yf.download(symbol,period=periods,rounding=True,proxy=HTTP_PROXY)

        if df.empty:
            return {
                "status": False,
                "error": "No data found for the given symbol and period.",
                "symbol": symbol
            }
        
        result = df.to_csv()
        result = base64.urlsafe_b64encode(result.encode()).decode().replace('=', '')

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

@app.get("/stock/symbol/all")
def get_all_us_stock_tickers():
    """
    获取所有美股股票的代码 (tickers)。
    Returns:
        list: 包含所有美股股票代码的列表。
    """

    cache_key = "all_stock_tickers"
    cached_data = r.get(cache_key)
    if cached_data:
        return {
        "status": True,
        "result": json.loads(cached_data),
        "cache": "hit"
        }
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.nasdaq.com/',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'application/json'
        }
        
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=9999"
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        df = data['data']['table']['rows']
        tickers = [row['symbol'] for row in df]
        
        # 过滤逻辑： 指数一般含有 "^" 字符
        tickers = [ticker for ticker in tickers if "^" not in ticker]
        
        # Replace "/" with "-" in tickers
        tickers = [ticker.replace("/", "-") for ticker in tickers]

        # If no cache, store the result in Redis
        r.setex(cache_key, CACHE_EXPIRATION, json.dumps(tickers))
        return {
            "status": True,
            "result": tickers
        }

    except Exception as e:
        return {
            "status": False,
            "error": f"request failed: {str(e)}"
        }