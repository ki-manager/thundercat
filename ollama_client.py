import json
import requests
from config import CATEGORIES

def test_ollama(base_url, model):
    response = requests.get(f"{base_url}/api/tags", timeout=10)
    response.raise_for_status()
    models = response.json().get("models", [])
    names = [item.get("name", "") for item in models]
    return {"ok": model in names, "models": names}

def classify_sender(base_url, model, address, info, min_confidence=0.80):
    prompt = f"""
Du klassifizierst E-Mail-Absender.

Verwende ausschließlich eine dieser Kategorien:
{", ".join(CATEGORIES)}

Definitionen:
PERSOENLICH: Private Kommunikation von Personen.
BEWERBUNG_ARBEITGEBER: Kommunikation eines Arbeitgebers zu einer konkreten Bewerbung.
RECRUITER: Personalvermittler, Headhunter oder Recruiting-Agentur.
JOBPORTAL: Automatische Stellenangebote oder Jobbenachrichtigungen.
RECHNUNG: Rechnung, Gutschrift oder Zahlungsaufforderung.
BANK: Banken und Finanzinstitute.
VERSICHERUNG: Versicherungskommunikation.
BESTELLUNG: Bestell- oder Auftragsbestätigung.
VERSAND: Tracking, Paketankündigung oder Versandstatus.
SHOP: Online-Shop ohne konkrete Bestellung.
NEWSLETTER: Regelmäßiger Newsletter.
WERBUNG: Marketing, Rabatt oder Verkaufsangebot.
VERTRAG_SERVICE: Hosting, Domain, Telefon, Energie, Software-Abonnement oder laufender Vertrag.
SYSTEM: Automatische Konto-, Login- oder Systemmeldung.
SPAM: Offensichtlicher Spam.
UNKLAR: Keine zuverlässige Zuordnung.

Absender: {address}
Name: {info["name"]}
Domain: {info["domain"]}
Anzahl: {info["count"]}

Beispiel-Betreffzeilen:
{json.dumps(info["subjects"], ensure_ascii=False)}

Antworte ausschließlich mit JSON:
{{
  "category": "KATEGORIE",
  "confidence": 0.95,
  "reason": "kurze Begründung"
}}
""".strip()

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    response = requests.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=120,
    )
    response.raise_for_status()

    content = response.json().get("message", {}).get("content", "")
    try:
        data = json.loads(content)
    except Exception:
        return {
            "category": "UNKLAR",
            "confidence": 0.0,
            "reason": "Ungültige JSON-Antwort",
        }

    category = data.get("category", "UNKLAR")
    if category not in CATEGORIES:
        category = "UNKLAR"

    try:
        confidence = float(data.get("confidence", 0))
    except Exception:
        confidence = 0.0

    if confidence < float(min_confidence):
        category = "UNKLAR"

    return {
        "category": category,
        "confidence": confidence,
        "reason": data.get("reason", ""),
    }

def classify_all(
    base_url,
    model,
    senders,
    min_confidence=0.80,
    progress_callback=None,
    status_callback=None,
):
    results = {}
    items = sorted(senders.items(), key=lambda item: -item[1]["count"])
    total = len(items)

    for index, (address, info) in enumerate(items, start=1):
        if status_callback:
            status_callback(f"Klassifiziere: {address}")
        try:
            result = classify_sender(
                base_url,
                model,
                address,
                info,
                min_confidence=min_confidence,
            )
        except Exception as exc:
            result = {
                "category": "UNKLAR",
                "confidence": 0.0,
                "reason": str(exc),
            }

        results[address] = result

        if progress_callback:
            progress_callback(index, total)

    return results
