import json
import math
import requests

from config import (
    CATEGORIES,
    OLLAMA_TIMEOUT,
)
from cache_manager import (
    load_cache,
    save_cache,
    get_cached,
    set_cached,
)


def test_ollama(base_url, model):
    response = requests.get(
        f"{base_url}/api/tags",
        timeout=10,
    )

    response.raise_for_status()

    models = response.json().get(
        "models",
        [],
    )

    names = [
        item.get("name", "")
        for item in models
    ]

    return {
        "ok": model in names,
        "models": names,
    }


def _clean_result(item, min_confidence):
    category = item.get(
        "category",
        "UNKLAR",
    )

    if category not in CATEGORIES:
        category = "UNKLAR"

    try:
        confidence = float(
            item.get(
                "confidence",
                0,
            )
        )
    except Exception:
        confidence = 0.0

    if confidence < float(min_confidence):
        category = "UNKLAR"

    return {
        "category": category,
        "confidence": confidence,
        "reason": item.get("reason", ""),
    }


def classify_batch(
    base_url,
    model,
    batch,
    min_confidence=0.80,
):
    compact = []

    for address, info in batch:
        compact.append({
            "email": address,
            "name": info["name"],
            "domain": info["domain"],
            "count": info["count"],
            "subjects": info["subjects"],
        })

    prompt = f"""
Du klassifizierst E-Mail-Absender.

Verwende ausschließlich eine dieser Kategorien:
{", ".join(CATEGORIES)}

Definitionen:

PERSOENLICH:
Private Kommunikation von Personen.

BEWERBUNG_ARBEITGEBER:
Kommunikation eines Arbeitgebers zu einer konkreten Bewerbung.

RECRUITER:
Personalvermittler, Headhunter oder Recruiting-Agentur.

JOBPORTAL:
Automatische Stellenangebote oder Jobbenachrichtigungen.

RECHNUNG:
Rechnung, Gutschrift oder Zahlungsaufforderung.

BANK:
Banken und Finanzinstitute.

VERSICHERUNG:
Versicherungskommunikation.

BESTELLUNG:
Bestell- oder Auftragsbestätigung.

VERSAND:
Tracking, Paketankündigung oder Versandstatus.

SHOP:
Online-Shop ohne konkrete Bestellung.

NEWSLETTER:
Regelmäßiger Newsletter.

WERBUNG:
Marketing, Rabatt oder Verkaufsangebot.

VERTRAG_SERVICE:
Hosting, Domain, Telefon, Energie,
Software-Abonnement oder laufender Vertrag.

SYSTEM:
Automatische Konto-, Login- oder Systemmeldung.

SPAM:
Offensichtlicher Spam.

UNKLAR:
Keine zuverlässige Zuordnung.

Klassifiziere ALLE folgenden Einträge.

Eingabe:
{json.dumps(compact, ensure_ascii=False)}

Antworte ausschließlich mit JSON in diesem Format:

{{
  "results": [
    {{
      "email": "adresse@example.de",
      "category": "KATEGORIE",
      "confidence": 0.95,
      "reason": "kurze Begründung"
    }}
  ]
}}
""".strip()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
    }

    response = requests.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=(
            10,
            OLLAMA_TIMEOUT,
        ),
    )

    response.raise_for_status()

    content = (
        response
        .json()
        .get("message", {})
        .get("content", "")
    )

    try:
        data = json.loads(content)
    except Exception:
        data = {}

    result_map = {}

    for item in data.get("results", []):
        email_address = (
            item
            .get("email", "")
            .lower()
            .strip()
        )

        if not email_address:
            continue

        result_map[email_address] = _clean_result(
            item,
            min_confidence,
        )

    for address, _ in batch:
        if address not in result_map:
            result_map[address] = {
                "category": "UNKLAR",
                "confidence": 0.0,
                "reason": (
                    "Keine gültige Ollama-Antwort "
                    "für diesen Absender."
                ),
            }

    return result_map


