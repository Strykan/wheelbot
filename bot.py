import logging
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters
from dotenv import load_dotenv
import sqlite3

# Загрузим переменные из .env
load_dotenv()

# Получаем токен из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # ID администратора для подтверждения квитанций

# Логирование для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Призовые сектора Колеса фортуны
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

# Подключение к базе данных
conn = sqlite3.connect('user_data.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблицы, если она еще не существует
cursor.execute('''CREATE TABLE IF NOT EXISTS user_attempts
                  (user_id INTEGER PRIMARY KEY, paid INTEGER, used INTEGER)''')
conn.commit()

def get_start_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Начать игру", callback_data="play")]])

def get_play_keyboard(user_id):
    # Получаем данные из БД
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result and result[0] > result[1]:  # Если есть неиспользованные попытки
        return InlineKeyboardMarkup([[InlineKeyboardButton("Крутить колесо", callback_data="spin_wheel")]])
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Купить попытки", callback_data="play")]])

def save_user_attempts(user_id, paid_attempts, used_attempts):
    try:
        cursor.execute('INSERT OR REPLACE INTO user_attempts (user_id, paid, used) VALUES (?, ?, ?)',
                       (user_id, paid_attempts, used_attempts))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я — бот Колесо фортуны. Чтобы начать, выбери одну из опций ниже.",
        reply_markup=get_start_keyboard()
    )

async def play(update: Update, context: CallbackContext):
    await update.callback_query.message.delete()
    
    keyboard = [
        [InlineKeyboardButton("1 попытка — 50 рублей", callback_data="pay_1")],
        [InlineKeyboardButton("3 попытки — 130 рублей", callback_data="pay_3")],
        [InlineKeyboardButton("5 попыток — 200 рублей", callback_data="pay_5")],
        [InlineKeyboardButton("10 попыток — 350 рублей", callback_data="pay_10")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.reply_text(
        "Выберите количество попыток для покупки:",
        reply_markup=reply_markup
    )

async def handle_payment_choice(update: Update, context: CallbackContext):
    choice = update.callback_query.data.split("_")[1]
    amounts = {"1": 50, "3": 130, "5": 200, "10": 350}
    
    if choice in amounts:
        context.chat_data["payment_choice"] = choice
        await update.callback_query.message.delete()
        await update.callback_query.message.reply_text(
            f"Вы выбрали {choice} попыток за {amounts[choice]} рублей.\n"
            "После перевода отправьте мне квитанцию о платеже (фото или документ)."
        )
    else:
        await update.callback_query.message.reply_text("Неверный выбор.")

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
    caption = f"Чек от @{user.username} (ID: {user.id}). Оплачено: {amount} рублей."

    try:
        if update.message.photo:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=update.message.photo[-1].file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{user.id}:{payment_choice}"),
                     InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{user.id}")]
                ])
            )
        else:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=update.message.document.file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{user.id}:{payment_choice}"),
                     InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{user.id}")]
                ])
            )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.")
    except Exception as e:
        logger.error(f"Error sending receipt: {e}")
        await update.message.reply_text("Произошла ошибка при отправке чека. Попробуйте позже.")

async def confirm_payment(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("Только администратор может подтверждать платежи.")
        return
        
    _, user_id, payment_choice = update.callback_query.data.split(":")
    user_id = int(user_id)
    attempts = {"1": 1, "3": 3, "5": 5, "10": 10}.get(payment_choice, 0)
    
    try:
        save_user_attempts(user_id, attempts, 0)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ Оплата подтверждена! Теперь у вас {attempts} попыток.",
            reply_markup=get_play_keyboard(user_id)
        )
        await update.callback_query.answer("Оплата подтверждена!")
        await update.callback_query.message.edit_reply_markup(reply_markup=None)
        await update.callback_query.message.reply_text(f"Оплата от пользователя ID {user_id} подтверждена.")
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        await update.callback_query.answer("Ошибка подтверждения платежа.")

async def decline_payment(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("Только администратор может отклонять платежи.")
        return
        
    _, user_id = update.callback_query.data.split(":")
    user_id = int(user_id)
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Ваш платеж был отклонен администратором. Если вы считаете это ошибкой, свяжитесь с поддержкой."
        )
        await update.callback_query.answer("Платеж отклонен!")
        await update.callback_query.message.edit_reply_markup(reply_markup=None)
        await update.callback_query.message.reply_text(f"Платеж от пользователя ID {user_id} отклонен.")
    except Exception as e:
        logger.error(f"Error declining payment: {e}")
        await update.callback_query.answer("Ошибка отклонения платежа.")

async def spin_wheel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if not result or result[0] <= result[1]:
        await update.callback_query.answer("У вас нет доступных попыток!")
        return
    
    # Увеличиваем счетчик использованных попыток
    new_used = result[1] + 1
    save_user_attempts(user_id, result[0], new_used)
    
    # Крутим колесо
    prize = random.choice(PRIZES)
    
    # Обработка специальных призов
    if prize == "Бесплатная попытка":
        cursor.execute('UPDATE user_attempts SET paid = paid + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
    elif prize == "5 бесплатных попыток":
        cursor.execute('UPDATE user_attempts SET paid = paid + 5 WHERE user_id = ?', (user_id,))
        conn.commit()
    
    await update.callback_query.message.reply_text(
        f"🎉 Поздравляем! Вы выиграли: {prize}\n"
        f"Осталось попыток: {result[0] - new_used}",
        reply_markup=get_play_keyboard(user_id)
    )

async def check_attempts(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        await update.message.reply_text(
            f"У вас {result[0] - result[1]} попыток из {result[0]} доступных.",
            reply_markup=get_play_keyboard(user_id)
        )
    else:
        await update.message.reply_text(
            "У вас нет активных попыток. Хотите купить?",
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
    elif query.data.startswith("confirm:"):
        await confirm_payment(update, context)
    elif query.data.startswith("decline:"):
        await decline_payment(update, context)

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("attempts", check_attempts))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_receipt))

    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    finally:
        conn.close()  # Закрываем соединение с БД при выходе