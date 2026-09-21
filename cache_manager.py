import json
from pathlib import Path
from config import CACHE_FILE

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
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def make_cache_key(address, model):
    return f"{model}|{address.lower().strip()}"

def get_cached(cache, address, model):
    return cache.get(make_cache_key(address, model))

def set_cached(cache, address, model, result):
    cache[make_cache_key(address, model)] = result
