import logging
import os
import random
import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    filters
)
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
conn = sqlite3.connect('wheel_of_fortune.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы
cursor.execute('''CREATE TABLE IF NOT EXISTS user_attempts
                  (user_id INTEGER PRIMARY KEY, paid INTEGER, used INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS payment_methods
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT NOT NULL,
                   details TEXT NOT NULL,
                   is_active BOOLEAN DEFAULT 1)''')
conn.commit()

# Клавиатуры
def get_start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 Начать игру", callback_data="play")],
        [InlineKeyboardButton("ℹ️ Мои попытки", callback_data="check_attempts")]
    ])

def get_play_keyboard(user_id):
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result and result[0] > result[1]:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Крутить колесо", callback_data="spin_wheel")],
            [InlineKeyboardButton("💰 Купить еще попыток", callback_data="play")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Купить попытки", callback_data="play")],
        [InlineKeyboardButton("ℹ️ Мои попытки", callback_data="check_attempts")]
    ])

def get_payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 попытка — 50 руб", callback_data="pay_1")],
        [InlineKeyboardButton("3 попытки — 130 руб (↘️10%)", callback_data="pay_3")],
        [InlineKeyboardButton("5 попыток — 200 руб (↘️20%)", callback_data="pay_5")],
        [InlineKeyboardButton("10 попыток — 350 руб (↘️30%)", callback_data="pay_10")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]
    ])

def get_payment_methods_keyboard():
    cursor.execute('SELECT id, name FROM payment_methods WHERE is_active = 1')
    methods = cursor.fetchall()
    keyboard = []
    for method in methods:
        keyboard.append([InlineKeyboardButton(method[1], callback_data=f"method_{method[0]}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_payment_methods_keyboard():
    cursor.execute('SELECT id, name, is_active FROM payment_methods')
    methods = cursor.fetchall()
    keyboard = []
    for method in methods:
        status = "✅" if method[2] else "❌"
        keyboard.append([
            InlineKeyboardButton(f"{status} {method[1]}", callback_data=f"admin_method_{method[0]}"),
            InlineKeyboardButton("✏️", callback_data=f"edit_method_{method[0]}"),
            InlineKeyboardButton("🗑", callback_data=f"delete_method_{method[0]}")
        ])
    keyboard.append([InlineKeyboardButton("➕ Добавить способ", callback_data="add_payment_method")])
    keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data="admin_back")])
    return InlineKeyboardMarkup(keyboard)

# Функции работы с БД
def save_user_attempts(user_id, paid_attempts, used_attempts):
    try:
        cursor.execute(
            'INSERT OR REPLACE INTO user_attempts (user_id, paid, used) VALUES (?, ?, ?)',
            (user_id, paid_attempts, used_attempts)
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")

def add_payment_method(name, details):
    try:
        cursor.execute(
            'INSERT INTO payment_methods (name, details) VALUES (?, ?)',
            (name, details)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False

def update_payment_method(method_id, name, details):
    try:
        cursor.execute(
            'UPDATE payment_methods SET name = ?, details = ? WHERE id = ?',
            (name, details, method_id)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False

def toggle_payment_method(method_id):
    try:
        cursor.execute(
            'UPDATE payment_methods SET is_active = NOT is_active WHERE id = ?',
            (method_id,)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False

def delete_payment_method(method_id):
    try:
        cursor.execute(
            'DELETE FROM payment_methods WHERE id = ?',
            (method_id,)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False

def get_payment_method(method_id):
    try:
        cursor.execute(
            'SELECT name, details FROM payment_methods WHERE id = ?',
            (method_id,)
        )
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None

# Обработчики команд
async def start(update: Update, context: CallbackContext):
    if update.message.from_user.id == ADMIN_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠 Управление ботом", callback_data="admin_panel")],
            [InlineKeyboardButton("🎰 Начать игру", callback_data="play")]
        ])
        await update.message.reply_text(
            "👋 Добро пожаловать, администратор!",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            "🎡 Добро пожаловать в <b>Колесо Фортуны</b>!\n\n"
            "💎 Крутите колесо и выигрывайте призы!\n"
            "💰 Попытки можно купить или выиграть в игре.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_start_keyboard()
        )

async def admin_panel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Управление способами оплаты", callback_data="manage_payment_methods")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_start")]
    ])
    
    await query.message.edit_text(
        "🛠 <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def manage_payment_methods(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    await query.message.edit_text(
        "💳 <b>Управление способами оплаты</b>\n\n"
        "Список доступных способов оплаты:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_payment_methods_keyboard()
    )

async def add_payment_method_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    context.user_data['adding_payment_method'] = True
    await query.message.edit_text(
        "Введите название нового способа оплаты:",
        reply_markup=InlineKeyboardMarkup(
            [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
        )
    )

async def edit_payment_method_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    method_id = int(query.data.split('_')[-1])
    context.user_data['editing_payment_method'] = method_id
    await query.message.edit_text(
        "Введите новое название и реквизиты в формате:\n\n"
        "<code>Название\nРеквизиты</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
        ])
    )

