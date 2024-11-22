import logging
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from binance.client import Client
import pandas as pd
import numpy as np
import asyncio

# .env файлс санал болгох
load_dotenv()

# Binance API түлхүүрүүд
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')

# Telegram API токен
TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')

# Binance client
client = Client(API_KEY, API_SECRET)

# Лог тохиргоо
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Хэрэглэгчийн мэдээлэл хадгалах
user_data = {}

# Криптовалют хослолууд ба интервалын сонголт
CRYPTO_PAIRS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT', 
                'DOGE/USDT', 'SOL/USDT', 'DOT/USDT', 'MATIC/USDT', 'LTC/USDT']
INTERVALS = {'1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h', '4h': '4h', '1d': '1d'}

async def start(update: Update, context: CallbackContext) -> None:
    """Эхлэл"""
    user_id = update.message.from_user.id
    user_data[user_id] = {'crypto_pair': None, 'interval': None}  # Хэрэглэгчийн мэдээлэл хадгалах

    keyboard = [
        [KeyboardButton("Топ 10 криптовалют хослол")],
        [KeyboardButton("Хослолын сигнал авах интервал")],
        [KeyboardButton("Хослол солих")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Сайн уу! Доорх сонголтуудаас нэгийг сонгоно уу:",
        reply_markup=reply_markup
    )

async def choose_crypto_pair(update: Update, context: CallbackContext) -> None:
    """Криптовалютын хослол сонгох"""
    user_id = update.message.from_user.id
    keyboard = [[KeyboardButton(pair)] for pair in CRYPTO_PAIRS]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Топ 10 криптовалют хослолуудаас сонгоно уу:",
        reply_markup=reply_markup
    )

async def set_crypto_pair(update: Update, context: CallbackContext) -> None:
    """Сонгосон хослолыг хадгалах"""
    user_id = update.message.from_user.id
    crypto_pair = update.message.text.strip()

    if crypto_pair not in CRYPTO_PAIRS:
        await update.message.reply_text("Зөвхөн жагсаалтад байгаа хослолуудыг сонгоно уу!")
        return

    user_data[user_id]['crypto_pair'] = crypto_pair
    await update.message.reply_text(
        f"Сонгосон хослол: {crypto_pair}. Одоо сигнал авах интервалыг сонгоно уу."
    )

    # Интервал сонголт харуулах
    keyboard = [[KeyboardButton(interval)] for interval in INTERVALS.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Сигнал авах интервалууд: 1m, 5m, 15m, 1h, 4h, 1d.",
        reply_markup=reply_markup
    )

async def set_interval(update: Update, context: CallbackContext) -> None:
    """Интервал сонгох"""
    user_id = update.message.from_user.id
    interval = update.message.text.strip()

    if interval not in INTERVALS:
        await update.message.reply_text("Зөвхөн жагсаалтад байгаа интервалуудыг сонгоно уу!")
        return

    user_data[user_id]['interval'] = INTERVALS[interval]
    crypto_pair = user_data[user_id]['crypto_pair']

    await update.message.reply_text(
        f"Сонгосон хослол: {crypto_pair}, интервал: {interval}. Бот сигнал илгээж эхэлнэ!"
    )
    asyncio.create_task(send_signals(update, context, user_id))

async def send_signals(update: Update, context: CallbackContext, user_id: int) -> None:
    """MACD, RSI, MA дээр үндэслэн сигнал илгээх"""
    crypto_pair = user_data[user_id]['crypto_pair']
    interval = user_data[user_id]['interval']

    while True:
        try:
            # Binance-ээс түүхэн дата авах
            klines = client.get_historical_klines(
                crypto_pair.replace("/", ""), interval, "50 minutes ago UTC"
            )
            df = pd.DataFrame(klines, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                                               'quote_asset_volume', 'number_of_trades', 'taker_buy_base',
                                               'taker_buy_quote', 'ignore'])
            df['close'] = df['close'].astype(float)

            # MACD тооцоолох
            df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
            df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
            df['macd'] = df['ema_12'] - df['ema_26']
            df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()

            # RSI тооцоолох
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            df['rsi'] = 100 - (100 / (1 + gain / loss))

            # MA тооцоолох
            df['ma_50'] = df['close'].rolling(window=50).mean()

            # Сүүлийн утгуудыг авах
            last_close = df['close'].iloc[-1]
            last_macd = df['macd'].iloc[-1]
            last_signal = df['signal'].iloc[-1]
            last_rsi = df['rsi'].iloc[-1]
            last_ma_50 = df['ma_50'].iloc[-1]

            # Сигналын логик
            if last_macd > last_signal and last_rsi < 70 and last_close > last_ma_50:
                await update.message.reply_text(f"**Авах сигнал!** {crypto_pair} одоогийн ханш: {last_close}")
            elif last_macd < last_signal and last_rsi > 30 and last_close < last_ma_50:
                await update.message.reply_text(f"**Зарах сигнал!** {crypto_pair} одоогийн ханш: {last_close}")

        except Exception as e:
            await update.message.reply_text(f"Сигнал боловсруулахад алдаа гарлаа: {e}")

        await asyncio.sleep(60)  # 1 минутын зайтай ажиллуулах

async def main() -> None:
    """Bot сервер эхлүүлэх"""
    application = Application.builder().token(TELEGRAM_API_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.Regex('Топ 10 криптовалют хослол'), choose_crypto_pair))
    application.add_handler(MessageHandler(filters.Regex('|'.join(CRYPTO_PAIRS)), set_crypto_pair))
    application.add_handler(MessageHandler(filters.Regex('|'.join(INTERVALS.keys())), set_interval))

    await application.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
