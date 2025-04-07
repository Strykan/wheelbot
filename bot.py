import logging
import os
import random
import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    filters
)
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PRIZES = [
    "100 рублей",
    "Бесплатная попытка",
    "5 бесплатных попыток",
    "10 рублей",
    "Конфетка",
    "Ничего",
    "5 рублей",
    "Скидка 10% на след. игру",
    "Подарок"
]

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
conn = sqlite3.connect('wheel_of_fortune.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS user_attempts
                  (user_id INTEGER PRIMARY KEY, paid INTEGER, used INTEGER)''')
conn.commit()

# Клавиатуры
def get_start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 Начать игру", callback_data="play")],
        [InlineKeyboardButton("ℹ️ Мои попытки", callback_data="check_attempts")]
    ])

def get_play_keyboard(user_id):
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result and result[0] > result[1]:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Крутить колесо", callback_data="spin_wheel")],
            [InlineKeyboardButton("💰 Купить еще попыток", callback_data="play")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Купить попытки", callback_data="play")],
        [InlineKeyboardButton("ℹ️ Мои попытки", callback_data="check_attempts")]
    ])

def get_payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 попытка — 50 руб", callback_data="pay_1")],
        [InlineKeyboardButton("3 попытки — 130 руб (↘️10%)", callback_data="pay_3")],
        [InlineKeyboardButton("5 попыток — 200 руб (↘️20%)", callback_data="pay_5")],
        [InlineKeyboardButton("10 попыток — 350 руб (↘️30%)", callback_data="pay_10")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]
    ])

# Функции работы с БД
def save_user_attempts(user_id, paid_attempts, used_attempts):
    try:
        cursor.execute(
            'INSERT OR REPLACE INTO user_attempts (user_id, paid, used) VALUES (?, ?, ?)',
            (user_id, paid_attempts, used_attempts)
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")

# Обработчики команд
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🎡 Добро пожаловать в <b>Колесо Фортуны</b>!\n\n"
        "💎 Крутите колесо и выигрывайте призы!\n"
        "💰 Попытки можно купить или выиграть в игре.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard()
    )

async def play(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "🎯 Выберите количество попыток:\n\n"
        "💎 1 попытка — 50 руб\n"
        "💎 3 попытки — 130 руб (экономия 10%)\n"
        "💎 5 попыток — 200 руб (экономия 20%)\n"
        "💎 10 попыток — 350 руб (экономия 30%)",
        reply_markup=get_payment_keyboard()
    )

async def check_attempts(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        text = (
            f"📊 Ваши попытки:\n\n"
            f"💎 Всего куплено: {result[0]}\n"
            f"🔄 Использовано: {result[1]}\n"
            f"🎯 Осталось: {result[0] - result[1]}"
        )
    else:
        text = "У вас пока нет попыток. Хотите купить?"
    
    await query.message.edit_text(
        text,
        reply_markup=get_play_keyboard(user_id)
    )

async def handle_payment_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    choice = query.data.split("_")[1]
    amounts = {"1": 50, "3": 130, "5": 200, "10": 350}
    
    if choice in amounts:
        context.chat_data["payment_choice"] = choice
        await query.message.edit_text(
            f"💳 Вы выбрали <b>{choice}</b> попыток за <b>{amounts[choice]} руб</b>.\n\n"
            "📤 Отправьте фото или скриншот чека об оплате.\n"
            "⏳ После проверки администратором вам будут начислены попытки.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="play")]
            ])
        )
    else:
        await query.answer("Неверный выбор")

async def handle_receipt(update: Update, context: CallbackContext):
    user = update.effective_user
    payment_choice = context.chat_data.get("payment_choice")
    
    if not payment_choice:
        await update.message.reply_text("Сначала выберите количество попыток через меню.")
        return
        
    if not (update.message.photo or update.message.document):
        await update.message.reply_text("Пожалуйста, отправьте чек о платеже (фото или документ).")
        return
    
    amount = {"1": 50, "3": 130, "5": 200, "10": 350}.get(payment_choice, 0)
    caption = (
        f"📤 Новый чек от @{user.username}\n"
        f"🆔 ID: {user.id}\n"
        f"💎 Попыток: {payment_choice}\n"
        f"💰 Сумма: {amount} руб"
    )

    try:
        if update.message.photo:
            msg = await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=update.message.photo[-1].file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{user.id}:{payment_choice}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{user.id}")
                    ]
                ])
            )
        else:
            msg = await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=update.message.document.file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{user.id}:{payment_choice}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{user.id}")
                    ]
                ])
            )
        
        await update.message.reply_text(
            "📨 Ваш чек отправлен на проверку администратору.\n"
            "⏳ Обычно проверка занимает не более 24 часов.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 В меню", callback_data="back_to_start")]
            ])
        )
        
        # Сохраняем ID сообщения для администратора
        context.chat_data["admin_message_id"] = msg.message_id
        
    except Exception as e:
        logger.error(f"Error sending receipt: {e}")
        await update.message.reply_text("❌ Произошла ошибка при отправке чека. Попробуйте позже.")

async def spin_wheel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if not result or result[0] <= result[1]:
        await query.answer("У вас нет доступных попыток!", show_alert=True)
        return
    
    # Увеличиваем счетчик использованных попыток
    new_used = result[1] + 1
    save_user_attempts(user_id, result[0], new_used)
    
    # Символы для анимации колеса (используем моноширинный шрифт)
    wheel_segments = ["🍒", "🍋", "🍊", "🍇", "🍉", "💰", "🎁", "⭐", "🍀"]
    pointer = "👇"
    
    # Создаем начальное сообщение с колесом
    message = await query.message.reply_text(
        "🎡 <b>Колесо Фортуны</b>\n\n"
        f"{' '.join(wheel_segments)}\n"
        f"{' ' * 8}{pointer}\n\n"
        "Крутим...",
        parse_mode=ParseMode.HTML
    )
    
    # Параметры анимации
    spin_duration = 3  # секунды
    frames_per_second = 10
    total_frames = spin_duration * frames_per_second
    slowdown_steps = 5  # количество шагов замедления
    
    # Анимация прокрутки с замедлением
    for frame in range(total_frames):
        # Вычисляем скорость с замедлением в конце
        if frame < total_frames - slowdown_steps:
            delay = 1 / frames_per_second
        else:
            delay = 1 / (frames_per_second - (total_frames - frame))
        
        # Вращаем колесо
        wheel_segments.insert(0, wheel_segments.pop())
        
        # Обновляем сообщение
        await message.edit_text(
            "🎡 <b>Колесо Фортуны</b>\n\n"
            f"{' '.join(wheel_segments)}\n"
            f"{' ' * 8}{pointer}\n\n"
            f"{'🌀' * (frame % 3 + 1)} Крутим...",
            parse_mode=ParseMode.HTML
        )
        
        await asyncio.sleep(delay)
    
    # Определяем выигрыш
    prize = random.choices(
        PRIZES,
        weights=[15, 10, 5, 20, 10, 5, 15, 10, 10],  # Вероятности выпадения
        k=1
    )[0]
    
    # Обработка специальных призов
    bonus_text = ""
    if prize == "Бесплатная попытка":
        cursor.execute('UPDATE user_attempts SET paid = paid + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        bonus_text = "\n\n🎁 Вам добавлена 1 бесплатная попытка!"
    elif prize == "5 бесплатных попыток":
        cursor.execute('UPDATE user_attempts SET paid = paid + 5 WHERE user_id = ?', (user_id,))
        conn.commit()
        bonus_text = "\n\n🎁 Вам добавлено 5 бесплатных попыток!"
    
    # Получаем обновленное количество попыток
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    updated_attempts = cursor.fetchone()
    
    # Показываем результат с эффектом "остановки" на выигранном призе
    for _ in range(3):
        await message.edit_text(
            f"🎡 <b>Колесо Фортуны</b>\n\n"
            f"{' '.join(wheel_segments)}\n"
            f"{' ' * 8}{pointer}\n\n"
            f"🎉 Ваш выигрыш: {prize}",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(0.5)
    
    # Финальное сообщение с результатом
    await message.edit_text(
        f"🎉 <b>Поздравляем!</b>\n\n"
        f"🏆 Ваш выигрыш: <b>{prize}</b>{bonus_text}\n\n"
        f"📊 Осталось попыток: <b>{updated_attempts[0] - updated_attempts[1]}</b>\n\n"
        "Хотите крутить еще?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_play_keyboard(user_id)
    )

async def confirm_payment(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может подтверждать платежи.", show_alert=True)
        return
        
    _, user_id, payment_choice = query.data.split(":")
    user_id = int(user_id)
    attempts = {"1": 1, "3": 3, "5": 5, "10": 10}.get(payment_choice, 0)
    
    try:
        save_user_attempts(user_id, attempts, 0)
        
        # Уведомляем пользователя
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ <b>Ваш платеж подтвержден!</b>\n\n"
                 f"💎 Вам начислено <b>{attempts}</b> попыток.\n"
                 f"🎯 Теперь вы можете крутить колесо фортуны!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_play_keyboard(user_id)
        )
        
        # Редактируем сообщение у администратора
        await query.message.edit_text(
            f"✅ Платеж подтвержден\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"💎 Попыток: {attempts}\n"
            f"🕒 {query.message.date.strftime('%Y-%m-%d %H:%M')}",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        await query.answer("Ошибка при подтверждении платежа", show_alert=True)

async def decline_payment(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может отклонять платежи.", show_alert=True)
        return
        
    _, user_id = query.data.split(":")
    user_id = int(user_id)
    
    try:
        # Уведомляем пользователя
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ <b>Ваш платеж был отклонен администратором</b>\n\n"
                 "Возможные причины:\n"
                 "• Неправильный чек\n"
                 "• Несоответствующая сумма\n"
                 "• Подозрительная активность\n\n"
                 "Если вы считаете это ошибкой, свяжитесь с поддержкой.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_start_keyboard()
        )
        
        # Редактируем сообщение у администратора
        await query.message.edit_text(
            f"❌ Платеж отклонен\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"🕒 {query.message.date.strftime('%Y-%m-%d %H:%M')}",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error declining payment: {e}")
        await query.answer("Ошибка при отклонении платежа", show_alert=True)

async def back_to_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "🎡 Добро пожаловать в <b>Колесо Фортуны</b>!\n\n"
        "💎 Крутите колесо и выигрывайте призы!\n"
        "💰 Попытки можно купить или выиграть в игре.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard()
    )

async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == "play":
        await play(update, context)
    elif query.data.startswith("pay_"):
        await handle_payment_choice(update, context)
    elif query.data == "spin_wheel":
        await spin_wheel(update, context)
    elif query.data == "check_attempts":
        await check_attempts(update, context)
    elif query.data.startswith("confirm:"):
        await confirm_payment(update, context)
    elif query.data.startswith("decline:"):
        await decline_payment(update, context)
    elif query.data == "back_to_start":
        await back_to_start(update, context)

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    
    # Обработчики callback-кнопок
    application.add_handler(CallbackQueryHandler(button))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_receipt))
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        conn.close()
        logger.info("Database connection closed")