async def handle_payment_method_text(update: Update, context: CallbackContext):
    if 'adding_payment_method' in context.user_data:
        # Добавление нового способа оплаты
        name = update.message.text
        context.user_data['new_payment_name'] = name
        context.user_data['adding_payment_method'] = False
        context.user_data['adding_payment_details'] = True
        
        await update.message.reply_text(
            "Теперь введите реквизиты для этого способа оплаты:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
            ])
        )
    elif 'adding_payment_details' in context.user_data:
        # Сохранение нового способа оплаты
        details = update.message.text
        name = context.user_data['new_payment_name']
        
        if add_payment_method(name, details):
            await update.message.reply_text(
                f"✅ Способ оплаты <b>{name}</b> успешно добавлен!",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при добавлении способа оплаты"
            )
        
        # Очищаем временные данные
        context.user_data.pop('new_payment_name', None)
        context.user_data.pop('adding_payment_details', None)
        
        # Возвращаемся к списку способов оплаты
        await manage_payment_methods(update, context)
    elif 'editing_payment_method' in context.user_data:
        # Редактирование существующего способа оплаты
        method_id = context.user_data['editing_payment_method']
        try:
            name, details = update.message.text.split('\n', 1)
            if update_payment_method(method_id, name, details):
                await update.message.reply_text(
                    f"✅ Способ оплаты успешно обновлен!",
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_text(
                    "❌ Произошла ошибка при обновлении способа оплаты"
                )
        except ValueError:
            await update.message.reply_text(
                "Неправильный формат. Введите название и реквизиты на отдельных строках."
            )
            return
        
        # Очищаем временные данные
        context.user_data.pop('editing_payment_method', None)
        
        # Возвращаемся к списку способов оплаты
        await manage_payment_methods(update, context)

async def toggle_payment_method_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    method_id = int(query.data.split('_')[-1])
    if toggle_payment_method(method_id):
        await query.message.edit_reply_markup(reply_markup=get_admin_payment_methods_keyboard())
    else:
        await query.answer("Ошибка при изменении статуса способа оплаты", show_alert=True)

async def delete_payment_method_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    method_id = int(query.data.split('_')[-1])
    if delete_payment_method(method_id):
        await query.message.edit_reply_markup(reply_markup=get_admin_payment_methods_keyboard())
    else:
        await query.answer("Ошибка при удалении способа оплаты", show_alert=True)

async def play(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "🎯 Выберите количество попыток:\n\n"
        "💎 1 попытка — 50 руб\n"
        "💎 3 попытки — 130 руб (экономия 10%)\n"
        "💎 5 попыток — 200 руб (экономия 20%)\n"
        "💎 10 попыток — 350 руб (экономия 30%)",
        reply_markup=get_payment_keyboard()
    )

async def check_attempts(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        text = (
            f"📊 Ваши попытки:\n\n"
            f"💎 Всего куплено: {result[0]}\n"
            f"🔄 Использовано: {result[1]}\n"
            f"🎯 Осталось: {result[0] - result[1]}"
        )
    else:
        text = "У вас пока нет попыток. Хотите купить?"
    
    await query.message.edit_text(
        text,
        reply_markup=get_play_keyboard(user_id)
    )

async def handle_payment_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    choice = query.data.split("_")[1]
    amounts = {"1": 50, "3": 130, "5": 200, "10": 350}
    
    if choice in amounts:
        context.chat_data["payment_choice"] = choice
        await query.message.edit_text(
            f"💳 Вы выбрали <b>{choice}</b> попыток за <b>{amounts[choice]} руб</b>.\n\n"
            "Теперь выберите способ оплаты:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_payment_methods_keyboard()
        )
    else:
        await query.answer("Неверный выбор")

async def show_payment_method(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    method_id = int(query.data.split("_")[1])
    method = get_payment_method(method_id)
    
    if not method:
        await query.answer("Способ оплаты не найден", show_alert=True)
        return
    
    name, details = method
    choice = context.chat_data.get("payment_choice")
    amounts = {"1": 50, "3": 130, "5": 200, "10": 350}
    amount = amounts.get(choice, 0)
    
    await query.message.edit_text(
        f"💳 <b>Способ оплаты: {name}</b>\n\n"
        f"💎 Количество попыток: {choice}\n"
        f"💰 Сумма к оплате: {amount} руб\n\n"
        f"<b>Реквизиты для оплаты:</b>\n"
        f"{details}\n\n"
        "После оплаты отправьте фото или скриншот чека в этот чат.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [InlineKeyboardButton("🔙 Выбрать другой способ", callback_data="back_to_payment_methods")]
        )
    )

async def back_to_payment_methods(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "💳 Выберите способ оплаты:",
        reply_markup=get_payment_methods_keyboard()
    )

# ... (остальные функции остаются без изменений, как в предыдущем коде)

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    
    # Обработчики callback-кнопок
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(manage_payment_methods, pattern="^manage_payment_methods$"))
    application.add_handler(CallbackQueryHandler(add_payment_method_handler, pattern="^add_payment_method$"))
    application.add_handler(CallbackQueryHandler(edit_payment_method_handler, pattern="^edit_method_"))
    application.add_handler(CallbackQueryHandler(toggle_payment_method_handler, pattern="^admin_method_"))
    application.add_handler(CallbackQueryHandler(delete_payment_method_handler, pattern="^delete_method_"))
    application.add_handler(CallbackQueryHandler(show_payment_method, pattern="^method_"))
    application.add_handler(CallbackQueryHandler(back_to_payment_methods, pattern="^back_to_payment_methods$"))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_receipt))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_payment_method_text))
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        conn.close()
        logger.info("Database connection closed")