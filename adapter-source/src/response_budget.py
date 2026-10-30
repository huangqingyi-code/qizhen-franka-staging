"""Bound complete JSON responses, including the public envelope."""

import json

MAX_RESPONSE_BYTES = 512 * 1024
PAGE_BUDGET_BYTES = 400 * 1024


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def artifact_page(records, offset, limit, budget=PAGE_BUDGET_BYTES):
    page = []
    used = 0
    for record in records[offset:offset + min(limit, 100)]:
        size = len(encoded(record)) + 1
        if used + size > budget:
            if not page:
                raise ValueError("ARTIFACT_METADATA_EXCEEDS_RESPONSE_BUDGET")
            break
        page.append(record)
        used += size
    end = offset + len(page)
    return page, end if end < len(records) else None


def bounded_response(result):
    if len(encoded(result)) <= MAX_RESPONSE_BYTES:
        return result
    return {"schema_version": "1.0", "backend": result["backend"],
            "simulated": result["simulated"], "sampled_at": result["sampled_at"],
            "ok": False, "data": {}, "error": {"code": "RESPONSE_TOO_LARGE",
            "message": "Use paged artifact/session operations; response exceeds 512 KiB"}}
