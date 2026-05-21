import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

# ---------- ХРАНЕНИЕ ОБЪЯВЛЕНИЙ В ПАМЯТИ ----------
ads_db = []          # список объявлений
next_id = 1

# ---------- КЛАВИАТУРЫ ----------
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add")],
        [InlineKeyboardButton(text="📋 Мои", callback_data="my")],
        [InlineKeyboardButton(text="📢 Все", callback_data="all")],
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="search")]
    ])

# ---------- FSM ----------
class AddState(StatesGroup):
    title = State()
    desc = State()
    price = State()

# ---------- БОТ ----------
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Старт
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🚀 Барахолка работает!\n\n"
        "Добавляй объявления, смотри свои и чужие.\n"
        "Данные хранятся в памяти, после перезапуска бота пропадут — но для теста норм.",
        reply_markup=main_menu()
    )

# Добавление — шаг 1
@dp.callback_query(F.data == "add")
async def add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddState.title)
    await callback.message.edit_text("Введите заголовок:")
    await callback.answer()

@dp.message(AddState.title)
async def add_title(message: Message, state: FSMContext):
    if len(message.text) > 50:
        await message.answer("Слишком длинный (макс 50). Попробуйте ещё.")
        return
    await state.update_data(title=message.text)
    await state.set_state(AddState.desc)
    await message.answer("Введите описание:")

@dp.message(AddState.desc)
async def add_desc(message: Message, state: FSMContext):
    if len(message.text) > 300:
        await message.answer("Описание слишком длинное (макс 300).")
        return
    await state.update_data(desc=message.text)
    await state.set_state(AddState.price)
    await message.answer("Введите цену (только число):")

@dp.message(AddState.price)
async def add_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Цена должна быть числом. Попробуйте снова.")
        return
    data = await state.get_data()
    global next_id
    ad = {
        "id": next_id,
        "user_id": message.from_user.id,
        "username": message.from_user.username or "no_name",
        "title": data["title"],
        "desc": data["desc"],
        "price": int(message.text)
    }
    ads_db.append(ad)
    next_id += 1
    await state.clear()
    await message.answer(
        f"✅ Объявление #{ad['id']} добавлено!\n\n"
        f"{ad['title']}\n{ad['desc']}\n💰 {ad['price']} ₽",
        reply_markup=main_menu()
    )

# Мои объявления
@dp.callback_query(F.data == "my")
async def my_ads(callback: CallbackQuery):
    user_ads = [a for a in ads_db if a["user_id"] == callback.from_user.id]
    if not user_ads:
        await callback.message.edit_text("У вас пока нет объявлений.", reply_markup=main_menu())
    else:
        text = "📋 Ваши объявления:\n\n"
        for a in user_ads:
            text += f"#{a['id']} {a['title']} — {a['price']} ₽\n"
        await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

# Все объявления
@dp.callback_query(F.data == "all")
async def all_ads(callback: CallbackQuery):
    if not ads_db:
        await callback.message.edit_text("Объявлений пока нет. Добавьте первое!", reply_markup=main_menu())
    else:
        text = "📢 Все объявления:\n\n"
        for a in ads_db:
            text += f"#{a['id']} {a['title']} — {a['price']} ₽ (от @{a['username']})\n"
        await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

# Поиск (всё, что пишут в чат, ищет по заголовку+описанию)
@dp.callback_query(F.data == "search")
async def search_prompt(callback: CallbackQuery):
    await callback.message.edit_text("🔍 Напишите любое слово в чат — я найду объявления по заголовку и описанию.")
    await callback.answer()

@dp.message()
async def search_text(message: Message):
    kw = message.text.strip().lower()
    if len(kw) < 2:
        await message.answer("Слишком короткое слово (минимум 2 буквы).")
        return
    found = [a for a in ads_db if kw in a["title"].lower() or kw in a["desc"].lower()]
    if not found:
        await message.answer(f"Ничего не найдено по запросу «{kw}».")
    else:
        text = f"🔍 Результаты по «{kw}»:\n\n"
        for a in found:
            text += f"#{a['id']} {a['title']} — {a['price']} ₽\n"
        await message.answer(text)

# Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())