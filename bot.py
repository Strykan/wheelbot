import logging
import os
import random
import asyncio
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DAILY_BONUS = 1  # Количество бесплатных попыток за ежедневный бонус

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('wheel_of_fortune.db', check_same_thread=False)
    cursor = conn.cursor()

    # Создаем таблицы
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_attempts
                      (user_id INTEGER PRIMARY KEY, 
                       paid INTEGER DEFAULT 0, 
                       used INTEGER DEFAULT 0,
                       last_bonus_date TEXT,
                       referral_code TEXT UNIQUE,
                       referred_by INTEGER DEFAULT NULL,
                       referrals_count INTEGER DEFAULT 0)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS payment_methods
                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       name TEXT NOT NULL UNIQUE,
                       details TEXT NOT NULL,
                       is_active BOOLEAN DEFAULT 1)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions
                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER NOT NULL,
                       amount INTEGER NOT NULL,
                       attempts INTEGER NOT NULL,
                       status TEXT NOT NULL,
                       receipt_id TEXT,
                       admin_id INTEGER,
                       created_at TEXT NOT NULL,
                       updated_at TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS prizes
                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER NOT NULL,
                       prize_type TEXT NOT NULL,
                       value TEXT NOT NULL,
                       is_claimed BOOLEAN DEFAULT 0,
                       created_at TEXT NOT NULL)''')

    conn.commit()
    return conn, cursor

conn, cursor = init_db()

# Валидация ввода
def validate_input(text, max_length=1000):
    if not text or len(text.strip()) == 0:
        return False
    if len(text) > max_length:
        return False
    return True

# Клавиатуры
def get_start_keyboard(user_id=None):
    buttons = [
        [InlineKeyboardButton("🎰 Начать игру", callback_data="play")],
        [InlineKeyboardButton("ℹ️ Мои попытки", callback_data="check_attempts")],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily_bonus")],
        [InlineKeyboardButton("👥 Реферальная программа", callback_data="referral_info")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton("🛠 Панель администратора", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def get_play_keyboard(user_id):
    attempts = get_user_attempts(user_id)
    if attempts['remaining'] > 0:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Крутить колесо (1 попытка)", callback_data="spin_wheel")],
            [InlineKeyboardButton("💰 Купить еще попыток", callback_data="buy_attempts")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Купить попытки", callback_data="buy_attempts")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]
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
    methods = get_payment_methods()
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

def get_admin_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Управление оплатой", callback_data="manage_payment_methods")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_start")]
    ])

# Функции работы с БД
def get_user_attempts(user_id):
    cursor.execute('SELECT paid, used, last_bonus_date FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    if result:
        return {
            'paid': result[0],
            'used': result[1],
            'remaining': result[0] - result[1],
            'last_bonus_date': result[2]
        }
    return {'paid': 0, 'used': 0, 'remaining': 0, 'last_bonus_date': None}

def update_user_attempts(user_id, paid=0, used=0, last_bonus_date=None):
    try:
        cursor.execute(
            '''INSERT OR IGNORE INTO user_attempts (user_id) VALUES (?)''',
            (user_id,)
        )
        
        update_query = '''UPDATE user_attempts SET '''
        params = []
        
        if paid != 0:
            update_query += '''paid = paid + ?, '''
            params.append(paid)
        
        if used != 0:
            update_query += '''used = used + ?, '''
            params.append(used)
        
        if last_bonus_date:
            update_query += '''last_bonus_date = ?, '''
            params.append(last_bonus_date)
        
        update_query = update_query[:-2]
        update_query += ''' WHERE user_id = ?'''
        params.append(user_id)
        
        cursor.execute(update_query, params)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return False

def get_payment_methods():
    try:
        cursor.execute('SELECT id, name, details FROM payment_methods WHERE is_active = 1')
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        return []

def add_payment_method(name, details):
    if not validate_input(name, 50) or not validate_input(details, 1000):
        return False
        
    try:
        cursor.execute('SELECT id FROM payment_methods WHERE name = ?', (name,))
        if cursor.fetchone():
            logger.warning(f"Способ оплаты '{name}' уже существует")
            return False
            
        cursor.execute(
            'INSERT INTO payment_methods (name, details) VALUES (?, ?)',
            (name, details)
        )
        conn.commit()
        logger.info(f"Добавлен способ оплаты: {name}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return False

def update_payment_method(method_id, name, details):
    if not validate_input(name, 50) or not validate_input(details, 1000):
        return False
        
    try:
        cursor.execute(
            'UPDATE payment_methods SET name = ?, details = ? WHERE id = ?',
            (name, details, method_id)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
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
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
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
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return False

def get_payment_method(method_id):
    try:
        cursor.execute(
            'SELECT name, details FROM payment_methods WHERE id = ?',
            (method_id,)
        )
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        return None

def create_transaction(user_id, amount, attempts, status='pending'):
    try:
        now = datetime.now().isoformat()
        cursor.execute(
            '''INSERT INTO transactions 
               (user_id, amount, attempts, status, created_at) 
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, amount, attempts, status, now)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return None

