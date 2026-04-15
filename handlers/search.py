from aiogram import types, Router
from aiogram.filters import Command
from services.mistral_service import get_mistral_response_with_search

router = Router()

@router.message(Command("search"))
async def cmd_search(message: types.Message):
    query = message.text.replace("/search", "").strip()
    if not query:
        await message.answer("Пожалуйста, укажите запрос после команды /search\nНапример: /search погода в Москве")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    answer = await get_mistral_response_with_search(query)
    await message.answer(answer)
