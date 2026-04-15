import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
