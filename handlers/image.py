from aiogram import types, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from services.mistral_service import generate_image_free

router = Router()

@router.message(Command("image"))
async def cmd_image(message: types.Message):
    prompt = message.text.replace("/image", "").strip()
    if not prompt:
        await message.answer("Пожалуйста, укажите описание изображения после команды /image\nНапример: /image кот в космосе")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="upload_photo")
    try:
        image_io = await generate_image_free(prompt)
        await message.answer_photo(
            BufferedInputFile(image_io.getvalue(), filename="generated.png"),
            caption=f"Сгенерировано по запросу: {prompt}"
        )
    except Exception as e:
        await message.answer(f"Не удалось сгенерировать изображение: {e}")
