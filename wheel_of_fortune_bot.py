import logging
import os
import random
import asyncio
from datetime import datetime, timedelta
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
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
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

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💳 Управление платежами", callback_data="admin_payments")],
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

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "play":
        await show_play_menu(query)
    elif data == "check_attempts":
        await check_attempts(query)
    elif data == "daily_bonus":
        await daily_bonus(query)
    elif data == "referral_info":
        await referral_info(query)
    elif data == "buy_attempts":
        await buy_attempts(query)
    elif data == "spin_wheel":
        await spin_wheel(query)
    elif data == "back_to_start":
        await back_to_start(query)
    elif data.startswith("pay_"):
        attempts = int(data.split("_")[1])
        await process_payment(query, attempts)
    elif data == "admin_panel" and query.from_user.id == ADMIN_ID:
        await admin_panel(query)
    elif data == "admin_stats" and query.from_user.id == ADMIN_ID:
        await admin_stats(query)

async def show_play_menu(query):
    user_id = query.from_user.id
    attempts = await db.get_user_attempts(user_id)
    await query.edit_message_text(
        f"🎰 <b>Игровое меню</b>\n\n"
        f"🔄 Доступно попыток: <b>{attempts['remaining']}</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_play_keyboard(user_id)
    )

async def check_attempts(query):
    user_id = query.from_user.id
    attempts = await db.get_user_attempts(user_id)
    await query.edit_message_text(
        f"ℹ️ <b>Ваши попытки</b>\n\n"
        f"💰 Куплено: <b>{attempts['paid']}</b>\n"
        f"🔄 Использовано: <b>{attempts['used']}</b>\n"
        f"🎯 Осталось: <b>{attempts['remaining']}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard(user_id)
    )

async def daily_bonus(query):
    user_id = query.from_user.id
    attempts = await db.get_user_attempts(user_id)
    today = datetime.now().date().isoformat()
    
    if attempts['last_bonus_date'] == today:
        await query.answer("❌ Вы уже получали бонус сегодня!", show_alert=True)
        return
    
    await db.update_user_attempts(
        user_id=user_id,
        paid=DAILY_BONUS,
        last_bonus_date=today
    )
    
    await query.edit_message_text(
        f"🎁 <b>Ежедневный бонус</b>\n\n"
        f"✅ Вы получили <b>{DAILY_BONUS}</b> бесплатную попытку!\n\n"
        f"🔄 Теперь у вас <b>{attempts['remaining'] + DAILY_BONUS}</b> попыток.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard(user_id)
    )

async def referral_info(query):
    user_id = query.from_user.id
    ref_info = await db.get_referral_info(user_id)
    
    if not ref_info or not ref_info['code']:
        ref_code = await db.generate_referral_code(user_id)
    else:
        ref_code = ref_info['code']
    
    ref_link = f"https://t.me/{context.bot.username}?start=ref{ref_code}"
    
    await query.edit_message_text(
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🔗 Ваша реферальная ссылка:\n<code>{ref_link}</code>\n\n"
        f"👤 Приглашено друзей: <b>{ref_info['count'] if ref_info else 0}</b>\n\n"
        "💎 За каждого друга вы получаете <b>+1 попытку</b>!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard(user_id)
    )

async def buy_attempts(query):
    await query.edit_message_text(
        "💰 <b>Покупка попыток</b>\n\n"
        "Выберите количество попыток:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_payment_keyboard()
    )

async def spin_wheel(query):
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

async def back_to_start(query):
    await query.edit_message_text(
        "🎡 Добро пожаловать в <b>Колесо Фортуны</b>!\n\n"
        "💎 Крутите колесо и выигрывайте призы!\n"
        "💰 Попытки можно купить, получить за рефералов или ежедневный бонус.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard(query.from_user.id)
    )

async def process_payment(query, attempts):
    user_id = query.from_user.id
    prices = {1: 50, 3: 130, 5: 200, 10: 350}
    amount = prices.get(attempts, 50 * attempts)
    
    try:
        transaction_id = await db.create_transaction(user_id, amount, attempts)
        await query.edit_message_text(
            f"💳 <b>Оплата {attempts} попыток</b>\n\n"
            f"💰 Сумма: <b>{amount} руб</b>\n\n"
            "Отправьте скриншот чека об оплате для подтверждения.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Payment error: {e}")
        await query.answer("❌ Ошибка при создании платежа", show_alert=True)

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo = update.message.photo[-1]
        await update.message.reply_text(
            "✅ Чек получен! Администратор проверит оплату и начислит попытки в течение 24 часов.",
            parse_mode=ParseMode.HTML
        )
        
        # Уведомление администратора
        if ADMIN_ID:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=photo.file_id,
                caption=f"Новый чек от пользователя {update.message.from_user.id}"
            )

async def admin_panel(query):
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    await query.edit_message_text(
        "🛠 <b>Панель администратора</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_keyboard()
    )

async def admin_stats(query):
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    # Здесь можно добавить реальную статистику из БД
    await query.edit_message_text(
        "📊 <b>Статистика</b>\n\n"
        "👤 Всего пользователей: <b>100</b>\n"
        "💰 Общий доход: <b>5000 руб</b>\n"
        "🎰 Всего игр: <b>250</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_keyboard()
    )

async def main():
    application = None
    try:
        await init_db()
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Регистрация обработчиков
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button))
        application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
        
        logger.info("Bot starting...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Бесконечный цикл ожидания
        while True:
            await asyncio.sleep(3600)  # Проверка каждые 60 минут
            
    except asyncio.CancelledError:
        logger.info("Bot received shutdown signal")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        if application:
            logger.info("Stopping bot gracefully...")
            await application.updater.stop()
            await application.stop()
            await application.shutdown()

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")
    finally:
        loop.close()
        logger.info("Event loop closed")