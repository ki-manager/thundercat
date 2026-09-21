import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "ChatGPT")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")

MAX_MAILS_PER_FOLDER = int(os.getenv("MAX_MAILS_PER_FOLDER", "5000"))
SUBJECTS_PER_SENDER = int(os.getenv("SUBJECTS_PER_SENDER", "5"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.80"))

BATCH_SIZE_OPENAI = int(os.getenv("BATCH_SIZE_OPENAI", "5"))
BATCH_SIZE_GEMINI = int(os.getenv("BATCH_SIZE_GEMINI", "30"))
BATCH_SIZE_OLLAMA = int(os.getenv("BATCH_SIZE_OLLAMA", "5"))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "45"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "0"))

CACHE_FILE = "cache/classification_cache.json"
TAXONOMY_VERSION = "folder-taxonomy-v2"

# Die Kategoriebezeichnungen sind bewusst identisch mit den gewünschten
# Thunderbird-/IMAP-Ordnernamen.
CATEGORIES = [
    "Persönlich",
    "Arbeit",
    "Bewerbungen",
    "Recruiter",
    "Jobportale",
    "Rechnungen",
    "Banken",
    "Versicherungen",
    "Behörden",
    "Schule & Bildung",
    "Termine",
    "Konto & Sicherheit",
    "Bestellungen",
    "Versand",
    "Shops",
    "Newsletter",
    "Werbung",
    "Verträge & Service",
    "System",
    "Kundenservice",
    "Spam",
    "Unklar",
]

CATEGORY_LABELS = {category: category for category in CATEGORIES}
