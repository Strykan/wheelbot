import os
import asyncpg
from dotenv import load_dotenv
import logging
from datetime import datetime
import random
from typing import Optional, Dict, List

load_dotenv()
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Установка соединения с PostgreSQL"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                database_url = os.getenv('DATABASE_URL')
                if not database_url:
                    raise ValueError("DATABASE_URL not set in .env")
                
                if 'railway' in database_url:
                    database_url = database_url.replace('postgresql://', 'postgres://')
                
                ssl_setting = 'require' if 'railway' in database_url else None
                
                self.pool = await asyncpg.create_pool(
                    dsn=database_url,
                    min_size=1,
                    max_size=10,
                    timeout=30,
                    ssl=ssl_setting
                )
                await self.create_tables()
                logger.info("Database connection established")
                return True
            except Exception as e:
                logger.error(f"Database connection error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def create_tables(self):
        """Создание таблиц в PostgreSQL"""
        async with self.pool.acquire() as conn:
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

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS payment_methods (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    details TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')

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
    async def get_user_attempts(self, user_id: int) -> Dict:
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

    async def update_user_attempts(self, user_id: int, paid: int = 0, used: int = 0, last_bonus_date: Optional[str] = None) -> bool:
        """Обновление попыток пользователя"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute('''
                    INSERT INTO user_attempts (user_id) 
                    VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING
                ''', user_id)
                
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
                return True

    async def generate_referral_code(self, user_id: int) -> str:
        """Генерация реферального кода"""
        code = f"REF{user_id}{random.randint(1000, 9999)}"
        async with self.pool.acquire() as conn:
            await conn.execute(
                'UPDATE user_attempts SET referral_code = $1 WHERE user_id = $2',
                code, user_id
            )
        return code

    async def get_referral_info(self, user_id: int) -> Optional[Dict]:
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

    async def process_referral(self, user_id: int, referral_code: str) -> bool:
        """Обработка реферала"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                referrer = await conn.fetchrow(
                    'SELECT user_id FROM user_attempts WHERE referral_code = $1',
                    referral_code
                )
                if not referrer:
                    return False
                
                referrer_id = referrer['user_id']
                
                await conn.execute(
                    'UPDATE user_attempts SET referred_by = $1 WHERE user_id = $2',
                    referrer_id, user_id
                )
                
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
    async def get_payment_methods(self) -> List:
        """Получение активных способов оплаты"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                'SELECT id, name, details FROM payment_methods WHERE is_active = TRUE'
            )

    async def add_payment_method(self, name: str, details: str) -> bool:
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

    # Transactions
    async def create_transaction(self, user_id: int, amount: int, attempts: int, status: str = 'pending') -> int:
        """Создание транзакции"""
        if amount <= 0 or amount > 10000:  # Максимальная сумма 10,000 руб
            raise ValueError("Invalid amount")
        if attempts <= 0:
            raise ValueError("Invalid attempts count")
            
        async with self.pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO transactions 
                (user_id, amount, attempts, status, created_at) 
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            ''', user_id, amount, attempts, status, datetime.now().isoformat())

    # Prizes
    async def add_prize(self, user_id: int, prize_type: str, value: str) -> None:
        """Добавление приза"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO prizes 
                (user_id, prize_type, value, created_at) 
                VALUES ($1, $2, $3, $4)
            ''', user_id, prize_type, value, datetime.now().isoformat())

    async def get_unclaimed_prizes(self, user_id: int) -> List:
        """Получение неполученных призов"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                '''SELECT id, prize_type, value FROM prizes 
                   WHERE user_id = $1 AND is_claimed = FALSE''',
                user_id
            )