def update_transaction(transaction_id, status, admin_id=None, receipt_id=None):
    try:
        now = datetime.now().isoformat()
        cursor.execute(
            '''UPDATE transactions SET 
               status = ?, 
               admin_id = ?,
               receipt_id = ?,
               updated_at = ?
               WHERE id = ?''',
            (status, admin_id, receipt_id, now, transaction_id)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return False

def add_prize(user_id, prize_type, value):
    try:
        now = datetime.now().isoformat()
        cursor.execute(
            '''INSERT INTO prizes 
               (user_id, prize_type, value, created_at) 
               VALUES (?, ?, ?, ?)''',
            (user_id, prize_type, value, now)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return False

def get_unclaimed_prizes(user_id):
    try:
        cursor.execute(
            '''SELECT id, prize_type, value FROM prizes 
               WHERE user_id = ? AND is_claimed = 0''',
            (user_id,)
        )
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        return []

def claim_prize(prize_id):
    try:
        cursor.execute(
            '''UPDATE prizes SET is_claimed = 1 WHERE id = ?''',
            (prize_id,)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return False

def generate_referral_code(user_id):
    code = f"REF{user_id}{random.randint(1000, 9999)}"
    try:
        cursor.execute(
            '''UPDATE user_attempts SET referral_code = ? WHERE user_id = ?''',
            (code, user_id)
        )
        conn.commit()
        return code
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return None

def get_referral_info(user_id):
    try:
        cursor.execute(
            '''SELECT referral_code, referred_by, referrals_count 
               FROM user_attempts WHERE user_id = ?''',
            (user_id,)
        )
        result = cursor.fetchone()
        if result:
            return {
                'code': result[0],
                'referred_by': result[1],
                'count': result[2]
            }
        return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        return None

def process_referral(user_id, referral_code):
    try:
        cursor.execute(
            '''SELECT user_id FROM user_attempts WHERE referral_code = ?''',
            (referral_code,)
        )
        referrer = cursor.fetchone()
        if not referrer:
            return False
            
        referrer_id = referrer[0]
        
        cursor.execute(
            '''UPDATE user_attempts SET referred_by = ? WHERE user_id = ?''',
            (referrer_id, user_id)
        )
        
        cursor.execute(
            '''UPDATE user_attempts 
               SET referrals_count = referrals_count + 1,
                   paid = paid + 1 
               WHERE user_id = ?''',
            (referrer_id,)
        )
        
        cursor.execute(
            '''UPDATE user_attempts SET paid = paid + 1 WHERE user_id = ?''',
            (user_id,)
        )
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
        return False

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    if args and args[0].startswith('ref'):
        referral_code = args[0][3:]
        if process_referral(user.id, referral_code):
            await update.message.reply_text(
                "🎉 Вы получили +1 попытку за регистрацию по реферальной ссылке!",
                parse_mode=ParseMode.HTML
            )
    
    ref_info = get_referral_info(user.id)
    if ref_info and not ref_info['code']:
        generate_referral_code(user.id)
    
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Добро пожаловать, администратор!",
            reply_markup=get_start_keyboard(ADMIN_ID)
        )
    else:
        await update.message.reply_text(
            "🎡 Добро пожаловать в <b>Колесо Фортуны</b>!\n\n"
            "💎 Крутите колесо и выигрывайте призы!\n"
            "💰 Попытки можно купить, получить за рефералов или ежедневный бонус.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_start_keyboard()
        )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    await query.message.edit_text(
        "🛠 <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )

async def manage_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    await query.message.edit_text(
        "💳 <b>Управление способами оплаты</b>\n\n"
        "Список доступных способов оплаты:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_payment_methods_keyboard()
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    try:
        cursor.execute('SELECT COUNT(*) FROM user_attempts')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(paid), SUM(used) FROM user_attempts')
        attempts = cursor.fetchone()
        total_paid = attempts[0] or 0
        total_used = attempts[1] or 0
        
        cursor.execute('''SELECT status, COUNT(*), SUM(amount) 
                          FROM transactions GROUP BY status''')
        transactions = cursor.fetchall()
        
        stats_text = [
            "📊 <b>Статистика бота</b>\n\n",
            f"👥 Всего пользователей: <b>{total_users}</b>",
            f"🎯 Всего попыток: <b>{total_paid}</b> (использовано: <b>{total_used}</b>)",
            "\n💳 <b>Транзакции:</b>"
        ]
        
        for status, count, amount in transactions:
            stats_text.append(
                f"▪️ {status.capitalize()}: <b>{count}</b> на сумму <b>{amount or 0} руб</b>"
            )
        
        await query.message.edit_text(
            "\n".join(stats_text),
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        await query.answer("❌ Ошибка при получении статистики", show_alert=True)

async def add_payment_method_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    context.user_data['adding_payment_method'] = True
    await query.message.edit_text(
        "Введите название нового способа оплаты (макс. 50 символов):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
        ])
    )

async def edit_payment_method_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    method_id = int(query.data.split('_')[-1])
    context.user_data['editing_payment_method'] = method_id
    method = get_payment_method(method_id)
    
    if method:
        await query.message.edit_text(
            f"✏️ <b>Редактирование способа оплаты</b>\n\n"
            f"Текущие данные:\n"
            f"▪️ Название: <code>{method[0]}</code>\n"
            f"▪️ Реквизиты: <code>{method[1]}</code>\n\n"
            "Введите новые данные в формате:\n"
            "<code>Новое название\nНовые реквизиты</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
            ])
        )
    else:
        await query.answer("❌ Способ оплаты не найден", show_alert=True)

async def handle_payment_method_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'adding_payment_method' in context.user_data:
        name = update.message.text.strip()
        if not validate_input(name, 50):
            await update.message.reply_text(
                "❌ Название не может быть пустым или превышать 50 символов. Попробуйте снова.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                ])
            )
            return
            
        context.user_data['new_payment_name'] = name
        context.user_data['adding_payment_method'] = False
        context.user_data['adding_payment_details'] = True
        
        await update.message.reply_text(
            "Теперь введите реквизиты для этого способа оплаты (макс. 1000 символов):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
            ])
        )
    
    elif 'adding_payment_details' in context.user_data:
        details = update.message.text.strip()
        if not validate_input(details, 1000):
            await update.message.reply_text(
                "❌ Реквизиты не могут быть пустыми или превышать 1000 символов. Попробуйте снова.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                ])
            )
            return
            
        name = context.user_data.get('new_payment_name')
        if not name:
            await update.message.reply_text(
                "❌ Ошибка: не найдено название способа оплаты",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                ])
            )
            return
            
        if add_payment_method(name, details):
            await update.message.reply_text(
                f"✅ Способ оплаты <b>{name}</b> успешно добавлен!",
                parse_mode=ParseMode.HTML
            )
            context.user_data.pop('new_payment_name', None)
            context.user_data.pop('adding_payment_details', None)
            await manage_payment_methods(update, context)
        else:
            await update.message.reply_text(
                "❌ Не удалось добавить способ оплаты. Возможно, такое название уже существует.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                ])
            )
    
    elif 'editing_payment_method' in context.user_data:
        method_id = context.user_data['editing_payment_method']
        try:
            text = update.message.text.strip()
            if not text:
                await update.message.reply_text(
                    "❌ Данные не могут быть пустыми.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                    ])
                )
                return
                
            parts = text.split('\n', 1)
            if len(parts) != 2:
                await update.message.reply_text(
                    "❌ Неверный формат. Введите название и реквизиты на отдельных строках.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                    ])
                )
                return
                
            name, details = parts
            name = name.strip()
            details = details.strip()
            
            if not validate_input(name, 50) or not validate_input(details, 1000):
                await update.message.reply_text(
                    "❌ Название или реквизиты не соответствуют требованиям.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                    ])
                )
                return
                
            if update_payment_method(method_id, name, details):
                await update.message.reply_text(
                    "✅ Способ оплаты успешно обновлен!",
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_text(
                    "❌ Не удалось обновить способ оплаты.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                    ])
                )
        except Exception as e:
            logger.error(f"Ошибка при редактировании способа оплаты: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обновлении способа оплаты.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
                ])
            )
        finally:
            context.user_data.pop('editing_payment_method', None)
            await manage_payment_methods(update, context)

