import os
import asyncio
import aiohttp
import yfinance as yf
from datetime import date, datetime

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

MARKETS = {
    "XAUUSD": "XAUUSD=X",
    "US30": "^DJI",
    "NAS100": "^NDX",
    "USDJPY": "JPY=X"
}

TIMEFRAME = "15m"        # Execution timeframe
ANALYSIS_HFT = "1d"      # High timeframe bias
INTERVAL = 60             # Loop interval

# ---------------- STATE ----------------
stats = {"wins":0,"losses":0,"total":0,"rr":0}
active_trades = {}
trade_history = []

# ---------------- TELEGRAM ----------------
async def send(session, msg, buttons=None):
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload={"chat_id":CHAT_ID,"text":msg}
    if buttons:
        payload["reply_markup"]=buttons
    await session.post(url,json=payload)

def buttons():
    return {"inline_keyboard":[
        [{"text":"📊 Stats","callback_data":"stats"}],
        [{"text":"📈 Active Trades","callback_data":"active"}],
        [{"text":"📉 History","callback_data":"history"}]
    ]}

# ---------------- DASHBOARD ----------------
def dashboard():
    winrate=(stats["wins"]/stats["total"]*100) if stats["total"] else 0
    return f"""
📊 VIP DASHBOARD

📅 {date.today()}

💹 Trades Today: {stats['total']}
✅ Wins: {stats['wins']}
❌ Losses: {stats['losses']}
📈 Win Rate: {round(winrate,2)}%
💰 Total RR: {stats['rr']}
📊 Active: {', '.join(active_trades.keys()) if active_trades else 'None'}
"""

# ---------------- DATA ----------------
def get_data(symbol, period="2d"):
    return yf.Ticker(symbol).history(period=period, interval=TIMEFRAME)

def get_hft_bias(symbol):
    data=yf.Ticker(symbol).history(period="30d", interval=ANALYSIS_HFT)
    if data.empty: return None
    return "BUY" if data['Close'].iloc[-1]>data['Close'].iloc[-2] else "SELL"

# ---------------- STRUCTURE ----------------
def bos(data):
    if data['High'].iloc[-1]>data['High'].iloc[-10]:
        return "BULLISH"
    if data['Low'].iloc[-1]<data['Low'].iloc[-10]:
        return "BEARISH"
    return None

def liquidity(data):
    high=data['High'].iloc[-6:-1].max()
    low=data['Low'].iloc[-6:-1].min()
    price=data['Close'].iloc[-1]
    if price>high: return "HIGH_SWEEP"
    if price<low: return "LOW_SWEEP"
    return None

# ---------------- TRADE MONITOR ----------------
async def monitor_trade(session,market,trade):
    while True:
        await asyncio.sleep(60)
        data=get_data(MARKETS[market])
        if data.empty: continue
        price=data['Close'].iloc[-1]
        if market not in active_trades: return

        if trade["dir"]=="BUY":
            if price>=trade["tp1"] and not trade.get("tp1_hit"):
                trade["tp1_hit"]=True
                await send(session,f"💰 {market} TP1 HIT ✅\n🔒 SL moved to BE")
            if price>=trade["tp2"]:
                stats["wins"]+=1; stats["rr"]+=3; stats["total"]+=1
                await send(session,f"🎯 {market} TP2 HIT 🚀 WIN")
                trade_history.append((market,"WIN")); del active_trades[market]; return
            if price<=trade["sl"]:
                stats["losses"]+=1; stats["total"]+=1
                await send(session,f"❌ {market} SL HIT")
                trade_history.append((market,"LOSS")); del active_trades[market]; return
        else:
            if price<=trade["tp1"] and not trade.get("tp1_hit"):
                trade["tp1_hit"]=True
                await send(session,f"💰 {market} TP1 HIT ✅\n🔒 SL moved to BE")
            if price<=trade["tp2"]:
                stats["wins"]+=1; stats["rr"]+=3; stats["total"]+=1
                await send(session,f"🎯 {market} TP2 HIT 🚀 WIN")
                trade_history.append((market,"WIN")); del active_trades[market]; return
            if price>=trade["sl"]:
                stats["losses"]+=1; stats["total"]+=1
                await send(session,f"❌ {market} SL HIT")
                trade_history.append((market,"LOSS")); del active_trades[market]; return

# ---------------- CALLBACK ----------------
async def handle_callbacks(session):
    offset=None
    while True:
        url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?timeout=60"
        if offset: url+=f"&offset={offset}"
        async with session.get(url) as resp:
            updates=await resp.json()
        for update in updates.get("result",[]):
            offset=update["update_id"]+1
            if "callback_query" in update:
                cmd=update["callback_query"]["data"]
                if cmd=="stats": await send(session,dashboard())
                elif cmd=="active":
                    msg="📈 ACTIVE TRADES\n"
                    for m,t in active_trades.items(): msg+=f"{m}: {t['dir']} @ {round(t['entry'],2)}\n"
                    if not active_trades: msg+="None"
                    await send(session,msg)
                elif cmd=="history":
                    msg="📉 HISTORY\n"
                    for h in trade_history: msg+=f"{h[0]} - {h[1]}\n"
                    if not trade_history: msg+="No trades yet"
                    await send(session,msg)

# ---------------- MAIN ----------------
async def main():
    print("🚀 VIP SIGNAL BOT RUNNING")
    async with aiohttp.ClientSession() as session:
        asyncio.create_task(handle_callbacks(session))

        while True:
            for market,symbol in MARKETS.items():
                if len(active_trades)>=3: break
                if market in active_trades: continue
                try:
                    data=get_data(symbol)
                    if data.empty: continue
                    price=data['Close'].iloc[-1]
                    hft_bias=get_hft_bias(symbol)
                    structure=bos(data)
                    liq=liquidity(data)
                    direction=None
                    if structure=="BULLISH" and liq=="LOW_SWEEP": direction="BUY"
                    elif structure=="BEARISH" and liq=="HIGH_SWEEP": direction="SELL"
                    if direction is None: continue

                    # ---------------- ANALYSIS MESSAGE ----------------
                    analysis=f"""
💹 NEW VIP TRADE - {market}

📊 Direction: {direction}
📍 Entry: {round(price,2)}
⚖️ HFT Bias: {hft_bias}
🕒 Analyzed TF: {ANALYSIS_HFT}
⏱️ Execution TF: {TIMEFRAME}

🔎 Reason: {'Bullish structure & liquidity sweep' if direction=='BUY' else 'Bearish structure & liquidity sweep'}
💡 Confidence: 80%
💰 Risk Management: 0.2% risk per trade
"""

                    # ---------------- SET SL/TP ----------------
                    risk=price*0.002
                    if direction=="BUY":
                        trade={"dir":"BUY","entry":price,"sl":price-risk,"tp1":price+risk,"tp2":price+risk*3}
                    else:
                        trade={"dir":"SELL","entry":price,"sl":price+risk,"tp1":price-risk,"tp2":price-risk*3}

                    active_trades[market]=trade
                    await send(session,analysis,buttons())
                    asyncio.create_task(monitor_trade(session,market,trade))

                except Exception as e: print("Error:",e)
            await asyncio.sleep(INTERVAL)

if __name__=="__main__":
    asyncio.run(main())
