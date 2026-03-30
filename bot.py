import os
import asyncio
import aiohttp
import yfinance as yf
from datetime import datetime, date

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

# ✅ FIXED SYMBOLS
MARKETS = {
    "BTCUSD": "BTC-USD",
    "GOLD": "XAUUSD=X",
    "US30": "^DJI",
    "NAS100": "^NDX",
    "USDJPY": "JPY=X"
}

TIMEFRAME = "15m"
INTERVAL = 60

# ---------- STATE ----------
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

📊 Active Markets:
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
    data = yf.Ticker(symbol).history(period="2d", interval=TIMEFRAME)
    return data

# ---------- SMC LOGIC ----------
def get_trend(data):
    return "BUY" if data['Close'].iloc[-1] > data['Close'].iloc[-30] else "SELL"

def bos(data):
    if data['High'].iloc[-1] > data['High'].iloc[-10]:
        return "BULLISH"
    if data['Low'].iloc[-1] < data['Low'].iloc[-10]:
        return "BEARISH"
    return None

def liquidity(data):
    high = data['High'].iloc[-6:-1].max()
    low = data['Low'].iloc[-6:-1].min()
    price = data['Close'].iloc[-1]

    if price > high:
        return "HIGH_SWEEP"
    if price < low:
        return "LOW_SWEEP"
    return None

# ---------- HIGH PROBABILITY ----------
def valid_setup(trend, structure, liq):
    return (
        (trend == "BUY" and structure == "BULLISH" and liq == "LOW_SWEEP") or
        (trend == "SELL" and structure == "BEARISH" and liq == "HIGH_SWEEP")
    )

# ---------- MONITOR ----------
async def monitor_trade(session, market, trade):
    while True:
        await asyncio.sleep(60)
        data = get_data(MARKETS[market])

        if data.empty:
            continue

        price = data['Close'].iloc[-1]

        if market not in active_trades:
            return

        if trade["dir"] == "BUY":
            if price >= trade["tp1"] and not trade.get("tp1_hit"):
                trade["tp1_hit"] = True
                await send(session, f"💰 {market} TP1 HIT ✅\n🔒 BE Activated")

            if price >= trade["tp2"]:
                stats["wins"] += 1
                stats["rr"] += 3
                stats["total"] += 1
                await send(session, f"🎯 {market} TP2 HIT 🚀 WIN")
                trade_history.append((market, "WIN"))
                del active_trades[market]
                return

            if price <= trade["sl"]:
                stats["losses"] += 1
                stats["total"] += 1
                await send(session, f"❌ {market} SL HIT")
                trade_history.append((market, "LOSS"))
                del active_trades[market]
                return

        else:
            if price <= trade["tp1"] and not trade.get("tp1_hit"):
                trade["tp1_hit"] = True
                await send(session, f"💰 {market} TP1 HIT ✅\n🔒 BE Activated")

            if price <= trade["tp2"]:
                stats["wins"] += 1
                stats["rr"] += 3
                stats["total"] += 1
                await send(session, f"🎯 {market} TP2 HIT 🚀 WIN")
                trade_history.append((market, "WIN"))
                del active_trades[market]
                return

            if price >= trade["sl"]:
                stats["losses"] += 1
                stats["total"] += 1
                await send(session, f"❌ {market} SL HIT")
                trade_history.append((market, "LOSS"))
                del active_trades[market]
                return

# ---------- CALLBACKS ----------
async def handle_callbacks(session):
    offset = None
    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?timeout=60"
        if offset:
            url += f"&offset={offset}"
        async with session.get(url) as resp:
            updates = await resp.json()

        for update in updates.get("result", []):
            offset = update["update_id"] + 1

            if "callback_query" in update:
                command = update["callback_query"]["data"]

                if command == "stats":
                    await send(session, dashboard())

                elif command == "active":
                    msg = "📊 ACTIVE TRADES\n"
                    for m, t in active_trades.items():
                        msg += f"{m}: {t['dir']} @ {round(t['entry'],2)}\n"
                    if not active_trades:
                        msg += "None"
                    await send(session, msg)

                elif command == "history":
                    msg = "📉 HISTORY\n"
                    for h in trade_history:
                        msg += f"{h[0]} - {h[1]}\n"
                    if not trade_history:
                        msg += "No trades"
                    await send(session, msg)

# ---------- MAIN ----------
async def main():
    print("🚀 FINAL SMC BOT RUNNING")

    async with aiohttp.ClientSession() as session:
        asyncio.create_task(handle_callbacks(session))

        while True:
            for market, symbol in MARKETS.items():

                if len(active_trades) >= 3:
                    break

                if market in active_trades:
                    continue

                try:
                    data = get_data(symbol)

                    if data.empty:
                        print(f"{market} ❌ No data")
                        continue

                    price = data['Close'].iloc[-1]

                    tr = get_trend(data)
                    st = bos(data)
                    liq = liquidity(data)

                    print(f"{market} | {tr} | {st} | {liq}")

                    if not valid_setup(tr, st, liq):
                        continue

                    risk = price * 0.002

                    if tr == "BUY":
                        trade = {
                            "dir": "BUY",
                            "entry": price,
                            "sl": price - risk,
                            "tp1": price + risk,
                            "tp2": price + risk * 3
                        }
                    else:
                        trade = {
                            "dir": "SELL",
                            "entry": price,
                            "sl": price + risk,
                            "tp1": price - risk,
                            "tp2": price - risk * 3
                        }

                    active_trades[market] = trade

                    msg = f"""
💹 NEW TRADE - {market}

📊 Direction: {trade['dir']}
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

if __name__ == "__main__":
    asyncio.run(main())
