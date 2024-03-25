import logging
import random
import os
from dotenv import load_dotenv
from aiogram import Dispatcher, Bot, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from dao import create_room_mongo, add_participant, get_room_info, find_user_rooms, find_rooms_by_admin, \
    find_rooms_with_multiple_participants, delete_room_from_db, count_user_rooms_with_multiple_participants

load_dotenv()

API_TOKEN = os.getenv('TELEGRAM_API_KEY')
ADMIN = os.getenv('TELEGRAM_ADMIN_ID')
bot_username = os.getenv('TELEGRAM_BOT_USERNAME')

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
rooms = {}


async def on_startup(dp):
    await bot.send_message(ADMIN, 'Bot has been started')


async def on_shutdown(dp):
    await bot.send_message(ADMIN, 'Bot has been stopped')


class CreateRoom(StatesGroup):
    waiting_for_description = State()


class NewUser(StatesGroup):
    waiting_for_name = State()


class DeleteRoom(StatesGroup):
    choosing_room = State()
    confirming_deletion = State()


class RandomizePairs(StatesGroup):
    choosing_room = State()


@dp.message_handler(commands=['start'])
async def start(message: types.Message, state: FSMContext):
    args = message.get_args()
    if args:
        room_id = args
        room = await get_room_info(room_id)
        if room:
            user_id = str(message.from_user.id)
            if user_id in room["participants"]:
                await message.reply("🌟 Вы уже являетесь участником этой комнаты! 🎉")
                return
            await state.update_data(room_id=room_id)
            await message.reply(
                "🎄Хо-хо-хо!🎅\n🌟 Пожалуйста, введите ваше имя и фамилию, чтобы создать атмосферу тепла и уюта для всех участников! 🎄")
            await NewUser.waiting_for_name.set()
        else:
            await message.reply(
                "🔍 Упс! Кажется, комната не найдена... 🤔 Попробуйте проверить ID или создайте новую комнату командой /create_room 🌟")
    else:
        await message.reply(
            "🎄 Добро пожаловать в гости к Тайному Санте! ❄️\nЧтобы начать волшебное приключение, используйте команду /create_room и создайте свою собственную праздничную комнату! 🎅🌟")


