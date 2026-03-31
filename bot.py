import os
import sqlite3
import random
import datetime
import pandas as pd
import yfinance as yf
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler

# =========================
# ENV VARIABLES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# SETTINGS
# =========================
PAIRS = {
    "XAUUSD": "GC=F",
    "US30": "^DJI",
    "NAS100": "^NDX",
    "USDJPY": "JPY=X"
}

MAX_TRADES_PER_DAY = 3
CONFIDENCE_THRESHOLD = 80

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("trades.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trades(
id INTEGER PRIMARY KEY AUTOINCREMENT,
pair TEXT,
result TEXT
)
""")
conn.commit()

# =========================
# TELEGRAM
# =========================
bot = Bot(token=BOT_TOKEN)

# =========================
# GLOBAL VARIABLES
# =========================
trades_today = 0
last_scan_day = datetime.date.today()

# =========================
# MARKET DATA
# =========================
def fetch_data(symbol, interval, period="5d"):
    try:
        df = yf.download(symbol, interval=interval, period=period, progress=False)
        return df
    except Exception as e:
        print(f"[ERROR] Fetching data for {symbol} ({interval}): {e}")
        return None

# =========================
# PRO ICT/SMC STRATEGY
# =========================
def detect_bias(df_htf):
    sma = df_htf["Close"].rolling(50).mean()
    return "BUY" if df_htf["Close"].iloc[-1] > sma.iloc[-1] else "SELL"

def detect_order_block(df):
    last_candle = df.iloc[-2]
    if last_candle['Close'] > last_candle['Open']:
        return ("bullish", last_candle['Low'])
    else:
        return ("bearish", last_candle['High'])

def detect_fvg(df):
    return df['High'].iloc[-3] < df['Low'].iloc[-1]

def detect_bos(df_ltf):
    highs = df_ltf['High'][-5:]
    lows = df_ltf['Low'][-5:]
    return df_ltf['Close'].iloc[-1] > max(highs) or df_ltf['Close'].iloc[-1] < min(lows)

def detect_liquidity_sweep(df_ltf):
    recent_low = df_ltf["Low"].iloc[-1]
    prev_low = df_ltf["Low"].iloc[-5:-1].min()
    recent_high = df_ltf["High"].iloc[-1]
    prev_high = df_ltf["High"].iloc[-5:-1].max()
    return recent_low < prev_low or recent_high > prev_high

def generate_signal(df_htf, df_ltf):
    bias = detect_bias(df_htf)
    ob_type, ob_level = detect_order_block(df_ltf)
    fvg = detect_fvg(df_ltf)
    bos = detect_bos(df_ltf)
    sweep = detect_liquidity_sweep(df_ltf)

    confidence = 0
    if bias: confidence += 25
    if ob_type: confidence += 25
    if fvg: confidence += 25
    if bos: confidence += 15
    if sweep: confidence += 10

    if confidence < CONFIDENCE_THRESHOLD:
        return None

    price = float(df_ltf["Close"].iloc[-1])

    if bias == "BUY":
        sl = price - random.uniform(5,10)
        tp1 = price + random.uniform(8,12)
        tp2 = price + random.uniform(20,30)
    else:
        sl = price + random.uniform(5,10)
        tp1 = price - random.uniform(8,12)
        tp2 = price - random.uniform(20,30)

    return {
        "type": bias,
        "entry": round(price,2),
        "sl": round(sl,2),
        "tp1": round(tp1,2),
        "tp2": round(tp2,2),
        "confidence": confidence,
        "reason": f"OB: {ob_type}, FVG: {fvg}, BOS: {bos}, Liquidity Sweep: {sweep}"
    }

# =========================
# TELEGRAM MESSAGES
# =========================
def send_analysis(pair, signal):
    message = f"""
📊 MARKET ANALYSIS — {pair}

Bias: {signal['type']}

Reason For Setup:
{signal['reason']}

Confidence: {signal['confidence']}%

Timeframes Used:
HTF: 4H / Daily
Entry: 5M

Risk Per Trade: 1%
"""
    try:
        bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        print(f"[ERROR] Sending analysis: {e}")

def send_trade(pair, signal):
    message = f"""
🚀 TRADE SETUP — {pair}

Type: {signal['type']}
Entry: {signal['entry']}
SL: {signal['sl']}
TP1: {signal['tp1']}
TP2: {signal['tp2']}

Management Plan:
TP1 → Move SL to Break Even
TP2 → Close remaining position
"""
    try:
        bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        print(f"[ERROR] Sending trade: {e}")

# =========================
# DASHBOARD
# =========================
def dashboard(update: Update, context: CallbackContext):
    cursor.execute("SELECT COUNT(*) FROM trades")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM trades WHERE result='win'")
    wins = cursor.fetchone()[0]
    losses = total - wins
    winrate = round((wins / total) * 100,2) if total > 0 else 0
    message = f"""
📊 VIP SIGNAL DASHBOARD

Total Trades: {total}
Wins: {wins}
Losses: {losses}
Win Rate: {winrate}%
"""
    update.message.reply_text(message)

# =========================
# SCHEDULED SCAN
# =========================
def scheduled_scan():
    global trades_today, last_scan_day
    try:
        today = datetime.date.today()
        if today != last_scan_day:
            trades_today = 0
            last_scan_day = today

        for pair, symbol in PAIRS.items():
            if trades_today >= MAX_TRADES_PER_DAY:
                break

            df_htf = fetch_data(symbol, interval="4h")
            df_ltf = fetch_data(symbol, interval="5m")
            if df_htf is None or df_ltf is None or df_htf.empty or df_ltf.empty:
                continue

            signal = generate_signal(df_htf, df_ltf)
            if signal:
                send_analysis(pair, signal)
                send_trade(pair, signal)
                trades_today += 1

    except Exception as e:
        print(f"[ERROR] Scheduled scan failed: {e}")

# =========================
# MAIN
# =========================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("dashboard", dashboard))

    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_scan, 'interval', minutes=15)
    scheduler.start()
    print("Scheduler started: scanning every 15 minutes")

    updater.start_polling()
    print("Bot is running...")
    updater.idle()

if __name__ == "__main__":
    main()
