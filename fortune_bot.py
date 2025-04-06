import random
import json
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = '7999095829:AAGkWkCIg8WuoqMnkyPHtl-QREB4T2bYKkU'

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
    message = await update.message.reply_text("Колесо начинает крутиться...")

    # Симуляция вращения
    for i in range(10):  # количество "шагов"
        current = random.choice(SECTORS)
        await message.edit_text(f"Колесо: {current}")
        await asyncio.sleep(0.3 + i * 0.05)  # замедление к концу

    # Итог
    final_result = random.choice(SECTORS)
    await message.edit_text(f"Колесо остановилось! Выпадает: {final_result}")

    # Обновление статистики
    user_id = update.effective_user.id
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
