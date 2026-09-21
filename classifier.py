import math
import time

from cache_manager import (
    load_cache,
    save_cache,
    get_cached,
    set_cached,
)
from provider_client import classify_batch


def _error_result(batch, exc):
    return {
        address: {
            "category": "Unklar",
            "confidence": 0.0,
            "reason": f"KI-Fehler: {type(exc).__name__}: {exc}",
        }
        for address, _ in batch
    }


def _classify_batch_resilient(
    provider,
    model,
    batch,
    min_confidence,
    api_key=None,
    ollama_url=None,
    status_callback=None,
    detail_callback=None,
    split_depth=0,
):
    started = time.perf_counter()

    try:
        if status_callback:
            addresses = ", ".join(address for address, _ in batch[:3])
            if len(batch) > 3:
                addresses += f" … (+{len(batch)-3})"
            status_callback(
                f"Sende {len(batch)} Absender an {provider}: {addresses}"
            )

        result_map, meta = classify_batch(
            provider=provider,
            model=model,
            batch=batch,
            min_confidence=min_confidence,
            api_key=api_key,
            ollama_url=ollama_url,
        )

        if detail_callback:
            detail_callback(
                {
                    "ok": True,
                    "provider": provider,
                    "size": len(batch),
                    "elapsed": meta.get(
                        "elapsed",
                        time.perf_counter() - started,
                    ),
                    "request_id": meta.get("request_id"),
                    "error": None,
                }
            )

        if status_callback:
            status_callback(
                f"{provider}: {len(batch)} Absender "
                f"in {meta.get('elapsed', 0):.1f}s verarbeitet."
            )

        return result_map

    except Exception as exc:
        elapsed = time.perf_counter() - started

        if detail_callback:
            detail_callback(
                {
                    "ok": False,
                    "provider": provider,
                    "size": len(batch),
                    "elapsed": elapsed,
                    "request_id": getattr(exc, "request_id", None),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        # Cloud-Aufrufe nicht minutenlang rekursiv wiederholen.
        # Fehler wird sofort sichtbar und der nächste Batch kann weiterlaufen.
        if provider.lower() != "ollama":
            if status_callback:
                status_callback(
                    f"{provider}-Batch fehlgeschlagen nach "
                    f"{elapsed:.1f}s: {type(exc).__name__}: {exc}"
                )
            return _error_result(batch, exc)

        # Ollama darf bei lokalen Timeouts kleinere Batches probieren,
        # aber maximal zwei Teilungsebenen.
        if len(batch) <= 1 or split_depth >= 2:
            if status_callback:
                status_callback(
                    f"Ollama-Batch endgültig fehlgeschlagen: {exc}"
                )
            return _error_result(batch, exc)

        half = max(1, len(batch) // 2)
        left = batch[:half]
        right = batch[half:]

        if status_callback:
            status_callback(
                f"Ollama-Batch fehlgeschlagen. Teile auf "
                f"{len(left)} + {len(right)}."
            )

        results = {}
        results.update(
            _classify_batch_resilient(
                provider=provider,
                model=model,
                batch=left,
                min_confidence=min_confidence,
                api_key=api_key,
                ollama_url=ollama_url,
                status_callback=status_callback,
                detail_callback=detail_callback,
                split_depth=split_depth + 1,
            )
        )

        if right:
            results.update(
                _classify_batch_resilient(
                    provider=provider,
                    model=model,
                    batch=right,
                    min_confidence=min_confidence,
                    api_key=api_key,
                    ollama_url=ollama_url,
                    status_callback=status_callback,
                    detail_callback=detail_callback,
                    split_depth=split_depth + 1,
                )
            )

        return results


def classify_one(
    provider,
    model,
    address,
    info,
    min_confidence=0.0,
    api_key=None,
    ollama_url=None,
):
    result_map, meta = classify_batch(
        provider=provider,
        model=model,
        batch=[(address, info)],
        min_confidence=min_confidence,
        api_key=api_key,
        ollama_url=ollama_url,
    )
    return result_map[address], meta


def classify_all(
    provider,
    model,
    senders,
    min_confidence=0.80,
    batch_size=5,
    api_key=None,
    ollama_url=None,
    progress_callback=None,
    status_callback=None,
    detail_callback=None,
    result_callback=None,
    force_reclassify=False,
):
    cache = load_cache()
    results = {}

    items = sorted(
        senders.items(),
        key=lambda item: -item[1]["count"],
    )

    cached_count = 0
    uncached = []

    for address, info in items:
        cached = None

        if not force_reclassify:
            cached = get_cached(
                cache,
                provider,
                address,
                model,
            )

        if cached:
            results[address] = cached
            cached_count += 1
        else:
            uncached.append((address, info))

    total_new = len(uncached)
    done_new = 0
    batch_size = max(1, int(batch_size))

    total_batches = (
        math.ceil(total_new / batch_size)
        if total_new
        else 0
    )

    for batch_index in range(total_batches):
        start = batch_index * batch_size
        batch = uncached[start:start + batch_size]

        if status_callback:
            status_callback(
                f"Batch {batch_index + 1}/{total_batches}: "
                f"{len(batch)} Absender werden vorbereitet …"
            )

        batch_results = _classify_batch_resilient(
            provider=provider,
            model=model,
            batch=batch,
            min_confidence=min_confidence,
            api_key=api_key,
            ollama_url=ollama_url,
            status_callback=status_callback,
            detail_callback=detail_callback,
        )

        for address, _ in batch:
            result = batch_results.get(
                address,
                {
                    "category": "Unklar",
                    "confidence": 0.0,
                    "reason": "Kein Ergebnis.",
                },
            )

            results[address] = result

            set_cached(
                cache,
                provider,
                address,
                model,
                result,
            )

            done_new += 1

            if result_callback:
                result_callback(
                    address,
                    result,
                    cached_count + done_new,
                    len(items),
                )

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
