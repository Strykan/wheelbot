import logging
import os
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
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

# Команда start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я — бот Колесо фортуны. Чтобы начать, выбери команду /play. "
        "Ты можешь выиграть различные призы, но для этого нужно заплатить за попытку. "
        "После того как оплатишь, отправь мне квитанцию и я подтвержу твою оплату."
    )

# Команда play
async def play(update: Update, context: CallbackContext):
    await update.message.reply_text(
        f"Для того, чтобы сыграть, переведи деньги на следующие реквизиты:\n"
        f"Сумма: 100 рублей\n\n"
        f"После перевода отправь мне квитанцию о платеже. Я проверю и дам тебе попытки!"
    )

# Функция для вращения колеса фортуны
async def spin_wheel(update: Update, context: CallbackContext):
    prize = random.choice(PRIZES)  # Выбираем случайный приз
    await update.message.reply_text(
        f"🎉 Поздравляем! Ты выиграл: {prize} 🎉"
    )

# Обработчик квитанций (фото или документы)
async def handle_receipt(update: Update, context: CallbackContext):
    if update.message.photo or update.message.document:
        caption = f"Чек от @{update.effective_user.username} (ID: {update.effective_user.id})"
        if update.message.photo:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=update.message.photo[-1].file_id,
                caption=caption
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=update.message.document.file_id,
                caption=caption
            )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.")
    else:
        await update.message.reply_text("Пожалуйста, отправь чек о платеже.")

# Обработчик команды подтверждения оплаты (администратором)
async def confirm_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == int(ADMIN_ID):  # Проверка, что это администратор
        if context.args:
            message = ' '.join(context.args)
            if message.lower() == 'подтвердить':
                await update.message.reply_text(f"Оплата подтверждена. Пользователь получит попытки!")
                # Запускаем колесо фортуны после подтверждения
                await spin_wheel(update, context)
            else:
                await update.message.reply_text("Неверная команда. Используйте /confirm_payment подтверждение.")
        else:
            await update.message.reply_text("Введите команду /confirm_payment с аргументами для подтверждения.")

# Ошибки
async def error(update: Update, context: CallbackContext):
    logger.warning(f'Update {update} caused error {context.error}')

# Основная функция для запуска
def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play))
    application.add_handler(CommandHandler("confirm_payment", confirm_payment))  # Убираем pass_args
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))  # Обработка фото
    application.add_handler(MessageHandler(filters.Document(), handle_receipt))  # Обработка документов
    application.add_error_handler(error)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
