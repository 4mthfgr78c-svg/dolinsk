import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

ADMINS = list(map(int, os.getenv("ADMINS", "").split(","))) if os.getenv("ADMINS") else []

# ---------- ХРАНЕНИЕ ДАННЫХ ----------
ads_db = []
users_db = []
next_ad_id = 1

ratings = {}
profiles = {}
forum_topics = {}
next_topic_id = 1

# ---------- ПОСТОЯННАЯ КЛАВИАТУРА ----------
reply_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🏠 Главное меню")]],
    resize_keyboard=True,
    one_time_keyboard=False
)

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def is_admin(user_id):
    return user_id in ADMINS

def get_display_name(user_id):
    """Возвращает имя для отображения на форуме (из анкеты или анонимное)"""
    profile = profiles.get(user_id, {})
    if profile.get('name') and profile['name'].strip():
        return profile['name']
    else:
        return f"Участник_{str(user_id)[-4:]}"

def get_rating(user_id):
    r = ratings.get(user_id, {'score': 0, 'votes': 0})
    if r['votes'] == 0:
        return "нет оценок"
    return f"{r['score']} ★ (голосов: {r['votes']})"

def update_rating(seller_id, delta):
    if seller_id not in ratings:
        ratings[seller_id] = {'score': 0, 'votes': 0}
    ratings[seller_id]['score'] += delta
    ratings[seller_id]['votes'] += 1

def format_ad(ad):
    rating_str = get_rating(ad['user_id'])
    profile = profiles.get(ad['user_id'], {})
    seller_info = f"👤 {profile.get('name', 'не указано')} | {profile.get('city', '?')}\n⭐ Рейтинг: {rating_str}"
    text = (
        f"📌 *{ad['title']}*\n"
        f"📂 {ad['category']}\n"
        f"💰 {ad['price']} ₽\n"
        f"📝 {ad['desc']}\n\n"
        f"{seller_info}"
    )
    return text

