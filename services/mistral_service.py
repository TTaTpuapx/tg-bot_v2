import os
import urllib.parse
import logging
import aiohttp
import random
import re
import fitz
from io import BytesIO
from docx import Document
from faster_whisper import WhisperModel
from config import MISTRAL_API_KEY, SCRAPERAPI_KEY
from mistralai.client import Mistral

client = Mistral(api_key=MISTRAL_API_KEY)
model = WhisperModel("base", device="cpu", compute_type="int8")
async def get_mistral_response(user_message: str) -> str:
    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": user_message}],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка при обращении к Mistral: {e}"

async def get_mistral_response_with_search(user_message: str) -> str:
    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": user_message}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query"}
                        },
                        "required": ["query"]
                    }
                }
            }],
            tool_choice="auto"
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка при поиске: {e}"

async def generate_image_free(prompt: str) -> BytesIO:
    safe_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&nologo=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                image_data = await resp.read()
                return BytesIO(image_data)
            else:
                raise Exception(f"Pollinations API error: {resp.status}")

async def transcribe_audio(file_bytes: bytes) -> str:
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        segments, _ = model.transcribe(tmp_path, language="ru", beam_size=5)
        text = " ".join(seg.text for seg in segments)
        os.unlink(tmp_path)
        return text.strip() or "Не удалось распознать речь."
    except Exception as e:
        logging.error(f"Transcription error: {e}")
        return f"Ошибка распознавания: {e}"

async def extract_text_from_file(file_bytes: bytes, file_name: str) -> str:
    try:
        if file_name.endswith('.pdf'):
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        elif file_name.endswith('.docx'):
            with open("temp.docx", "wb") as f:
                f.write(file_bytes)
            doc = Document("temp.docx")
            text = "\n".join(p.text for p in doc.paragraphs)
            os.remove("temp.docx")
            return text
        elif file_name.endswith('.txt'):
            return file_bytes.decode('utf-8', errors='ignore')
        else:
            return "Формат не поддерживается."
    except Exception as e:
        logging.error(f"File extraction error: {e}")
        return f"Ошибка извлечения текста: {e}"

async def summarize_text(text: str, max_tokens: int = 500) -> str:
    prompt = f"Сделай краткий пересказ (3-5 предложений) на русском:\n\n{text[:3000]}"
    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Summarize error: {e}")
        return f"Ошибка саммаризации: {e}"

async def search_scrapedo_raw(query: str, num_results: int = 3) -> list:
    api_key = SCRAPERAPI_KEY
    if not api_key:
        return []
    url = "https://api.scraperapi.com/structured/google/search"
    params = {
        "api_key": api_key,
        "query": query,
        "num": num_results,
        "country_code": "ru",
        "tld": "ru"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                organic_results = data.get("organic_results", [])
                results = []
                for item in organic_results[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", "")
                    })
                return results
        except Exception as e:
            logging.error(f"ScraperAPI raw error: {e}")
            return []

async def summarize_search_results(query: str, raw_results: list) -> str:
    if not raw_results:
        return "К сожалению, мне не удалось найти информацию по вашему запросу."
    context = "\n\n".join([
        f"Источник: {r.get('title', '')}\nТекст: {r.get('snippet', '')}"
        for r in raw_results[:3]
    ])
    prompt = f"""Пользователь спросил: "{query}"
Ниже приведены выдержки из результатов поиска. На основе только этой информации напиши краткий, но содержательный ответ на русском языке (2-4 предложения). Не упоминай источники, не используй маркдаун. Пиши как живой человек.
Информация:
{context}
Ответ:"""
    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.5
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Summarization failed: {e}")
        return raw_results[0].get('snippet', 'Информация найдена, но не удалось сформулировать ответ.')

