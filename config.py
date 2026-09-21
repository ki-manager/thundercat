import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")

MAX_MAILS_PER_FOLDER = int(os.getenv("MAX_MAILS_PER_FOLDER", "5000"))
SUBJECTS_PER_SENDER = int(os.getenv("SUBJECTS_PER_SENDER", "5"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.80"))

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

FOLDER_MAP = {
    "PERSOENLICH": "imap://USER@SERVER/Persoenlich",
    "BEWERBUNG_ARBEITGEBER": "imap://USER@SERVER/Bewerbungen/Arbeitgeber",
    "RECRUITER": "imap://USER@SERVER/Bewerbungen/Agenturen",
    "JOBPORTAL": "imap://USER@SERVER/Bewerbungen/Jobportale",
    "RECHNUNG": "imap://USER@SERVER/Finanzen/Rechnungen",
    "BANK": "imap://USER@SERVER/Finanzen/Banken",
    "VERSICHERUNG": "imap://USER@SERVER/Finanzen/Versicherungen",
    "BESTELLUNG": "imap://USER@SERVER/Einkaufen/Bestellungen",
    "VERSAND": "imap://USER@SERVER/Einkaufen/Versand",
    "SHOP": "imap://USER@SERVER/Einkaufen/Shops",
    "NEWSLETTER": "imap://USER@SERVER/Newsletter",
    "WERBUNG": "imap://USER@SERVER/Werbung",
    "VERTRAG_SERVICE": "imap://USER@SERVER/Vertraege-Service",
    "SYSTEM": "imap://USER@SERVER/System",
    "SPAM": "imap://USER@SERVER/Spam",
}