# ---------- INLINE-КЛАВИАТУРЫ ----------
def get_main_menu(user_id):
    buttons = [
        [InlineKeyboardButton(text="➕ Подать объявление", callback_data="add_ad")],
        [InlineKeyboardButton(text="📋 Мои объявления", callback_data="my_ads")],
        [InlineKeyboardButton(text="📢 Все объявления", callback_data="all_ads")],
        [InlineKeyboardButton(text="⭐ Моя анкета", callback_data="my_profile")],
        [InlineKeyboardButton(text="💬 Форум", callback_data="forum_menu")],
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="search")]
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="📢 Рассылка (админ)", callback_data="broadcast_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def categories_menu():
    cats = ["🚗 Автозапчасти", "🐟 Морепродукты", "🏠 Недвижимость", "💼 Услуги",
            "📱 Электроника", "👕 Одежда", "🧸 Детское", "🐾 Зоотовары",
            "🛋️ Мебель", "🌿 Для дома", "🎁 Другое"]
    buttons = []
    for i in range(0, len(cats), 2):
        row = [InlineKeyboardButton(text=cats[i], callback_data=f"cat_{cats[i]}")]
        if i+1 < len(cats):
            row.append(InlineKeyboardButton(text=cats[i+1], callback_data=f"cat_{cats[i+1]}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 На главную", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- FSM ----------
class AddAdStates(StatesGroup):
    category = State()
    title = State()
    desc = State()
    price = State()
    photos = State()

class ProfileStates(StatesGroup):
    name = State()
    city = State()
    contact = State()

class ForumStates(StatesGroup):
    new_topic_title = State()
    new_topic_text = State()
    reply_to_topic = State()

class BroadcastState(StatesGroup):
    waiting = State()

# ---------- БОТ ----------
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------- СТАРТ И МЕНЮ ----------
@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id not in users_db:
        users_db.append(message.from_user.id)
    await message.answer(
        "👋 Добро пожаловать в местную барахолку!\n\n"
        "Здесь можно продать что угодно: от рыбы до запчастей.\n"
        "Добавляй объявления, общайся на форуме, ставь оценки.\n\n"
        "Чем могу помочь?",
        reply_markup=reply_menu
    )
    await message.answer("Главное меню:", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "🏠 Главное меню")
@dp.message(Command("menu"))
async def show_menu(message: Message):
    await message.answer("Главное меню:", reply_markup=get_main_menu(message.from_user.id))

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()

# ---------- ОБЪЯВЛЕНИЯ ----------
@dp.callback_query(F.data == "add_ad")
async def add_ad_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddAdStates.category)
    await callback.message.edit_text("Выбери категорию:", reply_markup=categories_menu())
    await callback.answer()

@dp.callback_query(AddAdStates.category, F.data.startswith("cat_"))
async def add_ad_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("_", 1)[1]
    await state.update_data(category=category)
    await state.set_state(AddAdStates.title)
    await callback.message.edit_text("Введи заголовок (до 50 символов):")
    await callback.answer()

@dp.message(AddAdStates.title)
async def add_ad_title(message: Message, state: FSMContext):
    if len(message.text) > 50:
        await message.answer("Слишком длинный заголовок, сократи.")
        return
    await state.update_data(title=message.text)
    await state.set_state(AddAdStates.desc)
    await message.answer("Теперь описание (до 300 символов):")

@dp.message(AddAdStates.desc)
async def add_ad_desc(message: Message, state: FSMContext):
    if len(message.text) > 300:
        await message.answer("Многовато, покороче.")
        return
    await state.update_data(desc=message.text)
    await state.set_state(AddAdStates.price)
    await message.answer("Цену (только число):")

@dp.message(AddAdStates.price)
async def add_ad_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Цифрами пиши.")
        return
    await state.update_data(price=int(message.text))
    await state.update_data(photos=[])
    await state.set_state(AddAdStates.photos)
    await message.answer("Пришли до 3 фото (по одному). Когда закончишь, напиши /done")

@dp.message(AddAdStates.photos, F.photo)
async def add_ad_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    if len(photos) >= 3:
        await message.answer("Уже 3 фото, жми /done")
        return
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Фото {len(photos)}/3. Добавляй ещё или /done")

@dp.message(AddAdStates.photos, F.text == "/done")
async def add_ad_done(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    global next_ad_id
    ad = {
        "id": next_ad_id,
        "user_id": message.from_user.id,
        "username": message.from_user.username or "no_name",
        "category": data['category'],
        "title": data['title'],
        "desc": data['desc'],
        "price": data['price'],
        "photos": photos,
        "created": asyncio.get_event_loop().time()
    }
    ads_db.append(ad)
    next_ad_id += 1
    await state.clear()

    if photos:
        await message.answer_photo(photo=photos[0], caption=format_ad(ad), parse_mode="Markdown")
        if len(photos) > 1:
            await message.answer_media_group([InputMediaPhoto(media=p) for p in photos[1:]])
    else:
        await message.answer(format_ad(ad), parse_mode="Markdown")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 +1", callback_data=f"rate_up_{ad['id']}_{ad['user_id']}"),
         InlineKeyboardButton(text="👎 -1", callback_data=f"rate_down_{ad['id']}_{ad['user_id']}")],
        [InlineKeyboardButton(text="📩 Написать продавцу", url=f"https://t.me/{ad['username']}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])
    await message.answer("Объявление готово! Можешь оценить продавца:", reply_markup=keyboard)

@dp.message(AddAdStates.photos)
async def add_ad_photo_invalid(message: Message):
    await message.answer("Отправь фото или команду /done")

# ---------- РЕЙТИНГ ----------
@dp.callback_query(F.data.startswith("rate_up_"))
async def rate_up(callback: CallbackQuery):
    _, _, ad_id, seller_id = callback.data.split("_")
    seller_id = int(seller_id)
    if callback.from_user.id == seller_id:
        await callback.answer("Нельзя оценивать себя", show_alert=True)
        return
    update_rating(seller_id, +1)
    await callback.answer("Плюс поставлен", show_alert=True)

@dp.callback_query(F.data.startswith("rate_down_"))
async def rate_down(callback: CallbackQuery):
    _, _, ad_id, seller_id = callback.data.split("_")
    seller_id = int(seller_id)
    if callback.from_user.id == seller_id:
        await callback.answer("Себя не минусуют", show_alert=True)
        return
    update_rating(seller_id, -1)
    await callback.answer("Минус поставлен", show_alert=True)

# ---------- МОИ ОБЪЯВЛЕНИЯ ----------
@dp.callback_query(F.data == "my_ads")
async def my_ads(callback: CallbackQuery):
    user_ads = [a for a in ads_db if a['user_id'] == callback.from_user.id]
    if not user_ads:
        await callback.message.edit_text("У тебя пока нет объявлений.", reply_markup=get_main_menu(callback.from_user.id))
    else:
        text = "Твои объявления:\n\n"
        for a in user_ads:
            text += f"#{a['id']} {a['title']} — {a['price']} ₽\n"
        await callback.message.edit_text(text, reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()

# ---------- ВСЕ ОБЪЯВЛЕНИЯ ----------
@dp.callback_query(F.data == "all_ads")
async def all_ads_start(callback: CallbackQuery):
    if not ads_db:
        await callback.message.edit_text("Объявлений пока нет.", reply_markup=get_main_menu(callback.from_user.id))
        await callback.answer()
        return
    await show_ad(callback, 0)

async def show_ad(callback: CallbackQuery, index):
    if index >= len(ads_db):
        await callback.message.edit_text("Больше объявлений нет.", reply_markup=get_main_menu(callback.from_user.id))
        await callback.answer()
        return
    ad = ads_db[index]
    text = format_ad(ad)
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"ad_nav_{index-1}"))
    if index < len(ads_db)-1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"ad_nav_{index+1}"))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        nav_buttons,
        [InlineKeyboardButton(text="👍 +1", callback_data=f"rate_up_{ad['id']}_{ad['user_id']}"),
         InlineKeyboardButton(text="👎 -1", callback_data=f"rate_down_{ad['id']}_{ad['user_id']}")],
        [InlineKeyboardButton(text="📩 Написать продавцу", url=f"https://t.me/{ad['username']}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])
    if ad['photos']:
        await callback.message.edit_media(media=InputMediaPhoto(media=ad['photos'][0], caption=text, parse_mode="Markdown"), reply_markup=keyboard)
    else:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("ad_nav_"))
async def ad_nav(callback: CallbackQuery):
    index = int(callback.data.split("_")[-1])
    await show_ad(callback, index)

# ---------- АНКЕТА ----------
@dp.callback_query(F.data == "my_profile")
async def my_profile_menu(callback: CallbackQuery):
    profile = profiles.get(callback.from_user.id, {})
    text = "⭐ Твоя анкета:\n\n"
    text += f"Имя: {profile.get('name', 'не указано')}\n"
    text += f"Город: {profile.get('city', 'не указано')}\n"
    text += f"Контакт: {profile.get('contact', 'не указано')}\n"
    text += f"\nРейтинг: {get_rating(callback.from_user.id)}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Заполнить / редактировать", callback_data="edit_profile")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "edit_profile")
