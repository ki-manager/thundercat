import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")

MAX_MAILS_PER_FOLDER = int(os.getenv("MAX_MAILS_PER_FOLDER", "5000"))
SUBJECTS_PER_SENDER = int(os.getenv("SUBJECTS_PER_SENDER", "5"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.80"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5"))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
CACHE_FILE = "cache/classification_cache.json"

CATEGORIES = [
    "PERSOENLICH",
    "BEWERBUNG_ARBEITGEBER",
    "RECRUITER",
    "JOBPORTAL",
    "RECHNUNG",
    "BANK",
    "VERSICHERUNG",
    "BESTELLUNG",
    "VERSAND",
    "SHOP",
    "NEWSLETTER",
    "WERBUNG",
    "VERTRAG_SERVICE",
    "SYSTEM",
    "SPAM",
    "UNKLAR",
]

CATEGORY_LABELS = {
    "PERSOENLICH": "Persönlich",
    "BEWERBUNG_ARBEITGEBER": "Bewerbungen / Arbeitgeber",
    "RECRUITER": "Bewerbungen / Recruiter",
    "JOBPORTAL": "Bewerbungen / Jobportale",
    "RECHNUNG": "Finanzen / Rechnungen",
    "BANK": "Finanzen / Banken",
    "VERSICHERUNG": "Finanzen / Versicherungen",
    "BESTELLUNG": "Einkaufen / Bestellungen",
    "VERSAND": "Einkaufen / Versand",
    "SHOP": "Einkaufen / Shops",
    "NEWSLETTER": "Newsletter",
    "WERBUNG": "Werbung",
    "VERTRAG_SERVICE": "Verträge / Service",
    "SYSTEM": "System",
    "SPAM": "Spam",
    "UNKLAR": "Unklar",
}
