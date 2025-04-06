import logging
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters
from dotenv import load_dotenv

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

# Состояния пользователя для отслеживания попыток
user_attempts = {}

# Генерация клавиатуры для кнопок
def get_start_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Начать игру", callback_data="play"),
    ], [
        InlineKeyboardButton("Контакты для оплаты", callback_data="payment_info"),
    ]])

def get_spin_wheel_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Крутить колесо", callback_data="spin_wheel"),
    ]])

def get_payment_options_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("1 попытка (100 рублей)", callback_data="buy_1_attempt"),
    ], [
        InlineKeyboardButton("3 попытки (250 рублей)", callback_data="buy_3_attempts"),
    ], [
        InlineKeyboardButton("5 попыток (400 рублей)", callback_data="buy_5_attempts"),
    ], [
        InlineKeyboardButton("10 попыток (750 рублей)", callback_data="buy_10_attempts"),
    ]])

def get_admin_confirmation_keyboard(user_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Подтвердить оплату", callback_data=f"confirm_payment:{user_id}"),
        InlineKeyboardButton("Отклонить оплату", callback_data=f"decline_payment:{user_id}")
    ]])

# Команда start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я — бот Колесо фортуны. Чтобы начать, выбери одну из опций ниже.",
        reply_markup=get_start_keyboard()
    )

# Команда play
async def play(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Для того, чтобы сыграть, переведи деньги на следующие реквизиты:\n"
        "Сумма: 100 рублей\n\n"
        "После перевода отправь мне квитанцию о платеже. Я проверю и дам тебе попытки!",
        reply_markup=get_payment_options_keyboard()
    )

# Команда с реквизитами для оплаты
async def payment_info(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Переведи деньги на следующие реквизиты:\n"
        "Сумма: 100 рублей\n\n"
        "После перевода отправь мне квитанцию о платеже, и я дам тебе попытки!",
        reply_markup=get_payment_options_keyboard()
    )

# Функция для вращения колеса фортуны
async def spin_wheel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id in user_attempts and user_attempts[user_id] > 0:
        prize = random.choice(PRIZES)  # Выбираем случайный приз
        user_attempts[user_id] -= 1
        await update.message.reply_text(
            f"🎉 Поздравляем! Ты выиграл: {prize} 🎉\n\n"
            f"Осталось попыток: {user_attempts[user_id]}",
            reply_markup=get_spin_wheel_keyboard()
        )
    else:
        await update.message.reply_text(
            "Вы уже использовали все свои попытки! Купите дополнительные.",
            reply_markup=get_payment_options_keyboard()
        )

# Обработчик квитанций (фото или документы)
async def handle_receipt(update: Update, context: CallbackContext):
    user = update.effective_user
    if update.message.photo:
        caption = f"Чек от @{user.username} (ID: {user.id})"
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=update.message.photo[-1].file_id,
            caption=caption,
            reply_markup=get_admin_confirmation_keyboard(user.id)  # Кнопки для подтверждения
        )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.")
    elif update.message.document:
        caption = f"Чек от @{user.username} (ID: {user.id})"
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=update.message.document.file_id,
            caption=caption,
            reply_markup=get_admin_confirmation_keyboard(user.id)  # Кнопки для подтверждения
        )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.")
    else:
        await update.message.reply_text("Пожалуйста, отправьте чек о платеже.")

# Обработчик подтверждения или отклонения оплаты (администратором)
async def confirm_payment(update: Update, context: CallbackContext):
    user_id = int(update.callback_query.data.split(":")[1])
    if user_id not in user_attempts:
        user_attempts[user_id] = 0
    user_attempts[user_id] += 1  # Добавляем 1 попытку после подтверждения
    await update.callback_query.answer("Оплата подтверждена! Теперь вы можете крутить колесо.")
    await update.callback_query.edit_message_text("Оплата прошла успешно! Теперь вы можете крутить колесо.",
                                                 reply_markup=get_spin_wheel_keyboard())

async def decline_payment(update: Update, context: CallbackContext):
    user_id = int(update.callback_query.data.split(":")[1])
    await update.callback_query.answer("Оплата отклонена. Попробуйте снова.")
    await update.callback_query.edit_message_text("Оплата отклонена. Попробуйте снова.")

# Обработчик inline кнопок
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки

    if query.data == "play":
        await play(update, context)
    elif query.data == "payment_info":
        await payment_info(update, context)
    elif query.data == "spin_wheel":
        await spin_wheel(update, context)
    elif query.data.startswith("buy_"):
        # Обработка покупки попыток
        attempts = 0
        if query.data == "buy_1_attempt":
            attempts = 1
        elif query.data == "buy_3_attempts":
            attempts = 3
        elif query.data == "buy_5_attempts":
            attempts = 5
        elif query.data == "buy_10_attempts":
            attempts = 10
        
        user_id = query.from_user.id
        user_attempts[user_id] = attempts
        await query.edit_message_text(f"Вы приобрели {attempts} попыток! Теперь нажмите кнопку ниже, чтобы крутить колесо.",
                                      reply_markup=get_spin_wheel_keyboard())

# Ошибки
async def error(update: Update, context: CallbackContext):
    logger.warning(f'Update {update} caused error {context.error}')

# Основная функция для запуска
def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))  # Обработка фото
    application.add_handler(MessageHandler(filters.Document.ALL, handle_receipt))  # Обработка документов
    application.add_handler(CallbackQueryHandler(button))  # Обработчик inline кнопок
    application.add_error_handler(error)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