async def toggle_payment_method_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    method_id = int(query.data.split('_')[-1])
    if toggle_payment_method(method_id):
        await query.message.edit_reply_markup(reply_markup=get_admin_payment_methods_keyboard())
    else:
        await query.answer("❌ Ошибка при изменении статуса способа оплаты", show_alert=True)

async def delete_payment_method_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    method_id = int(query.data.split('_')[-1])
    if delete_payment_method(method_id):
        await query.message.edit_reply_markup(reply_markup=get_admin_payment_methods_keyboard())
    else:
        await query.answer("❌ Ошибка при удалении способа оплаты", show_alert=True)

async def buy_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def check_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    attempts = get_user_attempts(user_id)
    
    text = (
        f"📊 <b>Ваши попытки</b>\n\n"
        f"💎 Всего куплено: <b>{attempts['paid']}</b>\n"
        f"🔄 Использовано: <b>{attempts['used']}</b>\n"
        f"🎯 Осталось: <b>{attempts['remaining']}</b>"
    )
    
    await query.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_play_keyboard(user_id)
    )

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    attempts = get_user_attempts(user_id)
    
    now = datetime.now().date()
    last_bonus_date = datetime.fromisoformat(attempts['last_bonus_date']).date() if attempts['last_bonus_date'] else None
    
    if last_bonus_date and last_bonus_date == now:
        await query.answer("🎁 Вы уже получали бонус сегодня. Приходите завтра!", show_alert=True)
        return
    
    update_user_attempts(
        user_id=user_id,
        paid=DAILY_BONUS,
        last_bonus_date=datetime.now().isoformat()
    )
    
    await query.message.edit_text(
        f"🎁 <b>Ежедневный бонус</b>\n\n"
        f"Вам начислено <b>{DAILY_BONUS}</b> бесплатных попыток!\n\n"
        f"🎯 Теперь у вас <b>{attempts['remaining'] + DAILY_BONUS}</b> доступных попыток.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_play_keyboard(user_id)
    )