async def edit_profile(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.name)
    await callback.message.edit_text("Введи своё имя (оно будет показываться на форуме и в объявлениях):")
    await callback.answer()

@dp.message(ProfileStates.name)
async def profile_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ProfileStates.city)
    await message.answer("Теперь город (например, Долинск):")

@dp.message(ProfileStates.city)
async def profile_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(ProfileStates.contact)
    await message.answer("Контактные данные (телефон, @username и т.п.):")

@dp.message(ProfileStates.contact)
async def profile_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    profiles[message.from_user.id] = {
        'name': data['name'],
        'city': data['city'],
        'contact': message.text
    }
    await state.clear()
    await message.answer("Анкета сохранена! Теперь на форуме будет отображаться твоё имя.", reply_markup=get_main_menu(message.from_user.id))

# ---------- ФОРУМ (без реальных username) ----------
@dp.callback_query(F.data == "forum_menu")
async def forum_menu(callback: CallbackQuery):
    if not forum_topics:
        text = "На форуме пока пусто. Создай первую тему!"
    else:
        text = "Темы форума:\n\n"
        for tid, topic in forum_topics.items():
            text += f"{tid}. {topic['title']} (автор: {topic['author_display_name']}, ответов: {len(topic['messages'])-1})\n"
        text += "\nЧтобы открыть тему, введи её номер в чат."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать тему", callback_data="new_topic")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "new_topic")
async def new_topic_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ForumStates.new_topic_title)
    await callback.message.edit_text("Введите заголовок новой темы (до 80 символов):")
    await callback.answer()

