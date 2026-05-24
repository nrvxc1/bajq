import asyncio
import logging
import sys
import time
import random
import re
from datetime import datetime
from telethon import TelegramClient, functions
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import FloodWaitError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_ID = 38886400
API_HASH = "b7c5f1e52fab9f58250c583d5e5a4777"
PHONE = "+79191403988"
SOURCE_BOT = "@sdguhsdg_bot"
TARGET_USER = "@crmxcz"

MESSAGES = [
    "**__BHUMANUE ❗️ CEГODH9 BEPUФUKAЦИЯ HA ЛЮБУЮ ПЛOTФOPMY BCEГO 3A 200PYБ, ПOДPOБHOCTU TYT @crmxcz__**",
    "**__AKЦИ9 ! ПPOBEДEHUE BEPUФUKAЦИU HA БU3HEC AKKAYHTAX BCEГO 200PYБ, ДETAЛU @crmxcz__**",
    "**__TOЛЬKO CЕГODH9 PACПPODAЖA HA УСЛУГU ВEPUФUKAЦИU, ПO 200PYБ, ПOДPOБHOCTU B ЛС @crmxcz__**",
    "**__УСПEU CEГODH9 ЗAKAЗATЬ ВEPUФUKAЦИЮ BCEГO 3A 200PYБ, TOPOПUCЬ ПOKA ECTЬ MECTA @crmxcz__**",
    "**__ЧACOB 5 HAZAD ЗAKOHЧUЛC9 БOЛЬШOU ПPOEKТ, CПEШU 3A BEPUФUKAЦИEU ПO 200PYБ @crmxcz__**",
    "**__ХBAТUТ БЛOKUPOBOK, BEPUФUKAЦИЮ PAЗ U HABCЕГDA, CETbH9 BCEГO 200PYБ @crmxcz__**",
    "**__3AЧEM ПЛATUTЬ БOЛЬШE, ECЛU MOHO CEГODH9 ПPOЙТU BEPUФUKAЦИЮ 3A 200PYБ @crmxcz__**",
    "**__BEPUФUKAЦИЯ CEГODH9 HA ЛЮБOU ПЛOTФOPME, HE УПУCTU ШAHC, BCEГO 200PYБ @crmxcz__**",
    "**__CEГODH9 TAKOU DEHb ЧTO Я ПPOBEДEHUE BEPUФUKAЦИU PAЗДАЮ ПO 200PYБ @crmxcz__**",
    "**__3AБУДЬTE ПPO БAHЫ, СДEЛАEM BEPUФUKAЦИЮ U ЗABУДETЕ O ПPOБЛEMAX, BCEГO 200PYБ @crmxcz__**",
    "**__PEБ9TA Я CEГODH9 ДOБPЫU, СДEЛАЮ BEPUФUKAЦИЮ BCEГO 3A 200PYБ @crmxcz__**",
    "**__HE ПPOBEP9EM ЧTO TAM У TEB9, ДEЛАEM PAБOTY KAK BCEГDA, ЦEHA 200PYБ @crmxcz__**",
    "**__6 ЧACOB MOЩHOU PAБOTЫ CЕГODH9, BEPUФUKAЦИЯ ПO 200PYБ @crmxcz__**",
    "**__БEЗ BAЖHOCТU КAKAЯ ПЛOTФOPMA, ДEЛАEM ПPOUЗBOДCTBO BEPUФUKAЦИU, CEUЧAC 200PYБ @crmxcz__**",
    "**__PACCЧUTAHO HA ЛЮБOU КOШEЛEK, BEPUФUKAЦИЯ BCEГO 200PYБ, CTPOГO CEГODH9 @crmxcz__**"
]

joined_groups = set()
all_chats = {}

async def get_groups_from_bot(client):
    """Получает ссылки на группы из бота @sdguhsdg_bot"""
    groups = []
    
    try:
        messages = await client.get_messages(SOURCE_BOT, limit=1000)
        
        for msg in messages:
            if msg.message:
                links = re.findall(r'(?:t\.me/|@)([a-zA-Z0-9_]+)', msg.message)
                for link in links:
                    if link not in groups and link != SOURCE_BOT.replace('@', ''):
                        groups.append(link)
        
        logger.info(f"📊 Получено {len(groups)} групп из бота")
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения групп из бота: {e}")
    
    return groups

