import os
import asyncio
import aiohttp
import yfinance as yf
from datetime import datetime

# Telegram settings
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

if not TELEGRAM_TOKEN or not CHAT_ID:
    raise ValueError("Set TELEGRAM_TOKEN and CHAT_ID as environment variables.")

# Markets
MARKETS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "SP500": "SPY",
    "DAX": "^GDAXI",
    "NASDAQ": "^IXIC",
    "GOLD": "GC=F",
    "OIL": "CL=F",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "BNB": "BNB-USD"
}

# Tracking previous state
previous_prices = {m: None for m in MARKETS}
previous_signals = {m: None for m in MARKETS}

INTERVAL = 60  # seconds
BREAKOUT_THRESHOLD = 0.001  # 0.1% price breakout

# Send Telegram messages
async def send_telegram(session, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        async with session.post(url, data={"chat_id": CHAT_ID, "text": message}) as resp:
            await resp.text()
    except Exception as e:
        print("Telegram error:", e)

# Fetch latest price
async def fetch_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d", interval="1m")
        if not data.empty:
            return float(data['Close'].iloc[-1])
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
    return None

# Generate full trade signal
def generate_trade_signal(price, prev_price, market):
    if prev_price is None:
        return None  # Skip first iteration

    # Determine direction
    if price > prev_price * (1 + BREAKOUT_THRESHOLD):
        direction = "BUY 📈"
        reason = "Price broke above recent high 🔝"
        sl = round(prev_price, 4)
        tp = round(price + (price - sl) * 2, 4)
        rr = round((tp - price) / (price - sl), 2)
    elif price < prev_price * (1 - BREAKOUT_THRESHOLD):
        direction = "SELL 📉"
        reason = "Price broke below recent low 🔻"
        sl = round(prev_price, 4)
        tp = round(price - (sl - price) * 2, 4)
        rr = round((price - tp) / (sl - price), 2)
    else:
        return None  # No trade

    return {
        "market": market,
        "price": price,
        "direction": direction,
        "reason": reason,
        "sl": sl,
        "tp": tp,
        "rr": rr
    }

# Main loop
async def main():
    print("🚀 Professional Trade Signal Bot started...")
    async with aiohttp.ClientSession() as session:
        while True:
            for market, symbol in MARKETS.items():
                price = await fetch_price(symbol)
                if price is None:
                    continue

                trade = generate_trade_signal(price, previous_prices[market], market)
                if trade and trade != previous_signals[market]:
                    msg = f"""
💹 {trade['market']}
Entry: {trade['direction']} at {trade['price']:.4f}
Reason: {trade['reason']}
Stop-Loss: {trade['sl']} 🛑
Take-Profit: {trade['tp']} 🎯
Risk/Reward: {trade['rr']} ⚖️
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
                    await send_telegram(session, msg)
                    previous_signals[market] = trade

                previous_prices[market] = price
            await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
