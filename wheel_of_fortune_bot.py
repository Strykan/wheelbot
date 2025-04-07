import logging
import os
import random
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from dotenv import load_dotenv
from database import Database

# Инициализация
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DAILY_BONUS = 1
MAX_ATTEMPTS_PER_SPIN = 1
MAX_PAYMENT_AMOUNT = 10000

# Инициализация базы данных
db = Database()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def init_db():
    """Инициализация подключения к БД"""
    await db.connect()

# Клавиатуры
def get_start_keyboard(user_id=None):
    buttons = [
        [InlineKeyboardButton("🎰 Начать игру", callback_data="play")],
        [InlineKeyboardButton("ℹ️ Мои попытки", callback_data="check_attempts")],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily_bonus")],
        [InlineKeyboardButton("👥 Реферальная программа", callback_data="referral_info")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton("🛠 Панель администратора", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def get_play_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Крутить колесо (1 попытка)", callback_data="spin_wheel")],
        [InlineKeyboardButton("💰 Купить еще попыток", callback_data="buy_attempts")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]
    ])

def get_payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 попытка — 50 руб", callback_data="pay_1")],
        [InlineKeyboardButton("3 попытки — 130 руб (↘️10%)", callback_data="pay_3")],
        [InlineKeyboardButton("5 попыток — 200 руб (↘️20%)", callback_data="pay_5")],
        [InlineKeyboardButton("10 попыток — 350 руб (↘️30%)", callback_data="pay_10")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]
    ])

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    if args and args[0].startswith('ref'):
        referral_code = args[0][3:]
        if await db.process_referral(user.id, referral_code):
            await update.message.reply_text(
                "🎉 Вы получили +1 попытку за регистрацию по реферальной ссылке!",
                parse_mode=ParseMode.HTML
            )
    
    ref_info = await db.get_referral_info(user.id)
    if ref_info and not ref_info['code']:
        await db.generate_referral_code(user.id)
    
    await update.message.reply_text(
        "🎡 Добро пожаловать в <b>Колесо Фортуны</b>!\n\n"
        "💎 Крутите колесо и выигрывайте призы!\n"
        "💰 Попытки можно купить, получить за рефералов или ежедневный бонус.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard(user.id)
    )

async def spin_wheel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    attempts = await db.get_user_attempts(user_id)
    
    if attempts['remaining'] <= 0:
        await query.answer("❌ У вас нет доступных попыток!", show_alert=True)
        return
    
    if not await db.update_user_attempts(user_id=user_id, used=1):
        await query.answer("❌ Ошибка при использовании попытки", show_alert=True)
        return
    
    wheel_segments = ["🍒", "🍋", "🍊", "🍇", "🍉", "💰", "🎁", "⭐", "🍀"]
    segment_weights = [15, 15, 15, 15, 10, 5, 5, 10, 10]
    
    selected_index = random.choices(range(len(wheel_segments)), weights=segment_weights, k=1)[0]
    selected_segment = wheel_segments[selected_index]
    
    prize_mapping = {
        "🍒": ("10 рублей", "money", "10"),
        "🍋": ("20 рублей", "money", "20"),
        "🍊": ("Бесплатная попытка", "attempt", "1"),
        "🍇": ("5 рублей", "money", "5"),
        "🍉": ("Конфетка", "other", "candy"),
        "💰": ("100 рублей", "money", "100"),
        "🎁": ("Подарок", "other", "gift"),
        "⭐": ("5 бесплатных попыток", "attempt", "5"),
        "🍀": ("Скидка 10% на след. игру", "discount", "10")
    }
    prize_name, prize_type, prize_value = prize_mapping.get(selected_segment, ("Ничего", "other", "none"))
    
    await db.add_prize(user_id, prize_type, prize_value)
    
    message = await query.message.reply_text(
        "🎡 <b>Колесо Фортуны</b>\n\n"
        f"{' ' * 8}👆\n"
        f"{' '.join(wheel_segments)}\n\n"
        "🌀 Крутим колесо...",
        parse_mode=ParseMode.HTML
    )
    
    # Анимация вращения колеса
    for frame in range(15):
        wheel_segments.insert(0, wheel_segments.pop())
        delay = 0.15 + (max(0, frame - 10) * 0.1)
        await message.edit_text(
            f"🎡 <b>Колесо Фортуны</b>\n\n{' ' * 8}👆\n{' '.join(wheel_segments)}\n\n"
            f"{'🌀' * (frame % 3 + 1)} Крутим колесо...",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(delay)
    
    # Финальный результат
    attempts = await db.get_user_attempts(user_id)
    await message.edit_text(
        f"🎉 <b>Поздравляем!</b>\n\n🏆 Вы выиграли: <b>{prize_name}</b>\n\n"
        f"🔄 Осталось попыток: <b>{attempts['remaining']}</b>\n\n"
        "Хотите крутить еще?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_play_keyboard(user_id)
    )

# ... (добавьте остальные обработчики по аналогии)

async def main():
    try:
        await init_db()
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Регистрация обработчиков
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button))
        application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_receipt))
        
        logger.info("Bot starting...")
        await application.run_polling()
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())