def classify_batch_resilient(
    base_url,
    model,
    batch,
    min_confidence,
    status_callback=None,
):
    try:
        return classify_batch(
            base_url=base_url,
            model=model,
            batch=batch,
            min_confidence=min_confidence,
        )

    except requests.exceptions.ReadTimeout:
        if len(batch) == 1:
            address, _ = batch[0]

            return {
                address: {
                    "category": "UNKLAR",
                    "confidence": 0.0,
                    "reason": (
                        f"Ollama-Timeout nach "
                        f"{OLLAMA_TIMEOUT} Sekunden."
                    ),
                }
            }

        half = max(
            1,
            len(batch) // 2,
        )

        left = batch[:half]
        right = batch[half:]

        if status_callback:
            status_callback(
                f"Timeout bei Batch mit {len(batch)} Absendern. "
                f"Teile automatisch auf "
                f"{len(left)} + {len(right)}."
            )

        results = {}

        results.update(
            classify_batch_resilient(
                base_url=base_url,
                model=model,
                batch=left,
                min_confidence=min_confidence,
                status_callback=status_callback,
            )
        )

        if right:
            results.update(
                classify_batch_resilient(
                    base_url=base_url,
                    model=model,
                    batch=right,
                    min_confidence=min_confidence,
                    status_callback=status_callback,
                )
            )

        return results

    except requests.exceptions.RequestException as exc:
        if len(batch) == 1:
            address, _ = batch[0]

            return {
                address: {
                    "category": "UNKLAR",
                    "confidence": 0.0,
                    "reason": (
                        f"Ollama-/HTTP-Fehler: {exc}"
                    ),
                }
            }

        half = max(
            1,
            len(batch) // 2,
        )

        left = batch[:half]
        right = batch[half:]

        if status_callback:
            status_callback(
                f"HTTP-Fehler bei Batch mit "
                f"{len(batch)} Absendern. "
                f"Versuche kleinere Batches."
            )

        results = {}

        results.update(
            classify_batch_resilient(
                base_url=base_url,
                model=model,
                batch=left,
                min_confidence=min_confidence,
                status_callback=status_callback,
            )
        )

        if right:
            results.update(
                classify_batch_resilient(
                    base_url=base_url,
                    model=model,
                    batch=right,
                    min_confidence=min_confidence,
                    status_callback=status_callback,
                )
            )

        return results


def classify_all(
    base_url,
    model,
    senders,
    min_confidence=0.80,
    batch_size=5,
    progress_callback=None,
    status_callback=None,
    force_reclassify=False,
):
    cache = load_cache()
    results = {}

    items = sorted(
        senders.items(),
        key=lambda item:
        -item[1]["count"],
    )

    cached_count = 0
    uncached = []

    for address, info in items:
        cached = None

        if not force_reclassify:
            cached = get_cached(
                cache,
                address,
                model,
            )

        if cached:
            results[address] = cached
            cached_count += 1
        else:
            uncached.append(
                (
                    address,
                    info,
                )
            )

    total_new = len(uncached)
    done_new = 0

    total_batches = (
        math.ceil(
            total_new
            / int(batch_size)
        )
        if total_new
        else 0
    )

    for batch_index in range(total_batches):
        start = batch_index * int(batch_size)

        batch = uncached[
            start:
            start + int(batch_size)
        ]

        if status_callback:
            status_callback(
                f"Batch {batch_index + 1}/"
                f"{total_batches} – "
                f"{len(batch)} Absender"
            )

        batch_results = classify_batch_resilient(
            base_url=base_url,
            model=model,
            batch=batch,
            min_confidence=min_confidence,
            status_callback=status_callback,
        )

        for address, _ in batch:
            result = batch_results.get(
                address,
                {
                    "category": "UNKLAR",
                    "confidence": 0.0,
                    "reason": "Kein Ergebnis.",
                },
            )

            results[address] = result

            set_cached(
                cache,
                address,
                model,
                result,
            )

            done_new += 1

            if progress_callback:
                progress_callback(
                    cached_count + done_new,
                    len(items),
                    cached_count,
                    total_new,
                )

        save_cache(cache)

    if total_new == 0 and progress_callback:
        progress_callback(
            len(items),
            len(items),
            cached_count,
            total_new,
        )

    return (
        results,
        {
            "cached": cached_count,
            "new": total_new,
            "total": len(items),
        },
    )
