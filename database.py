import os
import asyncpg
from dotenv import load_dotenv
import logging
from datetime import datetime

load_dotenv()
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Установка соединения с PostgreSQL"""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=os.getenv('DATABASE_URL'),
                min_size=1,
                max_size=10,
                timeout=30
            )
            await self.create_tables()
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise

    async def create_tables(self):
        """Создание таблиц в PostgreSQL"""
        async with self.pool.acquire() as conn:
            # Таблица пользовательских попыток
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_attempts (
                    user_id BIGINT PRIMARY KEY, 
                    paid INTEGER DEFAULT 0, 
                    used INTEGER DEFAULT 0,
                    last_bonus_date TEXT,
                    referral_code TEXT UNIQUE,
                    referred_by BIGINT DEFAULT NULL,
                    referrals_count INTEGER DEFAULT 0
                )
            ''')

            # Таблица способов оплаты
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS payment_methods (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    details TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')

            # Таблица транзакций
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    receipt_id TEXT,
                    admin_id BIGINT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            ''')

            # Таблица призов
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS prizes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    prize_type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    is_claimed BOOLEAN DEFAULT FALSE,
                    created_at TEXT NOT NULL
                )
            ''')

    # User Attempts Methods
    async def get_user_attempts(self, user_id):
        """Получение попыток пользователя"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT paid, used, last_bonus_date FROM user_attempts WHERE user_id = $1',
                user_id
            )
            if row:
                return {
                    'paid': row['paid'],
                    'used': row['used'],
                    'remaining': row['paid'] - row['used'],
                    'last_bonus_date': row['last_bonus_date']
                }
            return {'paid': 0, 'used': 0, 'remaining': 0, 'last_bonus_date': None}

    async def update_user_attempts(self, user_id, paid=0, used=0, last_bonus_date=None):
        """Обновление попыток пользователя"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Вставка или игнорирование существующей записи
                await conn.execute('''
                    INSERT INTO user_attempts (user_id) 
                    VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING
                ''', user_id)
                
                # Динамическое построение запроса
                updates = []
                params = []
                param_count = 1
                
                if paid != 0:
                    updates.append(f"paid = paid + ${param_count}")
                    params.append(paid)
                    param_count += 1
                
                if used != 0:
                    updates.append(f"used = used + ${param_count}")
                    params.append(used)
                    param_count += 1
                
                if last_bonus_date:
                    updates.append(f"last_bonus_date = ${param_count}")
                    params.append(last_bonus_date)
                    param_count += 1
                
                if updates:
                    query = f'''
                        UPDATE user_attempts 
                        SET {', '.join(updates)}
                        WHERE user_id = ${param_count}
                    '''
                    params.append(user_id)
                    await conn.execute(query, *params)

    async def generate_referral_code(self, user_id):
        """Генерация реферального кода"""
        code = f"REF{user_id}{random.randint(1000, 9999)}"
        async with self.pool.acquire() as conn:
            await conn.execute(
                'UPDATE user_attempts SET referral_code = $1 WHERE user_id = $2',
                code, user_id
            )
        return code

    async def get_referral_info(self, user_id):
        """Получение реферальной информации"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                '''SELECT referral_code, referred_by, referrals_count 
                   FROM user_attempts WHERE user_id = $1''',
                user_id
            )
            if row:
                return {
                    'code': row['referral_code'],
                    'referred_by': row['referred_by'],
                    'count': row['referrals_count']
                }
            return None

    async def process_referral(self, user_id, referral_code):
        """Обработка реферала"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Проверка существования реферального кода
                referrer = await conn.fetchrow(
                    'SELECT user_id FROM user_attempts WHERE referral_code = $1',
                    referral_code
                )
                if not referrer:
                    return False
                
                referrer_id = referrer['user_id']
                
                # Обновление данных у реферала
                await conn.execute(
                    'UPDATE user_attempts SET referred_by = $1 WHERE user_id = $2',
                    referrer_id, user_id
                )
                
                # Начисление бонусов
                await conn.execute('''
                    UPDATE user_attempts 
                    SET referrals_count = referrals_count + 1,
                        paid = paid + 1 
                    WHERE user_id = $1
                ''', referrer_id)
                
                await conn.execute(
                    'UPDATE user_attempts SET paid = paid + 1 WHERE user_id = $1',
                    user_id
                )
                
                return True

    # Payment Methods
    async def get_payment_methods(self):
        """Получение активных способов оплаты"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                'SELECT id, name, details FROM payment_methods WHERE is_active = TRUE'
            )

    async def add_payment_method(self, name, details):
        """Добавление способа оплаты"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    'INSERT INTO payment_methods (name, details) VALUES ($1, $2)',
                    name, details
                )
                return True
            except asyncpg.UniqueViolationError:
                return False

    async def update_payment_method(self, method_id, name, details):
        """Обновление способа оплаты"""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE payment_methods SET name = $1, details = $2 WHERE id = $3',
                name, details, method_id
            )
            return "UPDATE" in result

    async def toggle_payment_method(self, method_id):
        """Переключение статуса способа оплаты"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                'UPDATE payment_methods SET is_active = NOT is_active WHERE id = $1',
                method_id
            )

    async def delete_payment_method(self, method_id):
        """Удаление способа оплаты"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM payment_methods WHERE id = $1',
                method_id
            )

    # Transactions
    async def create_transaction(self, user_id, amount, attempts, status='pending'):
        """Создание транзакции"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO transactions 
                (user_id, amount, attempts, status, created_at) 
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            ''', user_id, amount, attempts, status, datetime.now().isoformat())

    async def update_transaction(self, transaction_id, status, admin_id=None, receipt_id=None):
        """Обновление транзакции"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE transactions SET 
                status = $1,
                admin_id = $2,
                receipt_id = $3,
                updated_at = $4
                WHERE id = $5
            ''', status, admin_id, receipt_id, datetime.now().isoformat(), transaction_id)

    # Prizes
    async def add_prize(self, user_id, prize_type, value):
        """Добавление приза"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO prizes 
                (user_id, prize_type, value, created_at) 
                VALUES ($1, $2, $3, $4)
            ''', user_id, prize_type, value, datetime.now().isoformat())

    async def get_unclaimed_prizes(self, user_id):
        """Получение неполученных призов"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                '''SELECT id, prize_type, value FROM prizes 
                   WHERE user_id = $1 AND is_claimed = FALSE''',
                user_id
            )

    async def claim_prize(self, prize_id):
        """Отметка приза как полученного"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                'UPDATE prizes SET is_claimed = TRUE WHERE id = $1',
                prize_id
            )