async def referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    ref_info = get_referral_info(user_id)
    
    if not ref_info or not ref_info['code']:
        ref_info = {'code': generate_referral_code(user_id), 'count': 0}
    
    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        f"🔗 Ваша реферальная ссылка:\n"
        f"<code>https://t.me/{(await context.bot.get_me()).username}?start=ref{ref_info['code']}</code>\n\n"
        f"💎 За каждого приглашенного друга вы получаете:\n"
        f"▪️ +1 бесплатная попытка для вас\n"
        f"▪️ +1 бесплатная попытка для друга\n\n"
        f"📊 Всего приглашено: <b>{ref_info['count']}</b> человек"
    )
    
    await query.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]
        ])
    )

async def handle_payment_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    choice = query.data.split("_")[1]
    amounts = {"1": 50, "3": 130, "5": 200, "10": 350}
    attempts = {"1": 1, "3": 3, "5": 5, "10": 10}
    
    if choice in amounts:
        context.chat_data["payment_choice"] = choice
        context.chat_data["payment_amount"] = amounts[choice]
        context.chat_data["payment_attempts"] = attempts[choice]
        
        await query.message.edit_text(
            f"💳 Вы выбрали <b>{choice}</b> попыток за <b>{amounts[choice]} руб</b>.\n\n"
            "Теперь выберите способ оплаты:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_payment_methods_keyboard()
        )
    else:
        await query.answer("❌ Неверный выбор", show_alert=True)