async def get_coordinates(city_name: str) -> dict:
    geocode_url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": city_name,
        "format": "json",
        "limit": 1
    }
    headers = {"User-Agent": "MyTelegramBot/1.0"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(geocode_url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
        except Exception as e:
            logging.error(f"Geocoding error: {e}")
    return {}

async def get_weather_by_city(city_name: str) -> str:
    coords = await get_coordinates(city_name)
    if not coords:
        return f" Не могу найти город '{city_name}'. Проверьте название."

    weather_url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "current_weather": "true",
        "hourly": "temperature_2m,weathercode",
        "timezone": "auto"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(weather_url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    current = data.get("current_weather", {})
                    temperature = current.get("temperature", "N/A")
                    windspeed = current.get("windspeed", "N/A")
                    weather_code = current.get("weathercode", 0)

                    weather_desc = {
                        0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность",
                        3: "Пасмурно", 45: "Туман", 48: "Изморось", 51: "Легкая морось",
                        53: "Умеренная морось", 55: "Сильная морось", 61: "Небольшой дождь",
                        63: "Умеренный дождь", 65: "Сильный дождь", 71: "Небольшой снег",
                        73: "Умеренный снег", 75: "Сильный снег", 95: "Гроза"
                    }.get(weather_code, "Неизвестно")

                    return (f"Погода в городе **{city_name}**:\n"
                            f"Температура: **{temperature}°C**\n"
                            f"Ветер: **{windspeed} км/ч**\n"
                            f"Описание: **{weather_desc}**")
                else:
                    return " Не удалось получить данные о погоде."
        except Exception as e:
            logging.error(f"Weather API error: {e}")
            return " Ошибка при запросе погоды."

async def process_message_with_agent(user_message: str, history: list = None) -> dict:
    image_keywords = ["нарисуй", "сгенерируй", "покажи картинку", "создай изображение",
                      "нарисуй картинку", "сгенерируй изображение", "покажи фото"]
    msg_lower = user_message.lower()
    is_image_request = any(kw in msg_lower for kw in image_keywords)

    if is_image_request:
        prompt = user_message
        for kw in image_keywords:
            if kw in msg_lower:
                prompt = user_message.split(kw, 1)[-1].strip()
                break
        if not prompt:
            prompt = "кот"
        try:
            image_io = await generate_image_free(prompt)
            return {"type": "image", "content": image_io, "caption": f"Сгенерировано: {prompt}"}
        except Exception as e:
            return {"type": "text", "content": f" Не удалось сгенерировать изображение: {e}"}

    weather_keywords = ["погода", "сколько градусов", "дождь", "снег", "ветер", "температура"]
    if any(kw in msg_lower for kw in weather_keywords):
        city_name = "Москва"
        match = re.search(r'(?:погода|в)\s+([а-яё\-]+)', msg_lower)
        if match:
            city_name = match.group(1).capitalize()
        elif "москв" in msg_lower:
            city_name = "Москва"
        elif "питер" in msg_lower or "санкт-петербург" in msg_lower:
            city_name = "Санкт-Петербург"
        elif "новосибирск" in msg_lower:
            city_name = "Новосибирск"
        elif "екатеринбург" in msg_lower:
            city_name = "Екатеринбург"
        elif "нижн" in msg_lower and "новгор" in msg_lower:
            city_name = "Нижний Новгород"
        weather_answer = await get_weather_by_city(city_name)
        return {"type": "text", "content": weather_answer}

    messages = []
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=messages,
            tools=[{
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"]
                    }
                }
            }],
            tool_choice="auto"
        )
        answer = response.choices[0].message.content
        if not answer or not answer.strip():
            search_triggers = ["найди", "поищи", "информацию о", "расскажи о", "кто такой", "что такое"]
            if any(trigger in msg_lower for trigger in search_triggers):
                raw = await search_scrapedo_raw(user_message)
                if raw:
                    summary = await summarize_search_results(user_message, raw)
                    return {"type": "text", "content": summary}
                else:
                    return {"type": "text", "content": "Ничего не найдено."}
            else:
                return {"type": "text", "content": "Извините, я не смог сформулировать ответ."}
        return {"type": "text", "content": answer}
    except Exception as e:
        logging.error(f"Mistral error: {e}")
        raw = await search_scrapedo_raw(user_message)
        if raw:
            summary = await summarize_search_results(user_message, raw)
            return {"type": "text", "content": summary}
        return {"type": "text", "content": f"⚠️ Ошибка: {e}"}

COMPLIMENTS = [
    "Ты сегодня отлично выглядишь! 😊",
    "У тебя прекрасное чувство юмора!",
    "С тобой приятно общаться!",
    "Ты задаёшь очень интересные вопросы!",
    "Твой ник — просто 🔥",
]

FACTS = [
    "🐝 Пчёлы могут узнавать человеческие лица.",
    "🌍 Земля не идеальный шар, а немного сплюснута у полюсов.",
    "💡 Первая электрическая лампочка светила всего 13.5 часов.",
    "🎵 Самая короткая песня — You Suffer группы Napalm Death (1.316 сек).",
    "🍕 Слово «пицца» впервые появилось в 997 году в Италии.",
]

def get_random_compliment() -> str:
    return random.choice(COMPLIMENTS)

def get_random_fact() -> str:
    return random.choice(FACTS)
