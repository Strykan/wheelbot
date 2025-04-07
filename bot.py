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
                   name TEXT NOT NULL UNIQUE,
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
        # Проверка на существующий способ оплаты
        cursor.execute('SELECT id FROM payment_methods WHERE name = ?', (name,))
        if cursor.fetchone():
            logger.warning(f"Способ оплаты '{name}' уже существует")
            return False
            
        cursor.execute(
            'INSERT INTO payment_methods (name, details) VALUES (?, ?)',
            (name, details)
        )
        conn.commit()
        logger.info(f"Добавлен новый способ оплаты: {name}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        conn.rollback()
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
        logger.error(f"Database error: {e}")
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
        logger.error(f"Database error: {e}")
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
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
        ])
    )

async def edit_payment_method_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может использовать эту функцию.", show_alert=True)
        return
    
    method_id = int(query.data.split('_')[-1])
    context.user_data['editing_payment_method'] = method_id
    method = get_payment_method(method_id)
    
    if method:
        await query.message.edit_text(
            f"Текущие данные:\n\nНазвание: {method[0]}\nРеквизиты: {method[1]}\n\n"
            "Введите новые данные в формате:\n\n"
            "<code>Новое название\nНовые реквизиты</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Отмена", callback_data="manage_payment_methods")]
            ])
        )
    else:
        await query.answer("Способ оплаты не найден", show_alert=True)

async def handle_payment_method_text(update: Update, context: CallbackContext):
    if 'adding_payment_method' in context.user_data:
        # Этап 1: Получение названия способа оплаты
        name = update.message.text.strip()
        if not name:
            await update.message.reply_text("Название не может быть пустым. Попробуйте снова.")
            return
            
        if len(name) > 50:
            await update.message.reply_text("Название слишком длинное (макс. 50 символов).")
            return
            
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
        # Этап 2: Получение реквизитов
        details = update.message.text.strip()
        if not details:
            await update.message.reply_text("Реквизиты не могут быть пустыми. Попробуйте снова.")
            return
            
        name = context.user_data.get('new_payment_name')
        if not name:
            await update.message.reply_text("Ошибка: не найдено название способа оплаты")
            return
            
        if add_payment_method(name, details):
            await update.message.reply_text(
                f"✅ Способ оплаты <b>{name}</b> успешно добавлен!",
                parse_mode=ParseMode.HTML
            )
            # Очищаем временные данные
            context.user_data.pop('new_payment_name', None)
            context.user_data.pop('adding_payment_details', None)
            
            # Возвращаем администратора к списку способов оплаты
            await manage_payment_methods(update, context)
        else:
            await update.message.reply_text(
                "❌ Не удалось добавить способ оплаты. Возможно, такое название уже существует."
            )
    
    elif 'editing_payment_method' in context.user_data:
        # Редактирование существующего способа
        method_id = context.user_data['editing_payment_method']
        try:
            text = update.message.text.strip()
            if not text:
                await update.message.reply_text("Данные не могут быть пустыми.")
                return
                
            parts = text.split('\n', 1)
            if len(parts) != 2:
                await update.message.reply_text("Неверный формат. Введите название и реквизиты на отдельных строках.")
                return
                
            name, details = parts
            name = name.strip()
            details = details.strip()
            
            if not name or not details:
                await update.message.reply_text("Название и реквизиты не могут быть пустыми.")
                return
                
            if update_payment_method(method_id, name, details):
                await update.message.reply_text(
                    "✅ Способ оплаты успешно обновлен!",
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_text(
                    "❌ Не удалось обновить способ оплаты."
                )
        except Exception as e:
            logger.error(f"Ошибка при редактировании способа оплаты: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обновлении способа оплаты."
            )
        finally:
            # Очищаем временные данные
            context.user_data.pop('editing_payment_method', None)
            # Возвращаем к списку способов оплаты
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
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Выбрать другой способ", callback_data="back_to_payment_methods")]
        ])
    )

async def back_to_payment_methods(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "💳 Выберите способ оплаты:",
        reply_markup=get_payment_methods_keyboard()
    )

