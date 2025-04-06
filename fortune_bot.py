import os
import random
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Токен бота
BOT_TOKEN = os.getenv("7999095829:AAGkWkCIg8WuoqMnkyPHtl-QREB4T2bYKkU")

# Админ для проверки оплаты
ADMIN_ID = 271722022  # Замените на свой ID в Telegram

# Данные для игры
prizes = {
    1: "Приз 1: 10 монет",
    2: "Приз 2: 20 монет",
    3: "Приз 3: 50 монет",
    4: "Приз 4: 100 монет",
    5: "Приз 5: Бесплатная попытка",
    6: "Приз 6: Джекпот! 500 монет"
}

# Эмодзи сектора колеса
wheel_sectors = [
    "🔴", "🟢", "🟡", "🔵", "🟠", "🟣"
]

# Хранилище пользователей и их попыток
user_attempts = {}

# Функция для отправки анимации вращения колеса
async def spin_wheel_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    animation_url = "https://media.giphy.com/media/xT1XGV9Dbb1Jd13ZpS/giphy.gif"
    await update.message.reply_animation(animation_url, caption="Кручу колесо фортуны...")

# Стартовая команда
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой бот для игры в Колесо Фортуны! Чтобы начать, нужно оплатить попытку. "
        "Отправь мне чек для подтверждения оплаты. После подтверждения ты получишь возможность крутить колесо!"
    )

# Обработка чека и добавление попыток
async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo or update.message.document:
        # Отправка чека админу для подтверждения
        caption = f"Чек от @{update.effective_user.username} (ID: {user_id})"
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

# Подтверждение оплаты администратором
async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("У вас нет прав для подтверждения.")
    
    user_id = int(context.args[0])
    user_attempts[user_id] = 3  # Например, даём 3 попытки
    await context.bot.send_message(user_id, "Оплата подтверждена! Вы получили 3 попытки.")
    await update.message.reply_text(f"Оплата для пользователя {user_id} подтверждена. Он получил 3 попытки.")

# Функция для выполнения вращения
async def spin_wheel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_attempts or user_attempts[user_id] <= 0:
        return await update.message.reply_text("У вас нет попыток. Пожалуйста, оплатите их.")

    # Уменьшаем количество попыток
    user_attempts[user_id] -= 1

    # Отправляем анимацию вращения
    await spin_wheel_animation(update, context)

    # Симулируем вращение и определяем сектор
    wheel_result = random.randint(0, 5)  # Вращаем колесо
    prize = prizes[wheel_result + 1]  # Приз по результату сектора

    # Отправляем результат
    await update.message.reply_text(f"Колесо остановилось на секторе {wheel_sectors[wheel_result]}! {prize}")
    await update.message.reply_text(f"У вас осталось {user_attempts[user_id]} попыток.")

# Обработчик команд
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.DOCUMENT, handle_receipt))
    app.add_handler(CommandHandler("approve", approve_payment))
    app.add_handler(CommandHandler("spin", spin_wheel))

    app.run_polling()

if __name__ == '__main__':
    main()
