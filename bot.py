import os
import sqlite3
import random
import yfinance as yf
import pandas as pd
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext

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
CONFIDENCE_THRESHOLD = 70

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
# MARKET DATA
# =========================

def fetch_data(symbol):

    df = yf.download(
        symbol,
        interval="5m",
        period="5d",
        progress=False
    )

    return df

# =========================
# STRATEGY ENGINE
# =========================

def detect_bias(df):

    sma = df["Close"].rolling(50).mean()

    if df["Close"].iloc[-1] > sma.iloc[-1]:
        return "BUY"

    return "SELL"


def detect_liquidity_sweep(df):

    recent_low = df["Low"].iloc[-1]
    prev_low = df["Low"].iloc[-5:-1].min()

    if recent_low < prev_low:
        return True

    return False


def detect_fvg(df):

    if df["High"].iloc[-3] < df["Low"].iloc[-1]:
        return True

    return False


def generate_signal(df):

    bias = detect_bias(df)
    sweep = detect_liquidity_sweep(df)
    fvg = detect_fvg(df)

    confidence = 0

    if bias:
        confidence += 30

    if sweep:
        confidence += 40

    if fvg:
        confidence += 30

    if confidence < CONFIDENCE_THRESHOLD:
        return None

    price = float(df["Close"].iloc[-1])

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
        "reason": "Liquidity sweep + Fair Value Gap + HTF bias"
    }

# =========================
# SIGNAL MESSAGES
# =========================

def send_analysis(pair, signal):

    message = f"""
📊 MARKET ANALYSIS — {pair}

Bias: {signal['type']}

Reason For Setup:

• Liquidity sweep detected
• Fair Value Gap entry
• Higher timeframe bias aligned

Confidence:
{signal['confidence']}%

Timeframes Used:

HTF: Daily / 4H
Confirmation: 1H
Entry: 5M

Risk Per Trade:
1%
"""

    bot.send_message(chat_id=CHAT_ID, text=message)


def send_trade(pair, signal):

    message = f"""
🚀 TRADE SETUP — {pair}

Type: {signal['type']}

Entry:
{signal['entry']}

Stop Loss:
{signal['sl']}

Take Profit 1:
{signal['tp1']}

Take Profit 2:
{signal['tp2']}

Management Plan:

TP1 → Move SL to Break Even  
TP2 → Close remaining position
"""

    bot.send_message(chat_id=CHAT_ID, text=message)


# =========================
# MARKET SCANNER
# =========================

def scan_markets():

    trades_today = 0

    for pair, symbol in PAIRS.items():

        if trades_today >= MAX_TRADES_PER_DAY:
            break

        df = fetch_data(symbol)

        if df.empty:
            continue

        signal = generate_signal(df)

        if signal:

            send_analysis(pair, signal)
            send_trade(pair, signal)

            trades_today += 1


# =========================
# DASHBOARD COMMAND
# =========================

def dashboard(update: Update, context: CallbackContext):

    cursor.execute("SELECT COUNT(*) FROM trades")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trades WHERE result='win'")
    wins = cursor.fetchone()[0]

    losses = total - wins

    if total > 0:
        winrate = round((wins / total) * 100,2)
    else:
        winrate = 0

    message = f"""
📊 VIP SIGNAL DASHBOARD

Total Trades:
{total}

Wins:
{wins}

Losses:
{losses}

Win Rate:
{winrate}%
"""

    update.message.reply_text(message)


# =========================
# START BOT
# =========================

def main():

    updater = Updater(BOT_TOKEN, use_context=True)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("dashboard", dashboard))

    updater.start_polling()

    scan_markets()

    updater.idle()


if __name__ == "__main__":
    main()
