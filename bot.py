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
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
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

# Для отслеживания количества оплаченных и использованных попыток
user_attempts = {}

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

def get_play_keyboard(user_id):
    if user_attempts.get(user_id, {}).get('paid', 0) > 0:
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
    await update.message.reply_text(
        "Привет! Я — бот Колесо фортуны. Чтобы начать, выбери одну из опций ниже.",
        reply_markup=get_start_keyboard()
    )

# Команда play
async def play(update: Update, context: CallbackContext):
    # Удаляем предыдущее сообщение
    await update.callback_query.message.delete()

    # Отправляем сообщение, которое позволяет пользователю выбрать количество попыток
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
    # Извлекаем данные о количестве попыток из callback_data
    choice = update.callback_query.data.split("_")[1]
    amounts = {"1": 50, "3": 130, "5": 200, "10": 350}  # Стоимость для каждого варианта

    # Получаем сумму
    price = amounts.get(choice)
    if price:
        # Запрашиваем квитанцию и информируем о стоимости
        await update.callback_query.message.delete()
        await update.callback_query.message.reply_text(
            f"Вы выбрали {choice} попыток за {price} рублей.\n"
            "После перевода отправьте мне квитанцию о платеже, и я дам вам попытки!"
        )
        # Сохраняем выбранный вариант для дальнейшего использования
        context.chat_data["payment_choice"] = choice
    else:
        await update.callback_query.message.reply_text("Неверный выбор.")

# Обработка квитанций (фото или документы)
async def handle_receipt(update: Update, context: CallbackContext):
    user = update.effective_user
    if update.message.photo or update.message.document:
        # Извлекаем ID пользователя и сумму для оплаты
        user_id = user.id
        # Сначала получим выбранную сумму из context
        payment_choice = context.chat_data.get("payment_choice", None)
        if payment_choice:
            amount = {"1": 50, "3": 130, "5": 200, "10": 350}.get(payment_choice, 0)
            caption = f"Чек от @{user.username} (ID: {user_id}). Оплачено: {amount} рублей."

            # Отправляем фото или документ админу
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

# Обработчик подтверждения или отклонения оплаты (администратором)
async def confirm_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:  # Проверка, что это администратор
        # Получаем user_id клиента из callback_data
        client_id = int(update.callback_query.data.split(":")[1])
        logger.info(f"Подтверждение оплаты для клиента с ID: {client_id}")
        
        # Получаем выбранный payment_choice для этого клиента из context
        payment_choice = context.chat_data.get("payment_choice", None)
        
        if payment_choice:
            attempts = {"1": 1, "3": 3, "5": 5, "10": 10}.get(payment_choice, 0)
            
            if attempts > 0:
                save_user_attempts(client_id, attempts, 0)
                await context.bot.send_message(
                    chat_id=client_id,
                    text=f"Оплата прошла успешно! Теперь у вас есть {attempts} попыток.",
                    reply_markup=get_play_keyboard(client_id)  # Добавляем кнопку для игры
                )
                await update.callback_query.answer("Оплата подтверждена.")
            else:
                await update.callback_query.answer("Неизвестная сумма.")
        else:
            await update.callback_query.answer("Ошибка: не найдено выбранное количество попыток.")
    else:
        await update.callback_query.answer("Только администратор может подтвердить оплату.")

async def decline_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:  # Проверка, что это администратор
        # Получаем user_id клиента из callback_data
        client_id = int(update.callback_query.data.split(":")[1])
        logger.info(f"Отклонение оплаты для клиента с ID: {client_id}")
        
        # Отправляем сообщение клиенту об отклонении
        await context.bot.send_message(
            chat_id=client_id,
            text="Оплата отклонена. Попробуйте снова."
        )
        await update.callback_query.answer("Оплата отклонена.")
    else:
        await update.callback_query.answer("Только администратор может отклонить оплату.")

# Обработчик inline кнопок
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки
    
    # Обработка нажатий на кнопки с оплатой
    if query.data == "play":
        await play(update, context)
    elif query.data.startswith("pay_"):
        choice = query.data.split("_")[1]
        context.chat_data["payment_choice"] = choice  # Сохраняем выбор пользователя
        await handle_payment_choice(update, context)
    elif query.data == "spin_wheel":
        await spin_wheel(update, context)
    elif query.data.startswith("confirm_payment"):
        await confirm_payment(update, context)
    elif query.data.startswith("decline_payment"):
        await decline_payment(update, context)

# Основная функция для запуска бота
def main():
    # Создаем объект бота
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_receipt))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
