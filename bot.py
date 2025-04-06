import logging
import os
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
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Подключение к базе данных
conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

# Создание таблицы, если она еще не существует
cursor.execute('''CREATE TABLE IF NOT EXISTS user_attempts
                  (user_id INTEGER PRIMARY KEY, paid INTEGER, used INTEGER)''')
conn.commit()

# Генерация клавиатуры для кнопок
def get_start_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Начать игру", callback_data="play")]])

# Получаем данные о пользователе из базы данных
def get_user_attempts(user_id):
    cursor.execute("SELECT paid, used FROM user_attempts WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        return {"paid": result[0], "used": result[1]}
    else:
        return {"paid": 0, "used": 0}

def get_play_keyboard(user_id):
    user_data = get_user_attempts(user_id)
    if user_data['paid'] > 0:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Крутить колесо", callback_data="spin_wheel")]])
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Попробуйте купить попытки", callback_data="play")]])

def get_play_disabled_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Вы уже использовали все попытки", callback_data="spin_wheel_disabled")]])

# Сохранение данных о пользователе в базе данных
def save_user_attempts(user_id, paid_attempts, used_attempts):
    cursor.execute('INSERT OR REPLACE INTO user_attempts (user_id, paid, used) VALUES (?, ?, ?)',
                   (user_id, paid_attempts, used_attempts))
    conn.commit()

# Команда start
async def start(update: Update, context: CallbackContext):
    user_data = get_user_attempts(update.effective_user.id)
    
    if user_data['paid'] > 0:
        await update.message.reply_text(
            "У вас есть оплаченные попытки! Начнем?",
            reply_markup=get_play_keyboard(update.effective_user.id)
        )
    else:
        await update.message.reply_text(
            "Привет! Я — бот Колесо фортуны. Чтобы начать, выбери одну из опций ниже.",
            reply_markup=get_start_keyboard()
        )

# Команда play
async def play(update: Update, context: CallbackContext):
    try:
        await update.callback_query.message.delete()
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")

    keyboard = [
        [InlineKeyboardButton("1 попытка — 50 рублей", callback_data="pay_1")],
        [InlineKeyboardButton("3 попытки — 130 рублей", callback_data="pay_3")],
        [InlineKeyboardButton("5 попыток — 200 рублей", callback_data="pay_5")],
        [InlineKeyboardButton("10 попыток — 350 рублей", callback_data="pay_10")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.reply_text(
        "Выберите количество попыток для покупки. Сумма будет зависеть от вашего выбора.",
        reply_markup=reply_markup
    )

# Обработка выбора количества попыток
async def handle_payment_choice(update: Update, context: CallbackContext):
    choice = update.callback_query.data.split("_")[1]
    amounts = {"1": 50, "3": 130, "5": 200, "10": 350}

    price = amounts.get(choice)
    if price:
        await update.callback_query.message.delete()
        await update.callback_query.message.reply_text(
            f"Вы выбрали {choice} попыток за {price} рублей.\n"
            "После перевода отправьте мне квитанцию о платеже, и я дам вам попытки!",
        )
        context.user_data["payment_choice"] = choice
    else:
        await update.callback_query.message.reply_text("Неверный выбор.")

# Обработчик квитанций (фото или документы)
async def handle_receipt(update: Update, context: CallbackContext):
    user = update.effective_user
    if update.message.photo or update.message.document:
        user_id = user.id
        payment_choice = context.user_data.get("payment_choice", None)
        if payment_choice:
            amount = {"1": 50, "3": 130, "5": 200, "10": 350}.get(payment_choice, 0)
            caption = f"Чек от @{user.username} (ID: {user_id}). Оплачено: {amount} рублей."

            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=update.message.photo[-1].file_id,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([ 
                        [InlineKeyboardButton("Подтвердить оплату", callback_data=f"confirm_payment:{user_id}"),
                         InlineKeyboardButton("Отклонить оплату", callback_data=f"decline_payment:{user_id}")]
                    ])
                )
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=update.message.document.file_id,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([ 
                        [InlineKeyboardButton("Подтвердить оплату", callback_data=f"confirm_payment:{user_id}"),
                         InlineKeyboardButton("Отклонить оплату", callback_data=f"decline_payment:{user_id}")]
                    ])
                )
            await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.")
        else:
            await update.message.reply_text("Неизвестная сумма, повторите попытку.")
    else:
        await update.message.reply_text("Пожалуйста, отправьте чек о платеже.")

# Обработчик подтверждения оплаты (администратором)
async def confirm_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        client_id = int(update.callback_query.data.split(":")[1])
        logger.info(f"Подтверждение оплаты для клиента с ID: {client_id}")

        payment_choice = context.user_data.get("payment_choice", None)
        logger.info(f"Выбранное количество попыток: {payment_choice}")
        
        if payment_choice:
            attempts = {"1": 1, "3": 3, "5": 5, "10": 10}.get(payment_choice, 0)
            logger.info(f"Попытки, которые будут добавлены: {attempts}")
            
            if attempts > 0:
                save_user_attempts(client_id, attempts, 0)  # Сохраняем данные о попытках в базе данных
                await context.bot.send_message(
                    chat_id=client_id,
                    text=f"Оплата прошла успешно! Теперь у вас есть {attempts} попыток.",
                    reply_markup=get_play_keyboard(client_id)
                )
                await update.callback_query.answer("Оплата подтверждена.")
            else:
                logger.error("Ошибка: не найдено выбранное количество попыток.")
                await update.callback_query.answer("Неизвестная сумма.")
        else:
            logger.error("Ошибка: не найдено значение payment_choice.")
            await update.callback_query.answer("Ошибка: не найдено выбранное количество попыток.")
    else:
        logger.error("Ошибка: Только администратор может подтвердить оплату.")
        await update.callback_query.answer("Только администратор может подтвердить оплату.")

# Обработчик отклонения оплаты (администратором)
async def decline_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        client_id = int(update.callback_query.data.split(":")[1])
        await context.bot.send_message(
            chat_id=client_id,
            text="Ваш платеж был отклонен. Попробуйте снова."
        )
        await update.callback_query.answer("Оплата отклонена.")
    else:
        await update.callback_query.answer("Только администратор может отклонить оплату.")

# Обработчик для кручения колеса
async def spin_wheel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_data = get_user_attempts(user_id)

    if user_data['paid'] > 0:
        used_attempts = user_data['used'] + 1
        paid_attempts = user_data['paid'] - 1
        save_user_attempts(user_id, paid_attempts, used_attempts)

        result = "Поздравляем, вы выиграли 100 рублей!"  # Пример результата

        await update.callback_query.message.reply_text(
            f"Колесо крутано! Результат: {result}",
            reply_markup=get_play_disabled_keyboard()
        )
    else:
        await update.callback_query.message.reply_text(
            "У вас нет оплаченных попыток. Пожалуйста, купите попытки, чтобы продолжить."
        )

# Основная функция для запуска бота
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(play, pattern="play"))
    application.add_handler(CallbackQueryHandler(handle_payment_choice, pattern="pay_"))
    application.add_handler(MessageHandler(filters.Photo | filters.Document.ALL, handle_receipt))
    application.add_handler(CallbackQueryHandler(confirm_payment, pattern="confirm_payment"))
    application.add_handler(CallbackQueryHandler(decline_payment, pattern="decline_payment"))
    application.add_handler(CallbackQueryHandler(spin_wheel, pattern="spin_wheel"))

    application.run_polling()

if __name__ == "__main__":
    main()
