import asyncio
import logging
import re
import html
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from config import TELEGRAM_BOT_TOKEN
from services.mistral_service import (
    process_message_with_agent,
    search_scrapedo_raw,
    summarize_search_results,
    transcribe_audio,
    extract_text_from_file,
    summarize_text,
    get_random_compliment,
    get_random_fact
)
from handlers.search import router as search_router
from handlers.image import router as image_router

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

dp.include_router(search_router)
dp.include_router(image_router)

dialog_history = {}

def get_author_keyboard():
    buttons = [
        [InlineKeyboardButton(text="📩 Написать автору", url="https://t.me/your_username")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_response_to_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'`([^`]+?)`', r'<code>\1</code>', escaped)
    def replace_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2).strip()
        return f'<pre><code class="language-{lang}">{code}</code></pre>'
    escaped = re.sub(r'```(\w*)\n(.*?)```', replace_code_block, escaped, flags=re.DOTALL)
    return escaped
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_name = message.from_user.first_name or "друг"
    compliment = get_random_compliment()
    fact = get_random_fact()
    await message.answer(
        f"👋 Привет, <b>{user_name}</b>! {compliment}\n\n"
        f"Я умный бот с нейросетью Mistral AI. Вот что я умею:\n"
        f"• Отвечать на любые вопросы с учётом контекста\n"
        f"• Искать свежую информацию в интернете\n"
        f"• Рисовать картинки по описанию (напиши «нарисуй ...»)\n"
        f"• Распознавать голосовые сообщения 🎤\n"
        f"• Читать и пересказывать PDF, DOCX и TXT файлы\n"
        f"• Запоминать историю нашего диалога\n\n"
        f"Кстати, случайный факт: {fact}\n\n"
        f"Просто напиши мне что-нибудь!\n"
        f"Команды: /search, /image, /clear",
        parse_mode="HTML",
        reply_markup=get_author_keyboard()
    )

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    chat_id = message.chat.id
    if chat_id in dialog_history:
        dialog_history[chat_id] = []
    await message.answer("🧹 История диалога очищена.")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        text = await transcribe_audio(file_bytes.read())
        await message.answer(f"🎙️ Распознано:\n<i>{text}</i>", parse_mode="HTML")
        message.text = text
        await handle_smart_message(message)
    except Exception as e:
        await message.answer(f"❌ Ошибка обработки голосового: {e}")

@dp.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    file_name = doc.file_name or "file"
    if not file_name.endswith(('.pdf', '.docx', '.txt')):
        await message.answer("⚠️ Пока поддерживаются только PDF, DOCX и TXT.")
        return
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        file = await bot.get_file(doc.file_id)
        file_bytes = await bot.download_file(file.file_path)
        extracted = await extract_text_from_file(file_bytes.read(), file_name)
        if len(extracted) < 100:
            await message.answer(f"📄 Содержимое:\n{extracted}")
        else:
            summary = await summarize_text(extracted)
            formatted = format_response_to_html(summary)
            await message.answer(f"📝 Краткий пересказ:\n{formatted}", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка обработки файла: {e}")

@dp.message()
async def handle_smart_message(message: types.Message):
    chat_id = message.chat.id
    user_text = message.text

    history = dialog_history.get(chat_id, [])
    await message.bot.send_chat_action(chat_id=chat_id, action="typing")

    result = await process_message_with_agent(user_text, history)

    if result["type"] == "text":
        answer_text = result["content"]

        search_triggers = ["найди", "поищи", "информацию о", "расскажи о", "кто такой", "что такое"]
        if (not answer_text or not answer_text.strip()) and any(t in user_text.lower() for t in search_triggers):
            raw = await search_scrapedo_raw(user_text)
            if raw:
                answer_text = await summarize_search_results(user_text, raw)
            else:
                answer_text = "😕 Не удалось найти информацию."

        if not answer_text or not answer_text.strip():
            answer_text = "🤔 Извините, я не смог сформулировать ответ."

        formatted = format_response_to_html(answer_text)
        await message.answer(formatted, parse_mode="HTML")

        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": answer_text})
        dialog_history[chat_id] = history

    elif result["type"] == "image":
        image_io = result["content"]
        caption = result.get("caption", "")
        await message.answer_photo(
            BufferedInputFile(image_io.getvalue(), filename="generated.png"),
            caption=caption
        )
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": f"[Сгенерировано изображение: {caption}]"})
        dialog_history[chat_id] = history

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