async def show_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    method_id = int(query.data.split("_")[1])
    method = get_payment_method(method_id)
    
    if not method:
        await query.answer("❌ Способ оплаты не найден", show_alert=True)
        return
    
    name, details = method
    choice = context.chat_data.get("payment_choice")
    amount = context.chat_data.get("payment_amount", 0)
    
    transaction_id = create_transaction(
        user_id=query.from_user.id,
        amount=amount,
        attempts=context.chat_data["payment_attempts"],
        status='pending'
    )
    
    if not transaction_id:
        await query.answer("❌ Ошибка при создании транзакции", show_alert=True)
        return
    
    context.chat_data["current_transaction"] = transaction_id
    
    await query.message.edit_text(
        f"💳 <b>Способ оплаты: {name}</b>\n\n"
        f"💎 Количество попыток: {choice}\n"
        f"💰 Сумма к оплате: {amount} руб\n\n"
        f"<b>Реквизиты для оплаты:</b>\n"
        f"{details}\n\n"
        "После оплаты отправьте фото или скриншот чека в этот чат.\n"
        "❗️ В комментарии к платежу укажите ID: <code>{transaction_id}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Выбрать другой способ", callback_data="back_to_payment_methods")]
        ])
    )

async def back_to_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "💳 Выберите способ оплаты:",
        reply_markup=get_payment_methods_keyboard()
    )

