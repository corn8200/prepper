"""LLM-powered classification and summarization helpers.

This module is optional and only used when `OPENAI_API_KEY` is set and
`LLM_CLASSIFY_NEWS` is truthy. It classifies RSS items for prepper relevance
and returns a filtered list suitable for confirmation signals.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Tuple


DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


def _use_llm() -> bool:
    flag = os.getenv("LLM_CLASSIFY_NEWS", "").strip().lower() in {"1", "true", "yes", "on"}
    return bool(os.getenv("OPENAI_API_KEY")) and flag


def classify_news_items(
    items: List[Dict[str, Any]],
    *,
    location_id: str,
    geo_terms: Iterable[str] | None = None,
    locality: Dict[str, str] | None = None,
    max_items: int = 10,
    model: str | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (filtered_items, meta) keeping only LLM-flagged prepper-relevant items.

    Each input item should include at minimum: title, link, domain.
    """
    if not _use_llm() or not items:
        return [], {"used": False, "reason": "LLM disabled or no items"}

    model = model or DEFAULT_MODEL
    # Keep a small, recent slice to bound cost
    batch = items[: max(1, max_items)]

    payload = {
        "location": location_id,
        "geo_terms": list(geo_terms or []),
        "locality": locality or {},
        "items": [
            {
                "title": (i.get("title") or "")[:200],
                "summary": (i.get("summary") or "")[:400],
                "content": (i.get("content") or "")[: int(os.getenv("LLM_MAX_CHARS", "1000"))],
                "domain": i.get("domain") or i.get("source") or "",
                "link": i.get("link") or i.get("url") or "",
            }
            for i in batch
        ],
    }

    system = (
        "You are a risk triage analyst for emergency preparedness."
        " Only mark items PREPPER_RELEVANT when BOTH conditions are met:"
        " (1) Hazard: clear near-term threat or impact (disaster, severe weather, civil unrest/violence,"
        " infrastructure outage, hazmat/chemical spill, evacuation/shelter-in-place, lockdown, major road closure,"
        " public health emergency)."
        " (2) Locality: specifically pertains to the provided city or county; state-wide or state-only mentions are insufficient."
        " Always exclude sports, entertainment, routine politics, finance, human interest, and general features unless they contain a concrete hazard + locality."
        " Output strict JSON: {\"results\":[{title, link, domain, relevant:bool, category, reason, severity:int}]}"
        " where severity is 1 (info), 2 (watch), 3 (warning)."
    )

    user = (
        "Location: {location}\n\n"
        "Geo terms (hints): {geo_terms}\n\n"
        "Locality: city={city}, county={county}, state_code={state_code}\n\n"
        "Items:\n{items}"
    ).format(
        location=payload["location"],
        geo_terms=", ".join(payload["geo_terms"]),
        city=(payload["locality"].get("city") or ""),
        county=(payload["locality"].get("county") or ""),
        state_code=(payload["locality"].get("state_code") or ""),
        items=json.dumps(payload["items"], ensure_ascii=False),
    )

    content = _chat_json(system, user, model)
    try:
        parsed = json.loads(content or "{}")
    except json.JSONDecodeError:
        return [], {"used": True, "error": "invalid_json"}

    results = parsed.get("results") or []
    filtered: List[Dict[str, Any]] = []
    for src, res in zip(batch, results):
        try:
            if res.get("relevant") is True:
                tagged = dict(src)
                tagged["category"] = res.get("category") or "general"
                tagged["reason"] = res.get("reason") or ""
                tagged["severity"] = int(res.get("severity") or 1)
                filtered.append(tagged)
        except Exception:
            continue
    meta = {"used": True, "model": model, "input": len(batch), "kept": len(filtered)}
    return filtered, meta


def _chat_json(system: str, user: str, model: str) -> str:
    """Call OpenAI Chat API and return string content. Fallback across SDKs."""
    # Preferred path for openai>=1.x
    try:
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
    except Exception:
        pass

    # Fallback path for legacy openai<1.x
    try:
        import openai

        resp = openai.ChatCompletion.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp["choices"][0]["message"]["content"]
    except Exception:
        return ""