async def get_existing_groups(client):
    """Получает группы в которых уже состоит аккаунт"""
    groups = []
    
    try:
        dialogs = await client.get_dialogs()
        for dialog in dialogs:
            entity = dialog.entity
            
            is_group = getattr(entity, 'megagroup', False) or getattr(entity, 'gigagroup', False)
            is_basic_group = hasattr(entity, 'title') and not hasattr(entity, 'broadcast') and not hasattr(entity, 'first_name')
            
            if is_group or is_basic_group:
                chat_id = entity.id
                title = getattr(entity, 'title', 'Без названия')
                username = getattr(entity, 'username', None)
                groups.append({
                    'id': chat_id,
                    'title': title,
                    'username': username
                })
        
        logger.info(f"📊 Найдено {len(groups)} групп на аккаунте")
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения групп с аккаунта: {e}")
    
    return groups

async def join_group(client, group_username):
    """Вступает в группу"""
    try:
        entity = await client.get_entity(group_username)
        
        try:
            await client(JoinChannelRequest(entity))
            logger.info(f"✅ Вступил: {group_username}")
        except Exception:
            logger.info(f"⚠ {group_username} - уже в группе или закрытая")
            return None
        
        title = getattr(entity, 'title', group_username)
        return {'id': entity.id, 'title': title}
        
    except FloodWaitError as e:
        logger.warning(f"⚠ Telegram сказал ждать {e.seconds}с для {group_username}")
        await asyncio.sleep(e.seconds)
        return None
            
    except Exception as e:
        logger.error(f"❌ Ошибка вступления в {group_username}: {e}")
        return None

async def joiner_worker(client):
    """Воркер для вступления в группы"""
    global joined_groups, all_chats
    
    while True:
        try:
            bot_groups = await get_groups_from_bot(client)
            
            for group_link in bot_groups:
                if group_link not in joined_groups:
                    logger.info(f"🚪 Вступаем: {group_link}")
                    chat = await join_group(client, group_link)
                    
                    if chat:
                        joined_groups.add(group_link)
                        all_chats[chat['id']] = chat
            
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в joiner_worker: {e}")
            await asyncio.sleep(10)

async def sender_worker(client):
    """Воркер для рассылки сообщений"""
    global all_chats
    
    await asyncio.sleep(15)
    
    sent_total = 0
    failed_total = 0
    
    while True:
        try:
            existing = await get_existing_groups(client)
            for chat in existing:
                all_chats[chat['id']] = chat
            
            chats_list = list(all_chats.values())
            
            if not chats_list:
                await asyncio.sleep(30)
                continue
            
            logger.info(f"📨 Рассылка по {len(chats_list)} группам...")
            
            random.shuffle(chats_list)
            sent = 0
            failed = 0
            
            for idx, chat in enumerate(chats_list, 1):
                try:
                    msg = random.choice(MESSAGES)
                    
                    await client.send_message(chat['id'], msg, parse_mode='markdown')
                    logger.info(f"[{idx}/{len(chats_list)}] ✓ {chat['title']}")
                    
                    sent += 1
                    sent_total += 1
                    
                    delay = random.uniform(3, 7)
                    await asyncio.sleep(delay)
                    
                    if sent % 5 == 0:
                        extra = random.uniform(5, 10)
                        logger.info(f"⏸ Пауза {extra:.1f}с")
                        await asyncio.sleep(extra)
                    
                except FloodWaitError as e:
                    logger.warning(f"⚠ Telegram сказал ждать {e.seconds}с")
                    await asyncio.sleep(e.seconds)
                    try:
                        await client.send_message(chat['id'], random.choice(MESSAGES), parse_mode='markdown')
                        sent += 1
                        sent_total += 1
                    except:
                        failed += 1
                        failed_total += 1
                        
                except Exception as e:
                    logger.error(f"✗ {chat['title']}: {e}")
                    failed += 1
                    failed_total += 1
                    await asyncio.sleep(2)
            
            logger.info(f"📊 Рассылка: +{sent} | -{failed} | Всего: {sent_total}")
            
            wait = random.uniform(30, 60)
            logger.info(f"💤 Следующая рассылка через {wait/60:.1f} мин\n")
            await asyncio.sleep(wait)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в sender_worker: {e}")
            await asyncio.sleep(30)

async def main():
    print("\n" + "="*60)
    print("🤖 РАССЫЛКА + ВСТУПЛЕНИЕ (ТЕЛЕГРАМ ЛИМИТЫ)")
    print("="*60 + "\n")
    
    client = TelegramClient('session', API_ID, API_HASH)
    
    try:
        await client.start(phone=PHONE)
        logger.info("✅ Вход выполнен!")
        
        me = await client.get_me()
        logger.info(f"👤 Аккаунт: {me.first_name}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка входа: {e}")
        return
    
    existing = await get_existing_groups(client)
    for chat in existing:
        all_chats[chat['id']] = chat
    
    logger.info(f"📊 Загружено {len(all_chats)} групп")
    logger.info("🚀 Запуск воркеров...\n")
    
    await asyncio.gather(
        joiner_worker(client),
        sender_worker(client)
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Остановлено")
        sys.exit(0)