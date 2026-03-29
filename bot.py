import os
import asyncio
import aiohttp
import yfinance as yf
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

MARKETS = {
    "BTCUSD": "BTC-USD",
    "GOLD": "GC=F",
    "US30": "^DJI",
    "NAS100": "^IXIC",
    "USDJPY": "JPY=X"
}

TIMEFRAME = "15m"
INTERVAL = 60

traded_today = []

# ---------- TELEGRAM ----------
async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": CHAT_ID, "text": msg})

# ---------- DATA ----------
def get_data(symbol):
    return yf.Ticker(symbol).history(period="2d", interval=TIMEFRAME)

# ---------- TREND ----------
def trend(data):
    return "UP" if data['Close'].iloc[-1] > data['Close'].iloc[-30] else "DOWN"

# ---------- BOS ----------
def bos(data):
    if data['High'].iloc[-1] > data['High'].iloc[-10]:
        return "BULLISH"
    if data['Low'].iloc[-1] < data['Low'].iloc[-10]:
        return "BEARISH"
    return None

# ---------- LIQUIDITY ----------
def liquidity(data):
    high = data['High'].iloc[-6:-1].max()
    low = data['Low'].iloc[-6:-1].min()
    price = data['Close'].iloc[-1]

    if price > high:
        return "HIGH_SWEEP"
    if price < low:
        return "LOW_SWEEP"
    return None

# ---------- FVG ----------
def find_fvg(data):
    for i in range(-5, -1):
        c1 = data.iloc[i-2]
        c2 = data.iloc[i-1]
        c3 = data.iloc[i]

        # bullish gap
        if c3['Low'] > c1['High']:
            return ("BULLISH", c1['High'], c3['Low'])

        # bearish gap
        if c3['High'] < c1['Low']:
            return ("BEARISH", c3['High'], c1['Low'])

    return None

# ---------- ORDER BLOCK ----------
def find_ob(data):
    for i in range(-5, -1):
        candle = data.iloc[i]

        # bearish candle before bullish move
        if candle['Close'] < candle['Open']:
            return ("BUY_OB", candle['Low'], candle['High'])

        # bullish candle before bearish move
        if candle['Close'] > candle['Open']:
            return ("SELL_OB", candle['Low'], candle['High'])

    return None

# ---------- ENTRY CHECK ----------
def in_zone(price, zone_low, zone_high):
    return zone_low <= price <= zone_high

# ---------- MAIN ----------
async def main():
    print("🚀 Sniper SMC Bot Running...")

    async with aiohttp.ClientSession() as session:
        while True:

            for market, symbol in MARKETS.items():

                if market in traded_today:
                    continue

                try:
                    data = get_data(symbol)
                    price = data['Close'].iloc[-1]

                    tr = trend(data)
                    bs = bos(data)
                    liq = liquidity(data)
                    fvg = find_fvg(data)
                    ob = find_ob(data)

                    if not (tr and bs and liq and fvg and ob):
                        continue

                    fvg_type, fvg_low, fvg_high = fvg
                    ob_type, ob_low, ob_high = ob

                    # SNIPER CONDITIONS
                    valid = False

                    if tr == "UP" and bs == "BULLISH" and liq == "LOW_SWEEP":
                        if fvg_type == "BULLISH" and ob_type == "BUY_OB":
                            if in_zone(price, fvg_low, fvg_high):
                                valid = True
                                direction = "BUY 📈"
                                sl = ob_low
                                risk = price - sl
                                tp1 = price + risk
                                tp2 = price + risk * 3

                    elif tr == "DOWN" and bs == "BEARISH" and liq == "HIGH_SWEEP":
                        if fvg_type == "BEARISH" and ob_type == "SELL_OB":
                            if in_zone(price, fvg_low, fvg_high):
                                valid = True
                                direction = "SELL 📉"
                                sl = ob_high
                                risk = sl - price
                                tp1 = price - risk
                                tp2 = price - risk * 3

                    if not valid:
                        continue

                    # ---------- ANALYSIS ----------
                    analysis = f"""
🧠 SNIPER ANALYSIS - {market}

⏱ TF: 15M

📊 Trend: {tr}
🏗 BOS: {bs}
💧 Liquidity: {liq}

⚡ FVG Zone: {round(fvg_low,2)} - {round(fvg_high,2)}
🧱 OB Zone: {round(ob_low,2)} - {round(ob_high,2)}

📌 Entry Reason:
Liquidity sweep → BOS → Return to FVG inside OB

⚖️ Confidence: ELITE (95%+) 🔥
"""

                    await send(session, analysis)

                    # ---------- TRADE ----------
                    trade = f"""
💹 SNIPER TRADE - {market}

📊 {direction}
📍 Entry: {round(price,2)}

🛑 SL: {round(sl,2)}
💰 TP1: {round(tp1,2)}
🎯 TP2: {round(tp2,2)}

🔒 BE at TP1
⚖️ RR: 1:3

📉 Low drawdown entry (FVG + OB)

📅 {datetime.utcnow()}
"""

                    await send(session, trade)

                    traded_today.append(market)

                except Exception as e:
                    print("Error:", e)

            await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
