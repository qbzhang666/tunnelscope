"""
Cloud VLM — defect recognition via hosted Vision-Language model APIs
====================================================================

For operators who don't run a local Ollama/GPU. Sends the inspection
photo or report to a hosted Vision-Language model and parses the reply
into the same ingest-form fields the local path produces — so the form
is pre-filled for human review either way.

Providers
---------
- **Anthropic Claude** via the official `anthropic` SDK (Messages API,
  base64 image block). Default model `claude-opus-4-8`.
- **OpenAI** via HTTP (`/v1/chat/completions`, `image_url` data URI).
- **Google Gemini** via HTTP (`generateContent`, `inline_data`).

The JSON extraction and field mapping are reused from `local_lvm`, so
a cloud classification maps onto the form exactly like a local one.

API KEYS
--------
Keys are NEVER hard-coded or committed. They are read from Streamlit
secrets (`.streamlit/secrets.toml`, git-ignored) or the environment,
or pasted into the UI for the session only. One key per provider:

    ANTHROPIC_API_KEY · OPENAI_API_KEY · GEMINI_API_KEY (or GOOGLE_API_KEY)
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

import requests

from utils.local_lvm import (
    _downscale_image, _extract_json, _map_classification,
    CLASSIFY_IMAGE_PROMPT, CLASSIFY_TEXT_PROMPT,
)

PROVIDERS = ["Anthropic Claude", "OpenAI", "Google Gemini"]

# Sensible current defaults; all are editable in the UI so the operator
# can point at a newer/cheaper model without a code change.
DEFAULT_MODELS = {
    "Anthropic Claude": "claude-opus-4-8",
    "OpenAI": "gpt-4o",
    "Google Gemini": "gemini-2.0-flash",
}

# Environment-variable names checked per provider (also looked up in
# st.secrets by the page).
KEY_ENV_NAMES = {
    "Anthropic Claude": ["ANTHROPIC_API_KEY"],
    "OpenAI": ["OPENAI_API_KEY"],
    "Google Gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
}

TIMEOUT_S = 90
MAX_TOKENS = 2048  # the reply is a small JSON object


def api_key_from_env(provider: str) -> Optional[str]:
    """Return the provider's key from the environment, or None."""
    for name in KEY_ENV_NAMES.get(provider, []):
        if os.environ.get(name):
            return os.environ[name]
    return None


# -----------------------------------------------------------------------------
# Per-provider calls — each returns {"ok": bool, "text": str, "error": str|None}
# -----------------------------------------------------------------------------
def _call_claude(prompt: str, image_b64: Optional[str], model: str,
                 api_key: str) -> Dict[str, Any]:
    import anthropic  # official SDK (per Claude API guidance)
    client = anthropic.Anthropic(api_key=api_key)
    content: List[Dict[str, Any]] = []
    if image_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": image_b64},
        })
    content.append({"type": "text", "text": prompt})
    msg = client.messages.create(
        model=model, max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    return {"ok": True, "text": text, "error": None}


def _call_openai(prompt: str, image_b64: Optional[str], model: str,
                 api_key: str) -> Dict[str, Any]:
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    if image_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
        })
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={"model": model, "max_tokens": MAX_TOKENS,
              "messages": [{"role": "user", "content": content}]},
        timeout=TIMEOUT_S,
    )
    if resp.status_code != 200:
        return {"ok": False, "text": "",
                "error": f"OpenAI HTTP {resp.status_code}: {resp.text[:300]}"}
    data = resp.json()
    return {"ok": True,
            "text": data["choices"][0]["message"]["content"].strip(),
            "error": None}


def _call_gemini(prompt: str, image_b64: Optional[str], model: str,
                 api_key: str) -> Dict[str, Any]:
    parts: List[Dict[str, Any]] = [{"text": prompt}]
    if image_b64:
        parts.append({"inline_data": {"mime_type": "image/jpeg",
                                      "data": image_b64}})
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key}")
    resp = requests.post(url, json={"contents": [{"parts": parts}]},
                        timeout=TIMEOUT_S)
    if resp.status_code != 200:
        return {"ok": False, "text": "",
                "error": f"Gemini HTTP {resp.status_code}: {resp.text[:300]}"}
    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return {"ok": False, "text": "",
                "error": f"Gemini returned no content: {str(data)[:300]}"}
    return {"ok": True, "text": text.strip(), "error": None}


def _dispatch(provider: str, prompt: str, image_b64: Optional[str],
              model: str, api_key: str) -> Dict[str, Any]:
    """Route to the provider, turning every failure mode into a message."""
    try:
        if provider == "Anthropic Claude":
            return _call_claude(prompt, image_b64, model, api_key)
        if provider == "OpenAI":
            return _call_openai(prompt, image_b64, model, api_key)
        if provider == "Google Gemini":
            return _call_gemini(prompt, image_b64, model, api_key)
        return {"ok": False, "text": "", "error": f"Unknown provider {provider}"}
    except ImportError:
        return {"ok": False, "text": "",
                "error": "The 'anthropic' package is not installed — run "
                         "`pip install anthropic` (it is in requirements.txt)."}
    except requests.exceptions.Timeout:
        return {"ok": False, "text": "", "error": f"{provider} timed out "
                f"after {TIMEOUT_S}s."}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "text": "", "error": f"Cannot reach {provider} — "
                "check your internet connection."}
    except Exception as exc:  # noqa: BLE001 (surface auth/quota/etc. cleanly)
        return {"ok": False, "text": "", "error": f"{provider} error: {exc}"}


# -----------------------------------------------------------------------------
# Public classify functions — same return shape as the local_lvm versions
# -----------------------------------------------------------------------------
def classify_defect_image_cloud(
    image_bytes: bytes, provider: str, api_key: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Recognise a defect in a photo via a hosted VLM. Returns
    {ok, fields{...}, confidence, reasoning, raw, error}."""
    if not api_key:
        return {"ok": False, "error": "No API key provided.",
                "fields": {}, "raw": ""}
    if not image_bytes:
        return {"ok": False, "error": "No image supplied.",
                "fields": {}, "raw": ""}
    model = model or DEFAULT_MODELS.get(provider, "")
    b64 = base64.standard_b64encode(_downscale_image(image_bytes)).decode("ascii")
    out = _dispatch(provider, CLASSIFY_IMAGE_PROMPT, b64, model, api_key)
    return _finish(out)


def classify_defect_text_cloud(
    text: str, provider: str, api_key: str, model: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract defect fields from an inspection report via a hosted model."""
    if not api_key:
        return {"ok": False, "error": "No API key provided.",
                "fields": {}, "raw": ""}
    if not text or not text.strip():
        return {"ok": False, "error": "No report text supplied.",
                "fields": {}, "raw": ""}
    model = model or DEFAULT_MODELS.get(provider, "")
    prompt = CLASSIFY_TEXT_PROMPT.replace("{text}", text)
    out = _dispatch(provider, prompt, None, model, api_key)
    return _finish(out)


def _finish(out: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a provider reply into mapped form fields."""
    if not out["ok"]:
        return {"ok": False, "error": out["error"], "fields": {},
                "raw": out.get("text")}
    parsed = _extract_json(out["text"])
    if parsed is None:
        return {"ok": False, "fields": {}, "raw": out["text"],
                "error": "The model did not return parseable JSON — read its "
                         "raw output below and fill the form manually."}
    fields = _map_classification(parsed)
    return {"ok": True, "fields": fields, "confidence": fields["confidence"],
            "reasoning": fields["reasoning"], "raw": out["text"], "error": None}
