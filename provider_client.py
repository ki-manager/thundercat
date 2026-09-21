import json
import time
import requests

from config import (
    CATEGORIES,
    OLLAMA_TIMEOUT,
    OPENAI_TIMEOUT,
    OPENAI_MAX_RETRIES,
)
from prompt_builder import build_batch_prompt


def _clean_result(item, min_confidence):
    category = item.get("category", "Unklar")

    if category not in CATEGORIES:
        category = "Unklar"

    try:
        confidence = float(item.get("confidence", 0))
    except Exception:
        confidence = 0.0

    if confidence < float(min_confidence):
        category = "Unklar"

    return {
        "category": category,
        "confidence": confidence,
        "reason": item.get("reason", ""),
    }


def _parse_batch_json(text, batch, min_confidence):
    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError(
            f"Modellantwort ist kein gültiges JSON: {exc}. "
            f"Antwortbeginn: {text[:300]!r}"
        )

    result_map = {}

    for item in data.get("results", []):
        email_address = item.get("email", "").lower().strip()

        if not email_address:
            continue

        result_map[email_address] = _clean_result(
            item,
            min_confidence,
        )

    for address, _ in batch:
        if address not in result_map:
            result_map[address] = {
                "category": "Unklar",
                "confidence": 0.0,
                "reason": "Keine Modell-Antwort für diesen Absender.",
            }

    return result_map


def _openai_schema():
    return {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": CATEGORIES,
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "email",
                        "category",
                        "confidence",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    }


def _openai_client(api_key):
    from openai import OpenAI

    return OpenAI(
        api_key=api_key,
        timeout=OPENAI_TIMEOUT,
        max_retries=OPENAI_MAX_RETRIES,
    )


def test_provider(
    provider,
    model,
    api_key=None,
    ollama_url=None,
):
    provider_lower = provider.lower()

    if provider_lower == "ollama":
        response = requests.get(
            f"{ollama_url}/api/tags",
            timeout=10,
        )
        response.raise_for_status()

        models = response.json().get("models", [])
        names = [item.get("name", "") for item in models]

        return {
            "ok": model in names,
            "models": names,
            "message": (
                "Ollama-Verbindung erfolgreich."
                if model in names
                else f"Modell '{model}' nicht installiert."
            ),
        }

    if not api_key:
        return {
            "ok": False,
            "models": [],
            "message": "API-Key fehlt.",
        }

    if provider_lower == "openai":
        client = _openai_client(api_key)

        response = client.responses.create(
            model=model,
            input="Antworte nur mit dem Wort OK.",
            max_output_tokens=32,
            store=False,
        )

        return {
            "ok": bool(response.output_text),
            "models": [],
            "message": "OpenAI-Verbindung erfolgreich.",
            "request_id": getattr(response, "_request_id", None),
        }

    if provider_lower == "gemini":
        from google import genai

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=model,
            contents="Antworte ausschließlich mit OK.",
        )

        return {
            "ok": bool(response.text),
            "models": [],
            "message": "Gemini-Verbindung erfolgreich.",
        }

    return {
        "ok": False,
        "models": [],
        "message": f"Unbekannter Provider: {provider}",
    }


def classify_batch_openai(
    model,
    api_key,
    batch,
    min_confidence,
):
    client = _openai_client(api_key)
    prompt = build_batch_prompt(batch)

    kwargs = {
        "model": model,
        "input": prompt,
        "store": False,
        "max_output_tokens": max(800, len(batch) * 220),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "thundercat_classification",
                "strict": True,
                "schema": _openai_schema(),
            }
        },
    }

    # Für GPT-5 nano ist minimale Reasoning-Tiefe ideal für Routing/Klassifizierung.
    if model.startswith("gpt-5"):
        kwargs["reasoning"] = {"effort": "minimal"}

    started = time.perf_counter()
    response = client.responses.create(**kwargs)
    elapsed = time.perf_counter() - started

    if not response.output_text:
        raise ValueError(
            "OpenAI hat keine Textausgabe geliefert. "
            f"Status: {getattr(response, 'status', 'unbekannt')}"
        )

    result = _parse_batch_json(
        response.output_text,
        batch,
        min_confidence,
    )

    return result, {
        "elapsed": elapsed,
        "request_id": getattr(response, "_request_id", None),
        "provider": "OpenAI",
    }


def classify_batch_gemini(
    model,
    api_key,
    batch,
    min_confidence,
):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = build_batch_prompt(batch)

    started = time.perf_counter()

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )

    elapsed = time.perf_counter() - started

    result = _parse_batch_json(
        response.text,
        batch,
        min_confidence,
    )

    return result, {
        "elapsed": elapsed,
        "request_id": None,
        "provider": "Gemini",
    }


def classify_batch_ollama(
    model,
    ollama_url,
    batch,
    min_confidence,
):
    prompt = build_batch_prompt(batch)

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
        "options": {"temperature": 0},
    }

    started = time.perf_counter()

    response = requests.post(
        f"{ollama_url}/api/chat",
        json=payload,
        timeout=(10, OLLAMA_TIMEOUT),
    )

    response.raise_for_status()

    elapsed = time.perf_counter() - started

    text = (
        response.json()
        .get("message", {})
        .get("content", "")
    )

    result = _parse_batch_json(
        text,
        batch,
        min_confidence,
    )

    return result, {
        "elapsed": elapsed,
        "request_id": None,
        "provider": "Ollama",
    }


def classify_batch(
    provider,
    model,
    batch,
    min_confidence,
    api_key=None,
    ollama_url=None,
):
    provider_lower = provider.lower()

    if provider_lower == "openai":
        return classify_batch_openai(
            model=model,
            api_key=api_key,
            batch=batch,
            min_confidence=min_confidence,
        )

    if provider_lower == "gemini":
        return classify_batch_gemini(
            model=model,
            api_key=api_key,
            batch=batch,
            min_confidence=min_confidence,
        )

    if provider_lower == "ollama":
        return classify_batch_ollama(
            model=model,
            ollama_url=ollama_url,
            batch=batch,
            min_confidence=min_confidence,
        )

    raise ValueError(f"Unbekannter Provider: {provider}")
