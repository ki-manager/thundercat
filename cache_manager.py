import json
from pathlib import Path

from config import CACHE_FILE, TAXONOMY_VERSION


def load_cache():
    path = Path(CACHE_FILE)

    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache):
    path = Path(CACHE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def make_cache_key(provider, address, model):
    return (
        f"{TAXONOMY_VERSION}|"
        f"{provider.lower()}|"
        f"{model}|"
        f"{address.lower().strip()}"
    )


def get_cached(cache, provider, address, model):
    return cache.get(make_cache_key(provider, address, model))


def set_cached(cache, provider, address, model, result):
    # Technische Fehlschläge/UNKLAR mit 0.0 nicht dauerhaft cachen,
    # damit sie beim nächsten Lauf erneut versucht werden.
    if (
        result.get("category") == "Unklar"
        and float(result.get("confidence", 0) or 0) <= 0
    ):
        return

    cache[make_cache_key(provider, address, model)] = result
