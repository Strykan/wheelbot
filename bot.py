import logging
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters
from dotenv import load_dotenv
import asyncio  # Для задержек

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

# Генерация клавиатуры для кнопок
def get_start_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Начать игру", callback_data="play")]])

def get_play_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Крутить колесо", callback_data="spin_wheel")]])

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

    await update.callback_query.message.reply_text(
        "Для того, чтобы сыграть, переведи деньги на следующие реквизиты:\n"
        "Сумма: 100 рублей\n\n"
        "После перевода отправь мне квитанцию о платеже. Я проверю и дам тебе попытки!"
    )

# Команда с реквизитами для оплаты
async def payment_info(update: Update, context: CallbackContext):
    # Удаляем предыдущее сообщение
    await update.callback_query.message.delete()

    await update.callback_query.message.reply_text(
        "Переведи деньги на следующие реквизиты:\n"
        "Сумма: 100 рублей\n\n"
        "После перевода отправь мне квитанцию о платеже, и я дам тебе попытки!"
    )

# Функция для вращения колеса фортуны с поочередным выводом призов
async def spin_wheel(update: Update, context: CallbackContext):
    # Удаляем предыдущее сообщение
    await update.callback_query.message.delete()

    # Анимация вращения (выводим призы поочередно)
    await update.callback_query.message.reply_text(
        "🔄 Вращаю колесо... Пожалуйста, подождите..."
    )

    # Пройдемся по всем призам и покажем их с задержкой
    for prize in PRIZES:
        await update.callback_query.message.edit_text(
            f"Вращение... \nПриз: {prize}"
        )
        await asyncio.sleep(0.5)  # Задержка перед показом следующего приза

    # После того как все призы были выведены, показываем финальный результат
    final_prize = random.choice(PRIZES)  # Выбираем случайный приз
    await update.callback_query.message.edit_text(
        f"🎉 Поздравляем! Ты выиграл: {final_prize} 🎉",
        reply_markup=get_play_keyboard()  # Кнопка для продолжения
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
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Подтвердить оплату", callback_data=f"confirm_payment:{user.id}"),
                 InlineKeyboardButton("Отклонить оплату", callback_data=f"decline_payment:{user.id}")]
            ])
        )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.")
    elif update.message.document:
        caption = f"Чек от @{user.username} (ID: {user.id})"
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=update.message.document.file_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Подтвердить оплату", callback_data=f"confirm_payment:{user.id}"),
                 InlineKeyboardButton("Отклонить оплату", callback_data=f"decline_payment:{user.id}")]
            ])
        )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.")
    else:
        await update.message.reply_text("Пожалуйста, отправьте чек о платеже.")

# Обработчик подтверждения или отклонения оплаты (администратором)
async def confirm_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:  # Проверка, что это администратор
        # Получаем user_id клиента из callback_data
        client_id = int(update.callback_query.data.split(":")[1])
        # Отправляем сообщение клиенту о подтверждении
        await context.bot.send_message(
            chat_id=client_id,
            text="Оплата прошла успешно! Теперь вы можете крутить колесо фортуны.",
            reply_markup=get_play_keyboard()  # Добавляем кнопку для игры
        )
        # Подтверждаем администратору
        await update.callback_query.answer("Оплата подтверждена.")
    else:
        await update.callback_query.answer("Только администратор может подтвердить оплату.")

async def decline_payment(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:  # Проверка, что это администратор
        # Получаем user_id клиента из callback_data
        client_id = int(update.callback_query.data.split(":")[1])
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
    
    # Обработка нажатия на кнопки
    if query.data == "play":
        await play(update, context)
    elif query.data == "payment_info":
        await payment_info(update, context)
    elif query.data == "spin_wheel":
        await spin_wheel(update, context)
    elif query.data.startswith("confirm_payment"):
        client_id = int(query.data.split(":")[1])
        await confirm_payment(update, context)
    elif query.data.startswith("decline_payment"):
        client_id = int(query.data.split(":")[1])
        await decline_payment(update, context)

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