@dp.message(ForumStates.new_topic_title)
async def new_topic_title(message: Message, state: FSMContext):
    if len(message.text) > 80:
        await message.answer("Слишком длинный заголовок.")
        return
    await state.update_data(title=message.text)
    await state.set_state(ForumStates.new_topic_text)
    await message.answer("Теперь первый пост (текст):")

@dp.message(ForumStates.new_topic_text)
async def new_topic_text(message: Message, state: FSMContext):
    data = await state.get_data()
    global next_topic_id
    display = get_display_name(message.from_user.id)
    topic = {
        'title': data['title'],
        'author_id': message.from_user.id,
        'author_display_name': display,
        'messages': [{
            'author_id': message.from_user.id,
            'display_name': display,
            'text': message.text,
            'timestamp': asyncio.get_event_loop().time()
        }]
    }
    forum_topics[next_topic_id] = topic
    next_topic_id += 1
    await state.clear()
    await message.answer("✅ Тема создана! Теперь она видна в списке форума.", reply_markup=get_main_menu(message.from_user.id))

# ---------- ПРОСМОТР ТЕМЫ И ПОИСК (только когда нет состояния) ----------
@dp.message(StateFilter(None))
async def handle_topic_number_or_search(message: Message):
    if message.text.isdigit():
        tid = int(message.text)
        if tid in forum_topics:
            topic = forum_topics[tid]
            text = f"📌 {topic['title']}\n\n"
            for msg in topic['messages']:
                text += f"{msg['display_name']}: {msg['text']}\n\n"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_topic_{tid}")],
                [InlineKeyboardButton(text="🔙 К списку тем", callback_data="forum_menu")]
            ])
            await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer("Темы с таким номером нет.")
        return
    # Поиск
    kw = message.text.strip().lower()
    if len(kw) < 2:
        await message.answer("Слишком короткое слово (минимум 2 буквы).")
        return
    found_ads = [a for a in ads_db if kw in a['title'].lower() or kw in a['desc'].lower()]
    found_topics = [t for t in forum_topics.values() if kw in t['title'].lower() or any(kw in m['text'].lower() for m in t['messages'])]
    result_text = f"🔍 Результаты по слову «{kw}»:\n\n"
    if found_ads:
        result_text += "📢 Объявления:\n"
        for a in found_ads[:5]:
            result_text += f"#{a['id']} {a['title']} — {a['price']} ₽\n"
        result_text += "\n"
    if found_topics:
        result_text += "💬 Темы форума:\n"
        for t in found_topics[:5]:
            result_text += f"• {t['title']}\n"
    if not found_ads and not found_topics:
        result_text = f"Ничего не нашлось по запросу «{kw}»."
    await message.answer(result_text)

@dp.callback_query(F.data.startswith("reply_topic_"))
async def reply_start(callback: CallbackQuery, state: FSMContext):
    tid = int(callback.data.split("_")[-1])
    await state.update_data(topic_id=tid)
    await state.set_state(ForumStates.reply_to_topic)
    await callback.message.edit_text("Напиши свой ответ:")
    await callback.answer()

@dp.message(ForumStates.reply_to_topic)
async def reply_text(message: Message, state: FSMContext):
    data = await state.get_data()
    tid = data['topic_id']
    topic = forum_topics.get(tid)
    if not topic:
        await message.answer("Тема не найдена.")
        await state.clear()
        return
    display = get_display_name(message.from_user.id)
    topic['messages'].append({
        'author_id': message.from_user.id,
        'display_name': display,
        'text': message.text,
        'timestamp': asyncio.get_event_loop().time()
    })
    await state.clear()
    await message.answer("Ответ добавлен!", reply_markup=get_main_menu(message.from_user.id))

# ---------- АДМИНСКАЯ РАССЫЛКА ----------
@dp.callback_query(F.data == "broadcast_admin")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступно только админам", show_alert=True)
        return
    await state.set_state(BroadcastState.waiting)
    await callback.message.edit_text("📢 Отправьте текст сообщения для рассылки всем пользователям.\nДля отмены отправьте /cancel")
    await callback.answer()

@dp.message(BroadcastState.waiting)
async def broadcast_send(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Рассылка отменена.")
        return
    sent = 0
    for uid in users_db:
        try:
            await bot.send_message(uid, message.text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Рассылка завершена. Отправлено {sent} из {len(users_db)} пользователей.")
    await state.clear()
    await show_menu(message)

# ---------- ЗАПУСК ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())