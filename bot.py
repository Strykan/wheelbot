import logging
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters
from dotenv import load_dotenv

# Загрузим переменные из .env
load_dotenv()

# Получаем токен из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")  # ID администратора для подтверждения квитанций

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

# Генерация клавиатуры для кнопок
def get_start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Начать игру", callback_data="play")],
        [InlineKeyboardButton("Контакты для оплаты", callback_data="payment_info")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Назад", callback_data="back")]
    ])

def get_admin_confirmation_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Подтвердить оплату", callback_data="confirm_payment")],
        [InlineKeyboardButton("Отклонить оплату", callback_data="decline_payment")]
    ])

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
        reply_markup=get_back_keyboard()
    )

# Команда с реквизитами для оплаты
async def payment_info(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Переведи деньги на следующие реквизиты:\n"
        "Сумма: 100 рублей\n\n"
        "После перевода отправь мне квитанцию о платеже, и я дам тебе попытки!",
        reply_markup=get_back_keyboard()
    )

# Функция для вращения колеса фортуны
async def spin_wheel(update: Update, context: CallbackContext):
    prize = random.choice(PRIZES)  # Выбираем случайный приз
    await update.message.reply_text(
        f"🎉 Поздравляем! Ты выиграл: {prize} 🎉",
        reply_markup=get_back_keyboard()
    )

# Обработчик квитанций (фото или документы)
async def handle_receipt(update: Update, context: CallbackContext):
    if update.message.photo:
        caption = f"Чек от @{update.effective_user.username} (ID: {update.effective_user.id})"
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=update.message.photo[-1].file_id,
            caption=caption,
            reply_markup=get_admin_confirmation_keyboard()  # Кнопки для подтверждения
        )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.", reply_markup=get_back_keyboard())
    elif update.message.document:
        caption = f"Чек от @{update.effective_user.username} (ID: {update.effective_user.id})"
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=update.message.document.file_id,
            caption=caption,
            reply_markup=get_admin_confirmation_keyboard()  # Кнопки для подтверждения
        )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.", reply_markup=get_back_keyboard())
    else:
        await update.message.reply_text("Пожалуйста, отправьте чек о платеже.", reply_markup=get_back_keyboard())

# Обработчик подтверждения или отклонения оплаты (администратором)
async def confirm_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == int(ADMIN_ID):  # Проверка, что это администратор
        await update.message.reply_text("Оплата подтверждена! Пользователь получит попытки.", reply_markup=get_back_keyboard())
        # Запускаем колесо фортуны после подтверждения
        await spin_wheel(update, context)
    else:
        await update.message.reply_text("Только администратор может подтвердить оплату.", reply_markup=get_back_keyboard())

async def decline_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == int(ADMIN_ID):  # Проверка, что это администратор
        await update.message.reply_text("Оплата отклонена. Попробуйте снова.", reply_markup=get_back_keyboard())
    else:
        await update.message.reply_text("Только администратор может отклонить оплату.", reply_markup=get_back_keyboard())

# Обработчик inline кнопок
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки
    
    # Обработка нажатия на кнопки
    if query.data == "play":
        await play(update, context)
    elif query.data == "payment_info":
        await payment_info(update, context)
    elif query.data == "back":
        await start(update, context)
    elif query.data == "confirm_payment":
        # Проверим, есть ли сообщение с чеком
        if query.message.reply_to_message:
            # Это сообщение с чеком
            await query.message.reply_to_message.reply_text(
                "Оплата подтверждена! Пользователь получит попытки.", reply_markup=get_back_keyboard()
            )
            # Запускаем колесо фортуны после подтверждения
            await spin_wheel(update, context)
        else:
            # Обработка случая, когда нет сообщения с чеком (неожиданный случай)
            await query.message.reply_text("Ошибка: сообщение с чеком не найдено.", reply_markup=get_back_keyboard())

    elif query.data == "decline_payment":
        # Проверим, есть ли сообщение с чеком
        if query.message.reply_to_message:
            # Это сообщение с чеком
            await query.message.reply_to_message.reply_text(
                "Оплата отклонена. Попробуйте снова.", reply_markup=get_back_keyboard()
            )
        else:
            # Обработка случая, когда нет сообщения с чеком (неожиданный случай)
            await query.message.reply_text("Ошибка: сообщение с чеком не найдено.", reply_markup=get_back_keyboard())

# Ошибки
async def error(update: Update, context: CallbackContext):
    logger.warning(f'Update {update} caused error {context.error}')

# Основная функция для запуска
def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("confirm_payment", confirm_payment))  # Убираем pass_args
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))  # Обработка фото
    application.add_handler(MessageHandler(filters.Document.ALL, handle_receipt))  # Обработка документов
    application.add_handler(CallbackQueryHandler(button))  # Обработчик inline кнопок
    application.add_error_handler(error)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