async def spin_wheel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if not result or result[0] <= result[1]:
        await query.answer("У вас нет доступных попыток!", show_alert=True)
        return
    
    # Увеличиваем счетчик использованных попыток
    new_used = result[1] + 1
    save_user_attempts(user_id, result[0], new_used)
    
    # Символы для колеса и их веса
    wheel_segments = ["🍒", "🍋", "🍊", "🍇", "🍉", "💰", "🎁", "⭐", "🍀"]
    segment_weights = [15, 15, 15, 15, 10, 5, 5, 10, 10]
    
    # Выбираем случайный сегмент для остановки
    selected_index = random.choices(range(len(wheel_segments)), weights=segment_weights, k=1)[0]
    selected_segment = wheel_segments[selected_index]
    
    # Привязка сегментов к призам
    prize_mapping = {
        "🍒": "10 рублей",
        "🍋": "20 рублей",
        "🍊": "Бесплатная попытка",
        "🍇": "5 рублей",
        "🍉": "Конфетка",
        "💰": "100 рублей",
        "🎁": "Подарок",
        "⭐": "5 бесплатных попыток",
        "🍀": "Скидка 10% на след. игру"
    }
    prize = prize_mapping.get(selected_segment, "Ничего")
    
    # Создаем сообщение с анимацией
    message = await query.message.reply_text(
        "🎡 <b>Колесо Фортуны</b>\n\n"
        f"{' ' * 8}👆\n"
        f"{' '.join(wheel_segments)}\n\n"
        "🌀 Крутим колесо...",
        parse_mode=ParseMode.HTML
    )
    
    # Параметры анимации
    spin_duration = 3
    frames = 15
    slowdown_start = 10
    
    # Анимация вращения
    for frame in range(frames):
        # Вращаем колесо
        wheel_segments.insert(0, wheel_segments.pop())
        
        # Рассчитываем задержку
        if frame < slowdown_start:
            delay = 0.15
        else:
            delay = 0.15 + (frame - slowdown_start) * 0.1
        
        # Обновляем сообщение
        await message.edit_text(
            "🎡 <b>Колесо Фортуны</b>\n\n"
            f"{' ' * 8}👆\n"
            f"{' '.join(wheel_segments)}\n\n"
            f"{'🌀' * (frame % 3 + 1)} Крутим колесо...",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(delay)
    
    # Останавливаем колесо
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
    
    # Обработка призов
    bonus_text = ""
    if prize == "Бесплатная попытка":
        cursor.execute('UPDATE user_attempts SET paid = paid + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        bonus_text = "\n\n🎁 Вам добавлена 1 бесплатная попытка!"
    elif prize == "5 бесплатных попыток":
        cursor.execute('UPDATE user_attempts SET paid = paid + 5 WHERE user_id = ?', (user_id,))
        conn.commit()
        bonus_text = "\n\n🎁 Вам добавлено 5 бесплатных попыток!"
    
    # Получаем обновленное количество попыток
    cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
    updated_attempts = cursor.fetchone()
    remaining = updated_attempts[0] - updated_attempts[1]
    
    # Финальное сообщение
    await message.edit_text(
        f"🎉 <b>Поздравляем!</b>\n\n"
        f"🏆 Вы выиграли: <b>{prize}</b>{bonus_text}\n\n"
        f"🔄 Осталось попыток: <b>{remaining}</b>\n\n"
        "Хотите крутить еще?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_play_keyboard(user_id)
    )
    
    # Удаляем исходное сообщение с кнопкой
    try:
        await query.message.delete()
    except:
        pass

async def handle_receipt(update: Update, context: CallbackContext):
    user = update.effective_user
    payment_choice = context.chat_data.get("payment_choice")
    
    if not payment_choice:
        await update.message.reply_text("Сначала выберите количество попыток через меню.")
        return
        
    if not (update.message.photo or update.message.document):
        await update.message.reply_text("Пожалуйста, отправьте чек о платеже (фото или документ).")
        return
    
    amount = {"1": 50, "3": 130, "5": 200, "10": 350}.get(payment_choice, 0)
    caption = (
        f"📤 Новый чек от @{user.username}\n"
        f"🆔 ID: {user.id}\n"
        f"💎 Попыток: {payment_choice}\n"
        f"💰 Сумма: {amount} руб"
    )

    try:
        if update.message.photo:
            msg = await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=update.message.photo[-1].file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{user.id}:{user.username}:{payment_choice}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{user.id}:{user.username}")
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
                        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{user.id}:{user.username}:{payment_choice}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{user.id}:{user.username}")
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
        
        # Сохраняем ID сообщения для администратора
        context.chat_data["admin_message_id"] = msg.message_id
        
    except Exception as e:
        logger.error(f"Error sending receipt: {e}")
        await update.message.reply_text("❌ Произошла ошибка при отправке чека. Попробуйте позже.")

async def confirm_payment(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может подтверждать платежи.", show_alert=True)
        return
        
    _, user_id, username, payment_choice = query.data.split(":")
    user_id = int(user_id)
    new_attempts = {"1": 1, "3": 3, "5": 5, "10": 10}.get(payment_choice, 0)
    
    try:
        # Получаем текущее количество попыток
        cursor.execute('SELECT paid, used FROM user_attempts WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            current_paid, current_used = result
            # Суммируем новые попытки с существующими
            total_paid = current_paid + new_attempts
            # Сохраняем общее количество оплаченных попыток
            save_user_attempts(user_id, total_paid, current_used)
            remaining_attempts = total_paid - current_used
        else:
            # Если запись не существует, создаем новую
            save_user_attempts(user_id, new_attempts, 0)
            remaining_attempts = new_attempts
        
        # Уведомляем пользователя
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ <b>Ваш платеж подтвержден!</b>\n\n"
                 f"💎 Вам добавлено <b>{new_attempts}</b> попыток.\n"
                 f"🔄 Теперь у вас <b>{remaining_attempts}</b> доступных попыток.\n"
                 f"🎯 Можете крутить колесо фортуны!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_play_keyboard(user_id)
        )
        
        # Удаляем оригинальное сообщение с чеком
        await query.message.delete()
        
        # Отправляем подтверждение администратору
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ Платеж подтвержден\n\n"
                 f"👤 Пользователь: @{username} (ID: {user_id})\n"
                 f"💎 Добавлено попыток: {new_attempts}\n"
                 f"🔄 Всего доступно: {remaining_attempts}\n"
                 f"🕒 Время: {query.message.date.strftime('%Y-%m-%d %H:%M')}",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        await query.answer("Ошибка при подтверждении платежа", show_alert=True)

async def decline_payment(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только администратор может отклонять платежи.", show_alert=True)
        return
        
    _, user_id, username = query.data.split(":")
    user_id = int(user_id)
    
    try:
        # Уведомляем пользователя
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
        
        # Удаляем оригинальное сообщение с чеком
        await query.message.delete()
        
        # Отправляем уведомление администратору
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❌ Платеж отклонен\n\n"
                 f"👤 Пользователь: @{username} (ID: {user_id})\n"
                 f"🕒 Время: {query.message.date.strftime('%Y-%m-%d %H:%M')}",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error declining payment: {e}")
        await query.answer("Ошибка при отклонении платежа", show_alert=True)

async def back_to_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "🎡 Добро пожаловать в <b>Колесо Фортуны</b>!\n\n"
        "💎 Крутите колесо и выигрывайте призы!\n"
        "💰 Попытки можно купить или выиграть в игре.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard()
    )

async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == "play":
        await play(update, context)
    elif query.data.startswith("pay_"):
        await handle_payment_choice(update, context)
    elif query.data == "spin_wheel":
        await spin_wheel(update, context)
    elif query.data == "check_attempts":
        await check_attempts(update, context)
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

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    
    # Обработчики callback-кнопок
    application.add_handler(CallbackQueryHandler(button))
    
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