import asyncio
import io
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from datetime import timedelta

from aiogram.types import (
    Message,
    CallbackQuery,
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
    ChatPermissions,
)
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Font

import database as db

# .env faylidan tokenni o'qiymiz
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Xatolar va jarayonni terminalda ko'rish uchun
logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

phone_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

admin_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Statistika", callback_data="stat")],
    [InlineKeyboardButton(text="👥 Oxirgi 20 ta foydalanuvchi", callback_data="users")],
    [InlineKeyboardButton(text="📥 Hammasini Excel'ga yuklash", callback_data="export")],
])


# Shaxsiy chatda /start
@dp.message(CommandStart(), F.chat.type == "private")
async def start_private(message: Message):
    user = message.from_user

    # Bio ni olish (yashirilgan bo'lsa None bo'ladi)
    try:
        chat = await bot.get_chat(user.id)
        bio = chat.bio
    except Exception:
        bio = None

    db.add_user(user.id, user.first_name, user.last_name, user.username, bio)

    if db.has_phone(user.id):
        await message.answer(f"Salom, {user.first_name}! Siz allaqachon ro'yxatdan o'tgansiz ✅")
    else:
        await message.answer(
            f"Salom, {user.first_name}! 👮 Men guruh nazoratchisiman.\n\n"
            "Ro'yxatdan o'tish uchun telefon raqamingizni yuboring 👇",
            reply_markup=phone_kb,
        )


# Guruhda /start
@dp.message(CommandStart(), F.chat.type.in_({"group", "supergroup"}))
async def start_group(message: Message):
    await message.answer("Men shu guruhni nazorat qilaman 👮")

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "👮 Men guruh nazoratchisiman.\n\n"
        "/start - botni ishga tushirish\n"
        "/rules - guruh qoidalari\n"
        "/help - yordam"
    )


@dp.message(Command("rules"))
async def rules_cmd(message: Message):
    await message.answer(
        "📋 Guruh qoidalari\n\n"
        "1. Bir-biringizni hurmat qiling\n"
        "2. Reklama va begona havolalar taqiqlanadi\n"
        "3. Haqoratli so'zlar ishlatmang\n"
        "4. Mavzudan chetga chiqmang"
    )

warnings = {}

BAD_WORDS = {
    "axmoq", "tentak", "eshak", "hayvon",
    # O'zingiz qo'shing...
}


@dp.message(F.new_chat_members)
async def welcome(message: Message):
    for user in message.new_chat_members:
        await message.answer(
            f"Xush kelibsiz, {user.first_name}! 👋\n"
            "Qoidalarni o'qing: /rules"
        )


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.entities)
async def filter_links(message: Message):
    if message.from_user.id == ADMIN_ID:
        return
    for entity in message.entities:
        if entity.type in ("url", "text_link"):
            await message.delete()
            await message.answer(
                f"⚠️ {message.from_user.first_name}, havola yuborish taqiqlangan!"
            )
            return


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def filter_bad_words(message: Message):
    if message.from_user.id == ADMIN_ID:
        return
    text_lower = message.text.lower()
    if any(word in text_lower for word in BAD_WORDS):
        await message.delete()
        uid = message.from_user.id
        warnings[uid] = warnings.get(uid, 0) + 1
        if warnings[uid] >= 3:
            await bot.restrict_chat_member(
                message.chat.id,
                uid,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=timedelta(minutes=3),
            )
            warnings[uid] = 0
            await message.answer(
                f"🔇 {message.from_user.first_name} 3 daqiqaga cheklandi!"
            )
        else:
            await message.answer(
                f"⚠️ {message.from_user.first_name}, haqoratli so'zlar taqiqlangan! "
                f"({warnings[uid]}/3 ogohlantirish)"
            )


@dp.message(F.contact, F.chat.type == "private")
async def get_contact(message: Message):
    contact = message.contact

    # Boshqa odamning kontaktini yuborib aldamasin
    if contact.user_id != message.from_user.id:
        await message.answer("❌ Iltimos, o'zingizning raqamingizni yuboring.")
        return

    db.set_phone(message.from_user.id, contact.phone_number)
    await message.answer(
        "✅ Rahmat, ro'yxatdan o'tdingiz!",
        reply_markup=ReplyKeyboardRemove(),
    )

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID, F.chat.type == "private")
async def admin_panel(message: Message):
    await message.answer("🛠 Admin panel", reply_markup=admin_kb)


@dp.callback_query(F.data == "stat", F.from_user.id == ADMIN_ID)
async def show_stat(call: CallbackQuery):
    await call.message.answer(
        "📊 Statistika\n\n"
        f"Jami foydalanuvchilar: {db.count_users()}\n"
        f"Raqam yuborganlar: {db.count_with_phone()}\n"
        f"Bugun qo'shilganlar: {db.count_today()}"
    )
    await call.answer()


@dp.callback_query(F.data == "users", F.from_user.id == ADMIN_ID)
async def show_users(call: CallbackQuery):
    users = db.last_users()
    if not users:
        await call.message.answer("Hali hech kim yo'q.")
    else:
        text = "👥 Oxirgi foydalanuvchilar\n\n"
        for i, (uid, fn, ln, un, phone, joined) in enumerate(users, 1):
            ism = f"{fn or ''} {ln or ''}".strip()
            un = f"@{un}" if un else "—"
            line = f"{i}. {ism} | {un} | {phone or '—'} | {joined}\n"
            if len(text) + len(line) > 2000:
                await call.message.answer(text)
                text = ""
            text += line
        if text:
            await call.message.answer(text)
    await call.answer()

@dp.callback_query(F.data == "export", F.from_user.id == ADMIN_ID)
async def export_users(call: CallbackQuery):
    wb = Workbook()
    ws = wb.active
    ws.title = "Foydalanuvchilar"

    # Sarlavha qatori (qalin)
    ws.append(["ID", "Ism", "Familiya", "Username", "Telefon", "Bio", "Sana"])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Ma'lumotlar
    for row in db.all_users():
        ws.append(list(row))

    # Ustunlar kengligi
    widths = [14, 15, 15, 18, 16, 30, 18]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w

    # Faylni xotirada saqlab, Telegramga yuboramiz
    buffer = io.BytesIO()
    wb.save(buffer)

    await call.message.answer_document(
        BufferedInputFile(buffer.getvalue(), filename="foydalanuvchilar.xlsx"),
        caption=f"Jami: {db.count_users()} ta",
    )
    await call.answer()


# Shaxsiy chatdagi boshqa xabarlar (echo)
@dp.message(F.chat.type == "private")
async def echo(message: Message):
    if message.text:
        await message.answer(f"Siz yozdingiz: {message.text}")
    else:
        await message.answer("Men faqat matn xabarlarini tushunaman 😊")

async def set_commands():
    # Shaxsiy chat menyusi
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Botni ishga tushirish"),
            BotCommand(command="help", description="Yordam"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    # Guruh menyusi
    await bot.set_my_commands(
        [
            BotCommand(command="rules", description="Guruh qoidalari"),
            BotCommand(command="help", description="Yordam"),
        ],
        scope=BotCommandScopeAllGroupChats(),
    )
    # Faqat admin uchun menyu
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Botni ishga tushirish"),
            BotCommand(command="help", description="Yordam"),
            BotCommand(command="admin", description="Admin panel"),
        ],
        scope=BotCommandScopeChat(chat_id=ADMIN_ID),
    )

async def main():
    db.create_tables()
    await set_commands()
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())