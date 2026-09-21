import math

from cache_manager import load_cache, save_cache, get_cached, set_cached
from provider_client import classify_batch


def _classify_batch_resilient(
    provider,
    model,
    batch,
    min_confidence,
    api_key=None,
    ollama_url=None,
    status_callback=None,
):
    try:
        return classify_batch(
            provider=provider,
            model=model,
            batch=batch,
            min_confidence=min_confidence,
            api_key=api_key,
            ollama_url=ollama_url,
        )
    except Exception as exc:
        if len(batch) == 1:
            address, _ = batch[0]
            return {
                address: {
                    "category": "UNKLAR",
                    "confidence": 0.0,
                    "reason": str(exc),
                }
            }

        half = max(1, len(batch) // 2)
        left = batch[:half]
        right = batch[half:]

        if status_callback:
            status_callback(
                f"Fehler bei Batch mit {len(batch)} Absendern. "
                f"Teile automatisch auf {len(left)} + {len(right)}."
            )

        results = {}
        results.update(
            _classify_batch_resilient(
                provider, model, left, min_confidence,
                api_key=api_key, ollama_url=ollama_url,
                status_callback=status_callback,
            )
        )
        if right:
            results.update(
                _classify_batch_resilient(
                    provider, model, right, min_confidence,
                    api_key=api_key, ollama_url=ollama_url,
                    status_callback=status_callback,
                )
            )
        return results


def classify_all(
    provider,
    model,
    senders,
    min_confidence=0.80,
    batch_size=20,
    api_key=None,
    ollama_url=None,
    progress_callback=None,
    status_callback=None,
    force_reclassify=False,
):
    cache = load_cache()
    results = {}
    items = sorted(senders.items(), key=lambda item: -item[1]["count"])

    cached_count = 0
    uncached = []

    for address, info in items:
        cached = None
        if not force_reclassify:
            cached = get_cached(cache, provider, address, model)
        if cached:
            results[address] = cached
            cached_count += 1
        else:
            uncached.append((address, info))

    total_new = len(uncached)
    done_new = 0
    total_batches = math.ceil(total_new / int(batch_size)) if total_new else 0

    for batch_index in range(total_batches):
        start = batch_index * int(batch_size)
        batch = uncached[start:start + int(batch_size)]

        if status_callback:
            status_callback(
                f"{provider}: Batch {batch_index + 1}/{total_batches} – {len(batch)} Absender"
            )

        batch_results = _classify_batch_resilient(
            provider=provider,
            model=model,
            batch=batch,
            min_confidence=min_confidence,
            api_key=api_key,
            ollama_url=ollama_url,
            status_callback=status_callback,
        )

        for address, _ in batch:
            result = batch_results.get(
                address,
                {"category": "UNKLAR", "confidence": 0.0, "reason": "Kein Ergebnis."},
            )
            results[address] = result
            set_cached(cache, provider, address, model, result)
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
        progress_callback(len(items), len(items), cached_count, total_new)

    return results, {
        "cached": cached_count,
        "new": total_new,
        "total": len(items),
    }
