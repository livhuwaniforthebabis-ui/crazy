import os
import asyncio
import aiohttp
import yfinance as yf
from datetime import datetime, date

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

stats = {"wins": 0, "losses": 0, "total": 0, "rr": 0}
active_trades = {}
trade_history = []

# ---------- TELEGRAM ----------
async def send(session, msg, buttons=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}

    if buttons:
        payload["reply_markup"] = buttons

    await session.post(url, json=payload)

# ---------- DASHBOARD ----------
def dashboard():
    winrate = (stats["wins"]/stats["total"]*100) if stats["total"] else 0
    return f"""
📊 DAILY DASHBOARD

📅 {date.today()}

💹 Trades: {stats['total']}
✅ Wins: {stats['wins']}
❌ Losses: {stats['losses']}
📈 Win Rate: {round(winrate,2)}%

💰 RR Gained: {stats['rr']}

📊 Markets:
{", ".join(active_trades.keys()) if active_trades else "None"}
"""

# ---------- BUTTONS ----------
def buttons():
    return {
        "inline_keyboard": [
            [{"text": "📊 Stats", "callback_data": "stats"}],
            [{"text": "📈 Active Trades", "callback_data": "active"}],
            [{"text": "📉 History", "callback_data": "history"}]
        ]
    }

# ---------- DATA ----------
def get_data(symbol):
    return yf.Ticker(symbol).history(period="2d", interval=TIMEFRAME)

# ---------- SIMPLE SMC FILTER ----------
def valid_setup(data):
    return True  # use your SMC logic here

# ---------- TRACK TRADE ----------
async def monitor_trade(session, market, trade):
    while True:
        await asyncio.sleep(60)

        data = get_data(MARKETS[market])
        price = data['Close'].iloc[-1]

        if market not in active_trades:
            return

        if trade["dir"] == "BUY":
            if price >= trade["tp1"] and not trade.get("tp1_hit"):
                trade["tp1_hit"] = True
                await send(session, f"💰 {market} TP1 HIT ✅\n🔒 SL moved to BE")

            if price >= trade["tp2"]:
                stats["wins"] += 1
                stats["rr"] += 3
                stats["total"] += 1
                await send(session, f"🎯 {market} TP2 HIT 🚀 FULL WIN ✅")
                trade_history.append((market, "WIN"))
                del active_trades[market]
                return

            if price <= trade["sl"]:
                stats["losses"] += 1
                stats["total"] += 1
                await send(session, f"❌ {market} STOP LOSS HIT")
                trade_history.append((market, "LOSS"))
                del active_trades[market]
                return

        else:
            if price <= trade["tp1"] and not trade.get("tp1_hit"):
                trade["tp1_hit"] = True
                await send(session, f"💰 {market} TP1 HIT ✅\n🔒 SL moved to BE")

            if price <= trade["tp2"]:
                stats["wins"] += 1
                stats["rr"] += 3
                stats["total"] += 1
                await send(session, f"🎯 {market} TP2 HIT 🚀 FULL WIN ✅")
                trade_history.append((market, "WIN"))
                del active_trades[market]
                return

            if price >= trade["sl"]:
                stats["losses"] += 1
                stats["total"] += 1
                await send(session, f"❌ {market} STOP LOSS HIT")
                trade_history.append((market, "LOSS"))
                del active_trades[market]
                return

# ---------- MAIN ----------
async def main():
    print("🚀 Dashboard Bot Running...")

    async with aiohttp.ClientSession() as session:

        # Send dashboard every hour
        asyncio.create_task(periodic_dashboard(session))

        while True:
            for market, symbol in MARKETS.items():

                if len(active_trades) >= 3:
                    break

                if market in active_trades:
                    continue

                try:
                    data = get_data(symbol)
                    price = data['Close'].iloc[-1]

                    if not valid_setup(data):
                        continue

                    risk = price * 0.002

                    trade = {
                        "dir": "BUY",
                        "entry": price,
                        "sl": price - risk,
                        "tp1": price + risk,
                        "tp2": price + risk * 3
                    }

                    active_trades[market] = trade

                    msg = f"""
💹 NEW TRADE - {market}

📍 Entry: {round(price,2)}
🛑 SL: {round(trade['sl'],2)}
💰 TP1: {round(trade['tp1'],2)}
🎯 TP2: {round(trade['tp2'],2)}

⚖️ RR: 1:3
"""

                    await send(session, msg, buttons())

                    asyncio.create_task(monitor_trade(session, market, trade))

                except Exception as e:
                    print("Error:", e)

            await asyncio.sleep(INTERVAL)

# ---------- PERIODIC DASHBOARD ----------
async def periodic_dashboard(session):
    while True:
        await asyncio.sleep(3600)
        await send(session, dashboard(), buttons())

if __name__ == "__main__":
    asyncio.run(main())
