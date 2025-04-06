import logging
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Для отслеживания, кто уже использовал свои попытки
user_attempts = {}

# Генерация клавиатуры для кнопок
def get_start_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Начать игру", callback_data="play")]])

def get_play_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Крутить колесо", callback_data="spin_wheel")]])

def get_purchase_attempts_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Купить 1 попытку за 100 рублей", callback_data="purchase_1_attempt")],
        [InlineKeyboardButton("Купить 3 попытки за 300 рублей", callback_data="purchase_3_attempts")],
        [InlineKeyboardButton("Купить 5 попыток за 500 рублей", callback_data="purchase_5_attempts")],
        [InlineKeyboardButton("Купить 10 попыток за 1000 рублей", callback_data="purchase_10_attempts")]
    ])

def get_play_disabled_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Вы уже использовали попытку, купите дополнительные", callback_data="purchase_more_attempts")]])

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

# Функция для вращения колеса фортуны с поочередным выводом призов
async def spin_wheel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Проверяем, если пользователь уже использовал свою попытку
    if user_id in user_attempts and user_attempts[user_id] > 0:
        # Уменьшаем количество оставшихся попыток
        user_attempts[user_id] -= 1
        if user_attempts[user_id] == 0:
            del user_attempts[user_id]
        
        # Убираем кнопку "Крутить колесо", если попытки закончились
        keyboard = get_play_disabled_keyboard() if user_attempts.get(user_id, 0) == 0 else get_play_keyboard()
        
        # Удаляем предыдущее сообщение
        await update.callback_query.message.delete()

        # Отправляем новое сообщение, что начинается вращение
        result_message = await update.callback_query.message.reply_text(
            "🔄 Вращаю колесо... Пожалуйста, подождите..."
        )

        # Пройдемся по всем призам и покажем их с задержкой
        for prize in PRIZES:
            await result_message.edit_text(
                f"Вращение... \nПриз: {prize}"
            )
            await asyncio.sleep(0.5)  # Задержка перед показом следующего приза

        # После того как все призы были выведены, показываем финальный результат
        final_prize = random.choice(PRIZES)  # Выбираем случайный приз
        await result_message.edit_text(
            f"🎉 Поздравляем! Ты выиграл: {final_prize} 🎉",
            reply_markup=keyboard  # Кнопка для продолжения будет заблокирована, если попытки закончились
        )
    else:
        # Если попытки закончились, предлагаем купить дополнительные
        await update.callback_query.message.reply_text(
            "Вы уже использовали все попытки! Хотите купить дополнительные?",
            reply_markup=get_purchase_attempts_keyboard()
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
            reply_markup=InlineKeyboardMarkup([[ 
                InlineKeyboardButton("Подтвердить оплату", callback_data=f"confirm_payment:{user.id}"),
                InlineKeyboardButton("Отклонить оплату", callback_data=f"decline_payment:{user.id}")
            ]])
        )
        await update.message.reply_text("Чек отправлен на проверку. Ожидайте подтверждения.")
    elif update.message.document:
        caption = f"Чек от @{user.username} (ID: {user.id})"
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=update.message.document.file_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[ 
                InlineKeyboardButton("Подтвердить оплату", callback_data=f"confirm_payment:{user.id}"),
                InlineKeyboardButton("Отклонить оплату", callback_data=f"decline_payment:{user.id}")
            ]])
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
        # Удаляем квитанцию и заменяем на сообщение о подтверждении
        await update.callback_query.message.delete()
        await update.callback_query.message.reply_text("Оплата подтверждена!")
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
    elif query.data == "purchase_more_attempts":
        await update.callback_query.message.reply_text(
            "Выберите, сколько попыток хотите купить:",
            reply_markup=get_purchase_attempts_keyboard()
        )
    elif query.data.startswith("purchase_"):
        purchase_amount = int(query.data.split("_")[1])  # Получаем количество попыток для покупки
        user_attempts[update.effective_user.id] = user_attempts.get(update.effective_user.id, 0) + purchase_amount
        await query.message.edit_text(f"Вы купили {purchase_amount} попыток. Можете крутить колесо!",
                                      reply_markup=get_play_keyboard())

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
