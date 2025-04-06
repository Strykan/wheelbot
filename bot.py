import logging
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
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

# Для отслеживания, кто сколько попыток использовал
user_attempts = {}

# Генерация клавиатуры для кнопок
def get_start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Начать игру", callback_data="play")],
        [InlineKeyboardButton("Купить 3 попытки", callback_data="buy_3_attempts")],
        [InlineKeyboardButton("Купить 5 попыток", callback_data="buy_5_attempts")],
        [InlineKeyboardButton("Купить 10 попыток", callback_data="buy_10_attempts")]
    ])

def get_play_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Крутить колесо", callback_data="spin_wheel")]])

def get_play_disabled_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Вы уже использовали попытку", callback_data="spin_wheel_disabled")]])

# Команда start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я — бот Колесо фортуны. Чтобы начать, выбери одну из опций ниже.",
        reply_markup=get_start_keyboard()
    )

# Функция для обработки покупки попыток
async def buy_attempts(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    attempts_to_buy = int(update.callback_query.data.split('_')[1])

    # Обновляем количество попыток пользователя
    if user_id not in user_attempts:
        user_attempts[user_id] = 0

    user_attempts[user_id] += attempts_to_buy

    await update.callback_query.message.edit_text(
        f"Вы купили {attempts_to_buy} попыток! Теперь у вас {user_attempts[user_id]} попыток.",
        reply_markup=get_play_keyboard()
    )

# Функция для вращения колеса фортуны с поочередным выводом призов
async def spin_wheel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Проверяем, если у пользователя есть попытки
    if user_id not in user_attempts or user_attempts[user_id] == 0:
        # Если попыток нет, отправляем сообщение
        await update.callback_query.message.reply_text(
            "У вас нет попыток! Купите их для игры.",
            reply_markup=get_start_keyboard()
        )
        return

    # Уменьшаем количество попыток
    user_attempts[user_id] -= 1

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
        reply_markup=get_play_disabled_keyboard()  # Кнопка для продолжения будет заблокирована
    )

# Обработчик inline кнопок
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки
    
    # Обработка нажатия на кнопки
    if query.data == "play":
        await play(update, context)
    elif query.data == "spin_wheel":
        await spin_wheel(update, context)
    elif query.data.startswith("buy_"):
        await buy_attempts(update, context)

# Ошибки
async def error(update: Update, context: CallbackContext):
    logger.warning(f'Update {update} caused error {context.error}')

# Основная функция для запуска
def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))  # Обработчик inline кнопок
    application.add_error_handler(error)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