@dp.message_handler(state=NewUser.waiting_for_name)
async def get_user_name(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    room_id = user_data.get('room_id')
    user_id = str(message.from_user.id)
    user_name = message.text

    # Обновление списка участников в комнате в MongoDB
    await add_participant(room_id, user_id, user_name)

    # Получение обновленной информации о комнате
    room = await get_room_info(room_id)

    await message.reply(
        f"🎅 Добро пожаловать в праздничную комнату Тайного Санты под номером {room_id}.\n"
        f"🎄*Вот что о ней рассказывают*: {room['description']} 🌟", parse_mode='markdown')

    # Оповещение администратора комнаты
    await bot.send_message(room["admin"],
                           f"🌟 У нас отличные новости! Пользователь {user_name} только что присоединился к вашей новогодней комнате 🎄. "
                           f"Давайте вместе создадим праздничное настроение! 🎉")

    await state.finish()


@dp.message_handler(commands=['create_room'])
async def create_room(message: types.Message):
    await CreateRoom.waiting_for_description.set()
    await message.reply(
        "🎇 Расскажите нам немного о вашей комнате: введите краткое описание, чтобы создать новогоднюю атмосферу! 🏠✨")


@dp.message_handler(state=CreateRoom.waiting_for_description)
async def room_description_received(message: types.Message, state: FSMContext):
    description = message.text
    admin_id = message.from_user.id
    admin_name = message.from_user.full_name

    # Создание новой комнаты и получение ее ID
    room_id = await create_room_mongo(description, admin_id, admin_name)

    join_link = f"https://t.me/{bot_username}?start={room_id}"
    await message.reply(
        f"🎉 *Комната успешно создана!* ID комнаты: `{room_id}` 🎄\n"
        f"*Описание:* `{description}` 📜\n"
        f"Вы являетесь *администратором* и первым участником этой праздничной комнаты! 🌟",
        parse_mode='markdown')
    await bot.send_message(admin_id,
                           f"🔗 *Ссылка для присоединения:* 🔗\n[Присоединиться]({join_link})",
                           parse_mode='markdown')

    await state.finish()


@dp.message_handler(commands=['room_info'])
async def room_info(message: types.Message):
    user_id = str(message.from_user.id)
    found = False
    user_rooms = await find_user_rooms(user_id)

    for room in user_rooms:
        room_id = room["room_id"]
        role = "Владелец" if room["admin"] == user_id else "Участник"
        join_link = f"https://t.me/{bot_username}?start={room_id}"

        info = (
            f"🌟 *ID комнаты:* `{room_id}` 🎄\n"
            f"*Ваша роль:* `{role}`\n"
            f"*Описание комнаты:*\n`{room['description']}` 📝\n"
            f"*Количество участников:* `{len(room['participants'])}` 🎉\n"
            f"*Список участников:* `{', '.join(room['participants'].values())}` 🎊\n"
            f"*Ссылка для присоединения:* \n"
            f"{join_link}"
        )
        await message.reply(info, parse_mode='markdown')
        found = True

    if not found:
        await message.reply(
            "🤷Похоже, вы пока не являетесь администратором ни одной комнаты. Не беда! Вы всегда можете создать свою с помощью команды /create_room 🌟")


@dp.message_handler(commands=['delete_room'], state='*')
async def start_delete_room(message: types.Message):
    user_id = str(message.from_user.id)
    user_rooms = await find_rooms_by_admin(user_id)

    if user_rooms == None:
        await message.reply("У вас нет комнат для удаления.")
        return

    markup = types.InlineKeyboardMarkup()
    for room in user_rooms:
        room_id = room["room_id"]
        markup.add(types.InlineKeyboardButton(room_id, callback_data=room_id))

    await message.reply("Выберите комнату для удаления:", reply_markup=markup)
    await DeleteRoom.choosing_room.set()


# Шаг 2: Обработка выбора комнаты пользователем
@dp.callback_query_handler(state=DeleteRoom.choosing_room)
async def confirm_delete_room(callback_query: types.CallbackQuery, state: FSMContext):
    await state.update_data(room_id=callback_query.data)
    await callback_query.message.reply(f"Вы уверены, что хотите удалить комнату {callback_query.data}?",
                                       reply_markup=types.InlineKeyboardMarkup().add(
                                           types.InlineKeyboardButton("Да, удалить", callback_data="confirm"),
                                           types.InlineKeyboardButton("Отмена", callback_data="cancel")))
    await DeleteRoom.confirming_deletion.set()


# Шаг 3: Обработка подтверждения удаления
@dp.callback_query_handler(state=DeleteRoom.confirming_deletion)
async def delete_room(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    room_id = data['room_id']

    if callback_query.data == "confirm":
        await delete_room_from_db(room_id)
        await callback_query.message.reply(f"Комната {room_id} удалена.")
    else:
        await callback_query.message.reply("Удаление отменено.")

    await state.finish()


@dp.message_handler(commands=['randomize'], state='*')
async def start_randomize_pairs(message: types.Message):
    user_id = str(message.from_user.id)
    user_rooms = await find_rooms_with_multiple_participants(user_id)
    count = await count_user_rooms_with_multiple_participants(user_id)
    if count == 0:
        await message.reply("У вас нет комнат, где вы являетесь администратором")
        return
    markup = types.InlineKeyboardMarkup()
    for room in user_rooms:
        room_id = room["room_id"]
        markup.add(types.InlineKeyboardButton(room_id, callback_data=room_id))

    await message.reply("Выберите комнату для рандомизации пар:", reply_markup=markup)
    await RandomizePairs.choosing_room.set()


@dp.callback_query_handler(state=RandomizePairs.choosing_room)
async def perform_randomization(callback_query: types.CallbackQuery, state: FSMContext):
    room_id = callback_query.data
    room = await get_room_info(room_id)

    if room and len(room["participants"]) > 1:
        # Получаем список участников
        participants = list(room["participants"].keys())
        # Перемешиваем участников
        random.shuffle(participants)

        # Сопоставляем каждому участнику следующего в списке
        pairs = {participants[i]: room["participants"][participants[(i + 1) % len(participants)]] for i in
                 range(len(participants))}

        for giver_id, receiver_name in pairs.items():
            try:
                sent_message = await bot.send_message(giver_id,
                                                      f"Комната {room_id}: 🎁 Вы должны подарить подарок - {receiver_name} 🎄",
                                                      parse_mode='markdown')
                await bot.pin_chat_message(giver_id, sent_message.message_id)
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю с ID {giver_id}: {e}")

        await callback_query.message.reply(f"Комната {room_id}: 🎊 Пары успешно сформированы и отправлены участникам! 🌟",
                                           parse_mode='markdown')
    else:
        await callback_query.message.reply("Недостаточно участников для рандомизации пар.")

    await state.finish()


if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
