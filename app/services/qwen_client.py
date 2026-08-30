"""Qwen (DashScope OpenAI-compatible) client. Never writes schedule cells."""
import json
import logging

import httpx

from app.config import Config

log = logging.getLogger(__name__)

_TIMEOUT = 12.0


def qwen_configured() -> bool:
    return bool((Config.QWEN_API_KEY or "").strip())


def phrase_for_scheduler(user_payload: str, *, system: str) -> str | None:
    """
    Ask Qwen to rewrite *facts* as short Russian text.
    Returns None if the model is not configured or the call fails.
    """
    key = (Config.QWEN_API_KEY or "").strip()
    if not key:
        return None
    url = Config.QWEN_BASE_URL.rstrip("/") + "/chat/completions"
    body = {
        "model": Config.QWEN_MODEL,
        "temperature": 0.2,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_payload},
        ],
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            res = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if res.status_code >= 400:
            log.warning("Qwen HTTP %s: %s", res.status_code, res.text[:300])
            return None
        data = res.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if isinstance(text, str) and text.strip():
            return text.strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("Qwen call failed: %s", exc)
    return None


def complete_json(user_payload: str, *, system: str) -> dict | None:
    """Ask Qwen for a JSON object. Returns None if unset, invalid, or the call fails."""
    raw = phrase_for_scheduler(user_payload, system=system)
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(inner)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            log.warning("Qwen JSON parse failed: %s", text[:200])
            return None
    return data if isinstance(data, dict) else None
