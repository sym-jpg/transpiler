import os
import json
import requests
import time
from pathlib import Path
from typing import Any, Dict


def _load_local_env() -> None:
    """Load local LLM env vars without requiring an extra dotenv dependency."""
    for path in (Path(".env.local"), Path(".env")):
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _extract_output_text(data: Dict[str, Any]) -> str:
    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    parts: list[str] = []
    for item in data.get("output", []) or []:
        for c in item.get("content", []) or []:
            ctype = c.get("type")
            if ctype in ("output_text", "text"):
                t = c.get("text")
                if isinstance(t, str):
                    parts.append(t)
    return "".join(parts).strip()


def llm_chat_json(prompt: str) -> Dict[str, Any]:
    _load_local_env()
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "").strip()

    if not base or not key or not model:
        raise RuntimeError("Missing env: LLM_BASE_URL / LLM_API_KEY / LLM_MODEL")

    url = f"{base}/responses"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": "You are a code generator. Output ONLY valid JSON.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }

    last_exc: Exception | None = None
    r = None
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            break
        except requests.RequestException as e:
            last_exc = e
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

    if r is None:
        raise RuntimeError(f"LLM request failed before response: {last_exc}")

    if not (200 <= r.status_code < 300):
        try:
            err = r.json().get("error")
        except Exception:
            err = r.text
        raise RuntimeError(
            f"LLM request failed (status={r.status_code}, model={model}). error={err}"
        )

    try:
        data: Dict[str, Any] = r.json()
    except Exception as e:
        raise RuntimeError(
            f"LLM returned non-JSON response (status={r.status_code}, model={model}). body={r.text[:400]}"
        ) from e

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(
            f"LLM request failed (status={r.status_code}, model={model}). error={data.get('error')}"
        )

    content = _extract_output_text(data)
    if not content:
        raise RuntimeError(
            f"LLM returned empty output (status={r.status_code}, model={model}). body={json.dumps(data)[:400]}"
        )

    try:
        return json.loads(content)
    except Exception as e:
        raise RuntimeError(
            f"LLM did not return valid JSON (model={model}). content={content[:400]}"
        ) from e
