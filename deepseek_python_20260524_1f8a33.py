# ultimate_bot_safe.py - МАКСИМАЛЬНО ЧИСТЫЙ МЕТОД
import asyncio
import sqlite3
import time
import os
import traceback
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from telethon import TelegramClient
from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.errors import FloodWaitError, UsernameNotOccupiedError
from telethon.sessions import StringSession
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
import threading

BOT_TOKEN = "8456845056:AAFj2uy9sDeM4fboiMMJ_4ac3nS3EAM3Q6w"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db_lock = threading.Lock()

def init_databases():
    conn = sqlite3.connect("bot_users.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        api_id INTEGER,
        api_hash TEXT,
        session_string TEXT,
        phone TEXT,
        is_active INTEGER DEFAULT 1,
        added_date INTEGER
    )""")
    conn.commit()
    conn.close()
    
    conn = sqlite3.connect("million_chats.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS mega_chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER UNIQUE,
        username TEXT,
        title TEXT,
        members_count INTEGER,
        type TEXT,
        source TEXT
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS users_network (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        is_bot INTEGER,
        processed INTEGER DEFAULT 0
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS user_group_links (
        user_id INTEGER,
        chat_id INTEGER,
        PRIMARY KEY (user_id, chat_id)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS group_queue (
        chat_id INTEGER PRIMARY KEY,
        members_count INTEGER,
        scraped_members INTEGER DEFAULT 0,
        priority INTEGER DEFAULT 1
    )""")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_id ON mega_chats(chat_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_members ON mega_chats(members_count)")
    conn.commit()
    conn.close()

init_databases()

class States(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_session = State()
    waiting_message = State()

def create_client(api_id, api_hash, session_string=""):
    return TelegramClient(
        StringSession(session_string),
        api_id,
        api_hash,
        connection=ConnectionTcpAbridged,
        use_ipv6=False,
        system_version="4.16.30-vxCUSTOM",
        device_model="Pixel 8 Pro",
        app_version="10.15.0"
    )

class DistributedMiner:
    def __init__(self, account_id, api_id, api_hash, session_string):
        self.account_id = account_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.total_found = 0
        
    async def run_mining(self):
        client = create_client(self.api_id, self.api_hash, self.session_string)
        
        try:
            await client.start()
            print(f"[Miner {self.account_id}] ЗАПУЩЕН")
        except Exception as e:
            print(f"[Miner {self.account_id}] Ошибка запуска: {e}")
            with db_lock:
                conn = sqlite3.connect("bot_users.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (self.account_id,))
                conn.commit()
                conn.close()
            return 0
        
        # Сбор диалогов
        try:
            dialogs = await client.get_dialogs(limit=500)
            for dialog in dialogs:
                if dialog.is_group or dialog.is_channel:
                    chat = dialog.entity
                    with db_lock:
                        conn = sqlite3.connect("million_chats.db")
                        cursor = conn.cursor()
                        cursor.execute("""
                        INSERT OR IGNORE INTO mega_chats (chat_id, username, title, members_count, type, source)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            chat.id,
                            getattr(chat, 'username', ''),
                            dialog.name,
                            getattr(chat, 'participants_count', 0),
                            'channel' if dialog.is_channel else 'group',
                            f'dialogs_{self.account_id}'
                        ))
                        cursor.execute("""
                        INSERT OR IGNORE INTO group_queue (chat_id, members_count, priority)
                        VALUES (?, ?, ?)
                        """, (chat.id, getattr(chat, 'participants_count', 0), 3))
                        conn.commit()
                        conn.close()
                        self.total_found += 1
        except Exception as e:
            print(f"[Miner {self.account_id}] Ошибка диалогов: {e}")
        
        # Глобальный поиск
        search_queries = [
            "чат", "группа", "telegram", "общение", "новости",
            "бизнес", "заработок", "инвестиции", "криптовалюта",
            "chat", "group", "news", "community", "business"
        ]
        
        for query in search_queries:
            try:
                result = await client(SearchGlobalRequest(
                    q=query, filter=None, min_date=None, max_date=None,
                    offset_rate=0, offset_peer=types.InputPeerEmpty(),
                    offset_id=0, limit=200
                ))
                for chat in result.chats:
                    with db_lock:
                        conn = sqlite3.connect("million_chats.db")
                        cursor = conn.cursor()
                        cursor.execute("""
                        INSERT OR IGNORE INTO mega_chats (chat_id, username, title, members_count, type, source)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            chat.id,
                            getattr(chat, 'username', ''),
                            getattr(chat, 'title', ''),
                            getattr(chat, 'participants_count', 0),
                            'channel',
                            f'search_{self.account_id}'
                        ))
                        conn.commit()
                        conn.close()
                        self.total_found += 1
                await asyncio.sleep(0.5)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except:
                continue
        
        # Брутфорс юзернеймов
        base_words = ["chat", "group", "news", "bot", "free", "pro", "top", "club"]
        for word in base_words:
            for i in range(self.account_id * 100, (self.account_id + 1) * 100):
                username = f"{word}{i}"
                try:
                    result = await client(ResolveUsernameRequest(username))
                    for chat in result.chats:
                        with db_lock:
                            conn = sqlite3.connect("million_chats.db")
                            cursor = conn.cursor()
                            cursor.execute("""
                            INSERT OR IGNORE INTO mega_chats (chat_id, username, title, members_count, type, source)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """, (
                                chat.id,
                                getattr(chat, 'username', ''),
                                getattr(chat, 'title', ''),
                                getattr(chat, 'participants_count', 0),
                                'channel',
                                f'username_{self.account_id}'
                            ))
                            conn.commit()
                            conn.close()
                            self.total_found += 1
                    await asyncio.sleep(0.05)
                except UsernameNotOccupiedError:
                    continue
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except:
                    continue
        
        # Выкачка участников из групп
        with db_lock:
            conn = sqlite3.connect("million_chats.db")
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM group_queue WHERE scraped_members = 0 ORDER BY priority DESC LIMIT 50")
            groups = cursor.fetchall()
            conn.close()
        
        for (chat_id,) in groups:
            try:
                participants = await client.get_participants(chat_id, limit=5000)
                with db_lock:
                    conn = sqlite3.connect("million_chats.db")
                    cursor = conn.cursor()
                    for user in participants:
                        if not user.bot:
                            cursor.execute("""
                            INSERT OR REPLACE INTO users_network (user_id, username, first_name, last_name, is_bot)
                            VALUES (?, ?, ?, ?, ?)
                            """, (
                                user.id,
                                getattr(user, 'username', ''),
                                getattr(user, 'first_name', ''),
                                getattr(user, 'last_name', ''),
                                0
                            ))
                            cursor.execute("INSERT OR IGNORE INTO user_group_links VALUES (?, ?)", (user.id, chat_id))
                    cursor.execute("UPDATE group_queue SET scraped_members = ? WHERE chat_id = ?", (len(participants), chat_id))
                    conn.commit()
                    conn.close()
                await asyncio.sleep(1)
            except:
                continue
        
        print(f"[Miner {self.account_id}] ЗАВЕРШЁН: +{self.total_found}")
        await client.disconnect()
        return self.total_found

class MiningCoordinator:
    def __init__(self):
        self.active_miners = {}
        
    async def start_mining(self, user_id, api_id, api_hash, session_string):
        miner = DistributedMiner(user_id, api_id, api_hash, session_string)
        self.active_miners[user_id] = miner
        task = asyncio.create_task(miner.run_mining())
        return task
    
    async def get_stats(self):
        with db_lock:
            conn = sqlite3.connect("million_chats.db")
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM mega_chats")
            chats = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users_network")
            users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM user_group_links")
            links = cursor.fetchone()[0]
            conn.close()
        return chats, users, links
    
    async def get_chats(self):
        with db_lock:
            conn = sqlite3.connect("million_chats.db")
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM mega_chats ORDER BY members_count DESC")
            chats = [row[0] for row in cursor.fetchall()]
            conn.close()
        return chats

coordinator = MiningCoordinator()

# Генератор скрипта для получения сессии
def generate_session_script(api_id, api_hash):
    return f"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged

api_id = {api_id}
api_hash = "{api_hash}"

async def main():
    client = TelegramClient(
        StringSession(),
        api_id,
        api_hash,
        connection=ConnectionTcpAbridged,
        use_ipv6=False,
        system_version="4.16.30-vxCUSTOM",
        device_model="Pixel 8 Pro",
        app_version="10.15.0"
    )
    
    await client.start()
    session_string = StringSession.save(client.session)
    print("\\n" + "="*50)
    print("ТВОЯ СЕССИЯ:")
    print(session_string)
    print("="*50)
    print("\\nОтправь эту строку боту командой /session СТРОКА")
    await client.disconnect()

asyncio.run(main())
"""

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "[] RAGE mode\n\n"
        "Отправь api_id и api_hash с my.telegram.org в формате:\n"
        "/add_api ID HASH\n\n"
        "Пример:\n"
        "/add_api 123456 a1b2c3d4e5f6"
    )

@dp.message(Command("add_api"))
async def add_api(message: types.Message, state: FSMContext):
    parts = message.text.split()
    
    if len(parts) != 3:
        await message.answer("Неверный формат. Используй: /add_api ID HASH")
        return
    
    try:
        api_id = int(parts[1])
        api_hash = parts[2]
    except:
        await message.answer("api_id должен быть числом")
        return
    
    await state.update_data(api_id=api_id, api_hash=api_hash)
    
    # Генерируем скрипт для пользователя
    script = generate_session_script(api_id, api_hash)
    
    # Сохраняем скрипт
    filename = f"get_session_{message.from_user.id}.py"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(script)
    
    await message.answer(
        "Теперь тебе нужно получить сессию:\n\n"
        "1. Установи Python и Telethon:\n"
        "`pip install telethon`\n\n"
        "2. Запусти скрипт который я отправил ниже\n\n"
        "3. Введи номер телефона и код из Telegram\n\n"
        "4. Скопируй строку сессии\n\n"
        "5. Отправь её боту командой:\n"
        "/session СТРОКА_СЕССИИ"
    )
    
    # Отправляем скрипт
    await message.answer_document(
        types.FSInputFile(filename),
        caption="Запусти этот скрипт у себя на компьютере"
    )
    
    os.remove(filename)

@dp.message(Command("session"))
async def add_session(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    
    if len(parts) != 2:
        await message.answer("Неверный формат. Используй: /session СТРОКА_СЕССИИ")
        return
    
    session_string = parts[1]
    
    data = await state.get_data()
    api_id = data.get("api_id")
    api_hash = data.get("api_hash")
    
    if not api_id or not api_hash:
        await message.answer("Сначала отправь api_id и api_hash через /add_api")
        return
    
    # Проверяем сессию
    client = create_client(api_id, api_hash, session_string)
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await message.answer("Сессия невалидна. Получи новую.")
            await client.disconnect()
            return
        
        me = await client.get_me()
        phone = getattr(me, 'phone', 'Неизвестно')
        
        # Сохраняем в базу
        with db_lock:
            conn = sqlite3.connect("bot_users.db")
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, api_id, api_hash, session_string, phone, is_active, added_date)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (message.from_user.id, api_id, api_hash, session_string, phone, int(time.time())))
            conn.commit()
            conn.close()
        
        await client.disconnect()
        
        # Запускаем майнинг
        await coordinator.start_mining(message.from_user.id, api_id, api_hash, session_string)
        
        await message.answer(
            f"[] АККАУНТ ДОБАВЛЕН\n"
            f"Телефон: {phone}\n"
            f"Майнинг запущен!\n\n"
            f"/stats - статистика\n"
            f"/broadcast - рассылка"
        )
        
    except Exception as e:
        await message.answer(f"Ошибка проверки сессии: {e}")
        await client.disconnect()

@dp.message(Command("stats"))
async def stats(message: types.Message):
    chats, users, links = await coordinator.get_stats()
    
    await message.answer(
        f"[] СТАТИСТИКА БАЗЫ:\n\n"
        f"Чатов: {chats}\n"
        f"Пользователей: {users}\n"
        f"Связей: {links}"
    )

@dp.message(Command("broadcast"))
async def broadcast_start(message: types.Message, state: FSMContext):
    chats, _, _ = await coordinator.get_stats()
    
    await message.answer(
        f"В базе {chats} чатов.\n"
        "Введи сообщение для рассылки:"
    )
    await state.set_state(States.waiting_message)

@dp.message(States.waiting_message)
async def broadcast_send(message: types.Message, state: FSMContext):
    text = message.text
    chats = await coordinator.get_chats()
    
    if not chats:
        await message.answer("База пуста.")
        await state.clear()
        return
    
    with db_lock:
        conn = sqlite3.connect("bot_users.db")
        cursor = conn.cursor()
        cursor.execute("SELECT api_id, api_hash, session_string FROM users WHERE is_active = 1")
        accounts = cursor.fetchall()
        conn.close()
    
    if not accounts:
        await message.answer("Нет активных аккаунтов")
        await state.clear()
        return
    
    chunks = [[] for _ in accounts]
    for i, chat_id in enumerate(chats):
        chunks[i % len(accounts)].append(chat_id)
    
    async def send_from_account(account, chat_list, msg_text):
        api_id, api_hash, session = account
        client = create_client(api_id, api_hash, session)
        
        try:
            await client.start()
            sent = 0
            for chat_id in chat_list:
                try:
                    await client.send_message(chat_id, msg_text)
                    sent += 1
                    await asyncio.sleep(1.5)
                except:
                    continue
            await client.disconnect()
            return sent
        except:
            return 0
    
    tasks = []
    for account, chunk in zip(accounts, chunks):
        if chunk:
            tasks.append(send_from_account(account, chunk, text))
    
    results = await asyncio.gather(*tasks)
    total_sent = sum(results)
    
    await message.answer(f"[] Отправлено: {total_sent}")
    await state.clear()

async def main():
    # Автозапуск сохранённых аккаунтов
    with db_lock:
        conn = sqlite3.connect("bot_users.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, api_id, api_hash, session_string FROM users WHERE is_active = 1")
        accounts = cursor.fetchall()
        conn.close()
    
    for user_id, api_id, api_hash, session in accounts:
        try:
            await coordinator.start_mining(user_id, api_id, api_hash, session)
            print(f"Автозапуск майнера {user_id}")
        except:
            continue
    
    print("[] БОТ ЗАПУЩЕН")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
