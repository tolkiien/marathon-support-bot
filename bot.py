import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# -------------------
# Настройка логов
logging.basicConfig(level=logging.INFO)

# -------------------
# Загружаем токен из config.env
load_dotenv('config.env')
API_TOKEN = os.getenv('API_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# -------------------
# В памяти
support_messages = {}
# структура:
# { "@nickname": { "5": [(chat_id, msg_id), ...], "10": [...], ... } }

# -------------------
# FSM состояния
class SupportStates(StatesGroup):
    waiting_for_receiver = State()
    choosing_checkpoints = State()
    recording_voice = State()

class GetSupportStates(StatesGroup):
    running = State()

# -------------------
# Кнопки
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🗣 Поддержать"), KeyboardButton(text="🎧 Получить поддержку")]
    ],
    resize_keyboard=True
)

finish_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✅ Завершить")]],
    resize_keyboard=True
)

# -------------------
# Утилита для парсинга чекпойнтов
def parse_checkpoints(text: str):
    text = text.replace(" ", "")
    parts = text.split(",")
    return [p for p in parts if p.isdigit()]

# -------------------
# Команды
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привет! Что хочешь сделать?", reply_markup=main_kb)

# -------------------
# Поддержать
@dp.message(F.text == "🗣 Поддержать")
async def start_support(message: types.Message, state: FSMContext):
    await message.answer(
        "Введи никнейм друга, которого хочешь поддержать (например: @vasya):",
        reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    )
    await state.set_state(SupportStates.waiting_for_receiver)

@dp.message(SupportStates.waiting_for_receiver)
async def set_receiver(message: types.Message, state: FSMContext):
    receiver = message.text.strip()
    if not receiver.startswith("@"):
        await message.answer("Никнейм должен начинаться с @ (например: @vasya).")
        return
    await state.update_data(receiver=receiver)
    await message.answer(
        "Введи чекпойнты через запятую (например: 1,5,10,15):",
        reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    )
    await state.set_state(SupportStates.choosing_checkpoints)

@dp.message(SupportStates.choosing_checkpoints)
async def set_checkpoints(message: types.Message, state: FSMContext):
    checkpoints = parse_checkpoints(message.text)
    if not checkpoints:
        await message.answer("Не распознал чекпойнты. Введи числа через запятую (например: 1,5,10,15).")
        return
    await state.update_data(checkpoints=checkpoints, current=0)
    data = await state.get_data()
    await message.answer(
        f"Запиши голосовое для чекпойнта {data['checkpoints'][0]} км (или нажми ✅ Завершить).",
        reply_markup=finish_kb
    )
    await state.set_state(SupportStates.recording_voice)

@dp.message(SupportStates.recording_voice, F.voice)
async def record_voice(message: types.Message, state: FSMContext):
    data = await state.get_data()
    receiver = data['receiver']
    checkpoints = data['checkpoints']
    current = int(data.get('current', 0))
    checkpoint = checkpoints[current]

    support_messages.setdefault(receiver, {}).setdefault(checkpoint, []).append((message.chat.id, message.message_id))

    await message.answer(f"Голосовое для {checkpoint} км сохранено ✅", reply_markup=finish_kb)

    if current + 1 < len(checkpoints):
        await state.update_data(current=current + 1)
        next_cp = checkpoints[current + 1]
        await message.answer(f"Теперь запиши голосовое для {next_cp} км (или нажми ✅ Завершить).", reply_markup=finish_kb)
    else:
        await message.answer("Все голосовые сохранены! 🎉", reply_markup=main_kb)
        await state.clear()

@dp.message(SupportStates.recording_voice, F.text == "✅ Завершить")
async def finish_recording(message: types.Message, state: FSMContext):
    await message.answer("Запись завершена. Спасибо! Возвращаемся в меню.", reply_markup=main_kb)
    await state.clear()

@dp.message(SupportStates.recording_voice)
async def recording_non_voice(message: types.Message):
    await message.answer("Ожидаю голосовое сообщение (микрофон) или нажми ✅ Завершить.", reply_markup=finish_kb)

# -------------------
# Получить поддержку
@dp.message(F.text == "🎧 Получить поддержку")
async def get_support(message: types.Message, state: FSMContext):
    if not message.from_user.username:
        await message.answer("У тебя нет публичного @username в Telegram. Установи его и попробуй снова.")
        return
    nickname = f"@{message.from_user.username}"
    await state.update_data(nickname=nickname)

    if nickname not in support_messages:
        await message.answer("Для тебя пока нет сообщений 😔", reply_markup=main_kb)
        await state.clear()
        return

    checkpoints = sorted(support_messages[nickname].keys(), key=lambda x: int(x))
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"{cp} км")] for cp in checkpoints] + [[KeyboardButton(text="🏁 Завершить дистанцию")]],
        resize_keyboard=True
    )
    await message.answer("Нажимай на чекпойнты, чтобы получить сообщения 🎧", reply_markup=kb)
    await state.set_state(GetSupportStates.running)

@dp.message(GetSupportStates.running, F.text == "🏁 Завершить дистанцию")
async def finish_run(message: types.Message, state: FSMContext):
    await message.answer("🏁🎉🎊🥳🎈 Поздравляем с окончанием дистанции! 🎊🎉🏆🎈🥳", reply_markup=main_kb)
    await state.clear()

@dp.message(GetSupportStates.running)
async def send_support(message: types.Message, state: FSMContext):
    data = await state.get_data()
    nickname = data['nickname']
    selected = message.text.replace(" км", "").strip()

    if nickname not in support_messages or selected not in support_messages[nickname]:
        await message.answer("Для этого чекпойнта нет сообщений 😔")
        return

    for chat_id, msg_id in support_messages[nickname][selected]:
        try:
            await bot.copy_message(chat_id=message.chat.id, from_chat_id=chat_id, message_id=msg_id)
        except Exception:
            logging.exception("Не удалось скопировать сообщение")
            await message.answer("Не удалось отправить одно из сообщений (возможно удалено).")

# -------------------
if __name__ == "__main__":
    try:
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        logging.info("Бот остановлен")
