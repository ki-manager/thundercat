import json
import requests

from config import CATEGORIES, OLLAMA_TIMEOUT
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
    except Exception:
        data = {}

    result_map = {}
    for item in data.get("results", []):
        email_address = item.get("email", "").lower().strip()
        if email_address:
            result_map[email_address] = _clean_result(item, min_confidence)

    for address, _ in batch:
        if address not in result_map:
            result_map[address] = {
                "category": "Unklar",
                "confidence": 0.0,
                "reason": "Keine gültige Modell-Antwort für diesen Absender.",
            }
    return result_map


def test_provider(provider, model, api_key=None, ollama_url=None):
    provider = provider.lower()

    if provider == "ollama":
        response = requests.get(f"{ollama_url}/api/tags", timeout=10)
        response.raise_for_status()
        names = [item.get("name", "") for item in response.json().get("models", [])]
        return {
            "ok": model in names,
            "models": names,
            "message": "Ollama erreichbar." if model in names else f"Modell '{model}' nicht installiert.",
        }

    if not api_key:
        return {"ok": False, "models": [], "message": "API-Key fehlt."}

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            input="Antworte ausschließlich mit OK.",
            max_output_tokens=8,
            store=False,
        )
        return {
            "ok": bool(response.output_text),
            "models": [],
            "message": "OpenAI-Verbindung erfolgreich.",
        }

    if provider == "gemini":
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

    return {"ok": False, "models": [], "message": f"Unbekannter Provider: {provider}"}


def classify_batch_openai(model, api_key, batch, min_confidence):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=build_batch_prompt(batch),
        store=False,
    )
    return _parse_batch_json(response.output_text, batch, min_confidence)


def classify_batch_gemini(model, api_key, batch, min_confidence):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=build_batch_prompt(batch),
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    return _parse_batch_json(response.text, batch, min_confidence)


def classify_batch_ollama(model, ollama_url, batch, min_confidence):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_batch_prompt(batch)}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    response = requests.post(
        f"{ollama_url}/api/chat",
        json=payload,
        timeout=(10, OLLAMA_TIMEOUT),
    )
    response.raise_for_status()
    text = response.json().get("message", {}).get("content", "")
    return _parse_batch_json(text, batch, min_confidence)


def classify_batch(provider, model, batch, min_confidence, api_key=None, ollama_url=None):
    provider = provider.lower()
    if provider == "openai":
        return classify_batch_openai(model, api_key, batch, min_confidence)
    if provider == "gemini":
        return classify_batch_gemini(model, api_key, batch, min_confidence)
    if provider == "ollama":
        return classify_batch_ollama(model, ollama_url, batch, min_confidence)
    raise ValueError(f"Unbekannter Provider: {provider}")