async def spin_wheel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    attempts = get_user_attempts(user_id)
    
    if attempts['remaining'] <= 0:
        await query.answer("❌ У вас нет доступных попыток!", show_alert=True)
        return
    
    if not update_user_attempts(user_id=user_id, used=1):
        await query.answer("❌ Ошибка при использовании попытки", show_alert=True)
        return
    
    wheel_segments = ["🍒", "🍋", "🍊", "🍇", "🍉", "💰", "🎁", "⭐", "🍀"]
    segment_weights = [15, 15, 15, 15, 10, 5, 5, 10, 10]
    
    selected_index = random.choices(range(len(wheel_segments)), weights=segment_weights, k=1)[0]
    selected_segment = wheel_segments[selected_index]
    
    prize_mapping = {
        "🍒": ("10 рублей", "money", "10"),
        "🍋": ("20 рублей", "money", "20"),
        "🍊": ("Бесплатная попытка", "attempt", "1"),
        "🍇": ("5 рублей", "money", "5"),
        "🍉": ("Конфетка", "other", "candy"),
        "💰": ("100 рублей", "money", "100"),
        "🎁": ("Подарок", "other", "gift"),
        "⭐": ("5 бесплатных попыток", "attempt", "5"),
        "🍀": ("Скидка 10% на след. игру", "discount", "10")
    }
    prize_name, prize_type, prize_value = prize_mapping.get(selected_segment, ("Ничего", "other", "none"))
    
    add_prize(user_id, prize_type, prize_value)
    
    message = await query.message.reply_text(
        "🎡 <b>Колесо Фортуны</b>\n\n"
        f"{' ' * 8}👆\n"
        f"{' '.join(wheel_segments)}\n\n"
        "🌀 Крутим колесо...",
        parse_mode=ParseMode.HTML
    )
    
    spin_duration = 3
    frames = 15
    slowdown_start = 10
    
    for frame in range(frames):
        wheel_segments.insert(0, wheel_segments.pop())
        
        if frame < slowdown_start:
            delay = 0.15
        else:
            delay = 0.15 + (frame - slowdown_start) * 0.1
        
        await message.edit_text(
            "🎡 <b>Колесо Фортуны</b>\n\n"
            f"{' ' * 8}👆\n"
            f"{' '.join(wheel_segments)}\n\n"
            f"{'🌀' * (frame % 3 + 1)} Крутим колесо...",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(delay)
    
    while wheel_segments[-1] != selected_segment:
        wheel_segments.insert(0, wheel_segments.pop())
        await message.edit_text(
            "🎡 <b>Колесо Фортуны</b>\n\n"
            f"{' ' * 8}👆\n"
            f"{' '.join(wheel_segments)}\n\n"
            "🛑 Останавливается...",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(0.3)
    
    attempts = get_user_attempts(user_id)
    
    await message.edit_text(
        f"🎉 <b>Поздравляем!</b>\n\n"
        f"🏆 Вы выиграли: <b>{prize_name}</b>\n\n"
        f"🔄 Осталось попыток: <b>{attempts['remaining']}</b>\n\n"
        "Хотите крутить еще?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_play_keyboard(user_id)
    )
    
    try:
        await query.message.delete()
    except:
        pass

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    transaction_id = context.chat_data.get("current_transaction")
    
    if not transaction_id:
        await update.message.reply_text(
            "❌ Сначала выберите количество попыток через меню.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Купить попытки", callback_data="buy_attempts")]
            ])
        )
        return
        
    if not (update.message.photo or update.message.document):
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте чек о платеже (фото или документ).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]
            ])
        )
        return
    
    receipt_id = update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id
    update_transaction(
        transaction_id=transaction_id,
        status='pending',
        receipt_id=receipt_id
    )
    
    cursor.execute(
        '''SELECT amount, attempts FROM transactions WHERE id = ?''',
        (transaction_id,)
    )
    amount, attempts = cursor.fetchone()
    
    caption = (
        f"📤 Новый чек от @{user.username}\n"
        f"🆔 ID: {user.id}\n"
        f"💎 Попыток: {attempts}\n"
        f"💰 Сумма: {amount} руб\n"
        f"📝 ID транзакции: {transaction_id}"
    )

    try:
        if update.message.photo:
            msg = await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=update.message.photo[-1].file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{transaction_id}:{user.id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{transaction_id}:{user.id}")
                    ]
                ])
            )
        else:
            msg = await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=update.message.document.file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{transaction_id}:{user.id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{transaction_id}:{user.id}")
                    ]
                ])
            )
        
        await update.message.reply_text(
            "📨 Ваш чек отправлен на проверку администратору.\n"
            "⏳ Обычно проверка занимает не более 24 часов.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 В меню", callback_data="back_to_start")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error sending receipt: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при отправке чека. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 В меню", callback_data="back_to_start")]
            ])
        )

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может подтверждать платежи.", show_alert=True)
        return
        
    _, transaction_id, user_id = query.data.split(":")
    transaction_id = int(transaction_id)
    user_id = int(user_id)
    
    try:
        cursor.execute(
            '''SELECT amount, attempts FROM transactions WHERE id = ?''',
            (transaction_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            await query.answer("❌ Транзакция не найдена", show_alert=True)
            return
            
        amount, attempts = result
        
        update_transaction(
            transaction_id=transaction_id,
            status='completed',
            admin_id=query.from_user.id
        )
        
        update_user_attempts(user_id=user_id, paid=attempts)
        
        user_attempts = get_user_attempts(user_id)
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ <b>Ваш платеж подтвержден!</b>\n\n"
                 f"💎 Вам добавлено <b>{attempts}</b> попыток.\n"
                 f"🔄 Теперь у вас <b>{user_attempts['remaining']}</b> доступных попыток.\n"
                 f"🎯 Можете крутить колесо фортуны!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_play_keyboard(user_id)
        )
        
        await query.message.delete()
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ Платеж подтвержден\n\n"
                 f"👤 Пользователь: ID {user_id}\n"
                 f"💎 Добавлено попыток: {attempts}\n"
                 f"💰 Сумма: {amount} руб\n"
                 f"🔄 Всего доступно: {user_attempts['remaining']}\n"
                 f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        await query.answer("❌ Ошибка при подтверждении платежа", show_alert=True)

async def decline_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Только администратор может отклонять платежи.", show_alert=True)
        return
        
    _, transaction_id, user_id = query.data.split(":")
    transaction_id = int(transaction_id)
    user_id = int(user_id)
    
    try:
        update_transaction(
            transaction_id=transaction_id,
            status='declined',
            admin_id=query.from_user.id
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ <b>Ваш платеж был отклонен администратором</b>\n\n"
                 "Возможные причины:\n"
                 "• Неправильный чек\n"
                 "• Несоответствующая сумма\n"
                 "• Подозрительная активность\n\n"
                 "Если вы считаете это ошибкой, свяжитесь с поддержкой.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_start_keyboard()
        )
        
        await query.message.delete()
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❌ Платеж отклонен\n\n"
                 f"👤 Пользователь: ID {user_id}\n"
                 f"📝 ID транзакции: {transaction_id}\n"
                 f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error declining payment: {e}")
        await query.answer("❌ Ошибка при отклонении платежа", show_alert=True)

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.chat_data.pop("current_transaction", None)
    context.chat_data.pop("payment_choice", None)
    context.chat_data.pop("payment_amount", None)
    context.chat_data.pop("payment_attempts", None)
    
    await query.message.edit_text(
        "🎡 Добро пожаловать в <b>Колесо Фортуны</b>!\n\n"
        "💎 Крутите колесо и выигрывайте призы!\n"
        "💰 Попытки можно купить, получить за рефералов или ежедневный бонус.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard(query.from_user.id)
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "play":
        await spin_wheel(update, context)
    elif query.data == "buy_attempts":
        await buy_attempts(update, context)
    elif query.data.startswith("pay_"):
        await handle_payment_choice(update, context)
    elif query.data == "spin_wheel":
        await spin_wheel(update, context)
    elif query.data == "check_attempts":
        await check_attempts(update, context)
    elif query.data == "daily_bonus":
        await daily_bonus(update, context)
    elif query.data == "referral_info":
        await referral_info(update, context)
    elif query.data.startswith("confirm:"):
        await confirm_payment(update, context)
    elif query.data.startswith("decline:"):
        await decline_payment(update, context)
    elif query.data == "back_to_start":
        await back_to_start(update, context)
    elif query.data == "admin_panel":
        await admin_panel(update, context)
    elif query.data == "manage_payment_methods":
        await manage_payment_methods(update, context)
    elif query.data == "admin_stats":
        await admin_stats(update, context)
    elif query.data == "add_payment_method":
        await add_payment_method_handler(update, context)
    elif query.data.startswith("edit_method_"):
        await edit_payment_method_handler(update, context)
    elif query.data.startswith("admin_method_"):
        await toggle_payment_method_handler(update, context)
    elif query.data.startswith("delete_method_"):
        await delete_payment_method_handler(update, context)
    elif query.data.startswith("method_"):
        await show_payment_method(update, context)
    elif query.data == "back_to_payment_methods":
        await back_to_payment_methods(update, context)
    elif query.data == "admin_back":
        await admin_panel(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    
    if update and update.effective_user:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="❌ Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_start_keyboard(update.effective_user.id)
        )

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    
    # Обработчики callback-кнопок
    application.add_handler(CallbackQueryHandler(button))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_receipt))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_payment_method_text))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
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