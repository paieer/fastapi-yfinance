from fastapi import FastAPI, Depends, HTTPException, Header
import requests
import yfinance as yf
import os
import random
import string
import json
from datetime import datetime
import redis
from cachetools import cached, LRUCache, TTLCache
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
CACHE_EXPIRATION_SHORT = int(os.getenv("CACHE_EXPIRATION_SHORT", 10*60)) 
CACHE_EXPIRATION_LONG = int(os.getenv("CACHE_EXPIRATION_LONG", 3600*23)) 
SESSION_PROXY= os.getenv("SESSION_PROXY", "").strip() or None
SESSION_A= os.getenv("SESSION_A", "").strip() or None
SESSION_B= os.getenv("SESSION_B", "").strip() or None
polygon_api_key = os.getenv("POLYGON_API_KEY", "").strip() or None

HTTP_PROXY = os.getenv("HTTP_PROXY", "").strip() or None
VALID_API_KEY = os.getenv("API_KEY", "default-secret-key").strip()

def validate_date_format(date_str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def generate_random_string(length=8):
    # letters_and_digits = string.ascii_letters + string.digits
    return ''.join(random.choice(string.digits) for i in range(length))


@cached(cache=TTLCache(maxsize=500, ttl=3600*24))
def get_polygon_grouped_daily(date):
    """
    Fetch grouped daily stock data from Polygon API for a specific date.
    https://polygon.io/docs/stocks/getting-started

    This function retrieves aggregated daily stock data for all US stocks on a given date
    using the Polygon.io API.

    Args:
        date (str): The date to get data for in the format 'YYYY-MM-DD'

    Returns:
        dict: JSON response from Polygon API containing the grouped daily stock data.
              The response includes aggregated metrics like open, close, high, low prices
              and volume for all US stocks on the specified date.
    """
    url = f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=true&apiKey={polygon_api_key}"
    response = requests.get(url)
    data = response.json()
    return data

async def verify_api_key(api_key: str = Header(..., alias="X-API-Key")):
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )
    return api_key

@app.get("/market/stocks/{date}")
async def get_entire_stocks_daily(date: str):
    """
    获取指定日期的所有美股的数据。
    Args:
        date (str): 日期，格式为 'YYYY-MM-DD'。
    Returns:
        dict: 包含所有美股日线数据的字典。
    """
    # Validate date format
    if not validate_date_format(date):
        return {
            "status": False,
            "error": "Invalid date format. Please use YYYY-MM-DD"
        }
    
    # Check if date is not greater than current date
    try:
        input_date = datetime.strptime(date, "%Y-%m-%d")
        current_date = datetime.now()
        if input_date.date() > current_date.date():
            return {
                "status": False,
                "error": "Date cannot be in the future"
            }
    except ValueError as e:
        return {
            "status": False,
            "error": f"Invalid date: {str(e)}"
        }
    
    try:
        data = get_polygon_grouped_daily(date)
        if data['status'] != "OK":
            return {
                "status": False,
                "error": data
            }
        return {
            "status": True,
            "date": date,
            "result": data
        }
    except Exception as e:
        return {
            "status": False,
            "error": f"API request failed: {str(e)}"
        }

@app.get("/tickers/{symbol}", dependencies=[Depends(verify_api_key)])
async def get_stock_info(symbol: str):
    symbol = symbol.upper()
    cache_key = f"stock_ticker_info:{symbol}"
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
        
        r.setex(cache_key, CACHE_EXPIRATION_LONG, json.dumps(result))
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
    symbol = symbol.upper()
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
    symbol = symbol.upper()
    valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y','ytd', 'max']
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
            "result": cached_data,
            "cache": "hit"
        }
        
    try:
        intervals = "1d"
        if periods == "1d":
            intervals = "30m"

        random_string = generate_random_string()
        if SESSION_PROXY == "TRUE":
            Proxy = SESSION_A + random_string + SESSION_B 
            df = yf.download(symbol,period=periods,interval=intervals,rounding=True,proxy=Proxy)
        else:
            df = yf.download(symbol,period=periods,interval=intervals,rounding=True,proxy=HTTP_PROXY)

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
        r.setex(cache_key, CACHE_EXPIRATION_LONG, json.dumps(tickers))
        return {
            "status": True,
            "result": tickers
        }

    except Exception as e:
        return {
            "status": False,
            "error": f"request failed: {str(e)}"
        }