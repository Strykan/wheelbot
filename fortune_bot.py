import random
import json
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import os
from telegram import Update
from telegram.ext import Application, CommandHandler

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context):
    await update.message.reply_text("Привет! Я твой бот!")

if __name__ == '__main__':
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()


SECTORS = [
    "Выигрыш 100 рублей!",
    "Попробуй ещё раз",
    "Проигрыш",
    "Сюрприз!",
    "Двойной шанс",
    "Ничего",
    "Ты победитель дня!",
    "Подарок от Вселенной"
]

STATS_FILE = 'fortune_stats.json'

# Загрузка статистики из файла
def load_stats():
    try:
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Сохранение статистики в файл
def save_stats(stats):
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

# Обновление статистики
def update_user_stats(user_id, result):
    stats = load_stats()
    user_stats = stats.get(str(user_id), {})
    user_stats[result] = user_stats.get(result, 0) + 1
    stats[str(user_id)] = user_stats
    save_stats(stats)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Напиши /spin чтобы крутануть колесо фортуны!")

# Команда /spin с "анимацией" и сохранением статистики
async def spin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not use_attempt(user_id):
        await update.message.reply_text("У тебя нет попыток. Купи их с помощью команды /buy.")
        return

    message = await update.message.reply_text("Колесо начинает крутиться...")

    user_sectors = get_user_sectors(user_id)
    sectors = user_sectors if user_sectors else DEFAULT_SECTORS

    # Анимация
    for i in range(10):
        current = random.choice(sectors)
        await message.edit_text(f"Колесо: {current}")
        await asyncio.sleep(0.3 + i * 0.05)

    final_result = random.choice(sectors)
    await message.edit_text(f"Колесо остановилось! Выпадает: {final_result}")

    update_user_stats(user_id, final_result)

# Команда /stats — показывает статистику пользователя
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    stats = load_stats().get(user_id, {})
    if not stats:
        await update.message.reply_text("У тебя пока нет статистики. Попробуй крутануть колесо!")
    else:
        lines = [f"{key}: {value}" for key, value in stats.items()]
        await update.message.reply_text("Твоя статистика:\n" + "\n".join(lines))

# Основной запуск
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("spin", spin))
    app.add_handler(CommandHandler("stats", stats))

    print("Бот запущен!")
    app.run_polling()

ATTEMPTS_FILE = 'attempts.json'

def load_attempts():
    return load_json(ATTEMPTS_FILE)

def save_attempts(data):
    save_json(ATTEMPTS_FILE, data)

def get_attempts(user_id):
    attempts = load_attempts()
    return attempts.get(str(user_id), 0)

def add_attempts(user_id, count):
    attempts = load_attempts()
    user_id = str(user_id)
    attempts[user_id] = attempts.get(user_id, 0) + count
    save_attempts(attempts)

def use_attempt(user_id):
    attempts = load_attempts()
    user_id = str(user_id)
    if attempts.get(user_id, 0) > 0:
        attempts[user_id] -= 1
        save_attempts(attempts)
        return True
    return False

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        count = int(context.args[0])
        if count <= 0:
            raise ValueError
        add_attempts(user_id, count)
        await update.message.reply_text(f"Ты получил {count} попыток! У тебя теперь {get_attempts(user_id)}.")
    except (IndexError, ValueError):
        await update.message.reply_text("Напиши, сколько попыток хочешь купить. Например:\n/buy 3")

async def attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = get_attempts(user_id)
    await update.message.reply_text(f"У тебя {count} попыток.")

app.add_handler(CommandHandler("buy", buy))
app.add_handler(CommandHandler("attempts", attempts))

