"""
Local LVM utilities — call a locally-running model server (Ollama)
==================================================================

This module is the bridge between the Streamlit app and a local
multimodal model (e.g. Qwen2.5-VL) served via Ollama on the
operator's own machine. Nothing in this module sends data anywhere
except `http://localhost:11434` (or whatever endpoint the operator
configures).

USAGE PATTERN — MANUAL FEEDBACK LOOP
------------------------------------
This module returns raw model output as a string. The operator reads
that output and decides what to put into the ingest form. There is
NO automatic field parsing — that decision was deliberate:

  1. Local-model outputs are not guaranteed to follow a strict
     schema, and silently mis-parsing them could create wrong
     metadata that then propagates downstream.
  2. The operator retains accountability for what gets registered.
     A human in the loop is required at the data-quality step.
  3. The same module works against any vision-capable Ollama model
     (Qwen2.5-VL, LLaVA, Llama 3.2 Vision, etc.) without needing
     model-specific parsers.

If you later want an automatic field parser, build it on top of
this module — but keep the manual path as a fallback.

DEPLOYMENT
----------
Ollama is NOT a dependency of the cloud-deployed app. The functions
here use `requests` (already pulled in by streamlit-folium) and only
talk to the configured endpoint when explicitly invoked. If no
Ollama server is reachable, `check_ollama_health()` returns False
and the UI shows a clear message — no crash.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5vl:7b"
DEFAULT_TIMEOUT_S = 120  # generous — local models can be slow on CPU


# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------
def check_ollama_health(
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 2.0,
) -> Tuple[bool, str]:
    """
    Quick health check. Returns (is_alive, message). Never raises.

    `message` is a short string suitable for st.info / st.warning.
    """
    try:
        resp = requests.get(f"{endpoint}/api/tags", timeout=timeout)
        if resp.status_code == 200:
            return True, f"Ollama reachable at {endpoint}."
        return False, (
            f"Ollama responded at {endpoint} but returned "
            f"HTTP {resp.status_code}."
        )
    except requests.exceptions.ConnectionError:
        return False, (
            f"No Ollama server reachable at {endpoint}. "
            f"Start Ollama on your local machine "
            f"(`ollama serve`) and try again."
        )
    except requests.exceptions.Timeout:
        return False, f"Ollama at {endpoint} timed out on health check."
    except Exception as exc:  # noqa: BLE001
        return False, f"Health check error: {exc}"


# -----------------------------------------------------------------------------
# List models available on the local server
# -----------------------------------------------------------------------------
def list_local_models(
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 5.0,
) -> List[str]:
    """Return the list of model names installed in the local Ollama."""
    try:
        resp = requests.get(f"{endpoint}/api/tags", timeout=timeout)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# -----------------------------------------------------------------------------
# Inference — images (vision-capable models)
# -----------------------------------------------------------------------------
def run_image_inference(
    image_bytes: bytes,
    prompt: str,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """
    Send an image plus a text prompt to a vision-capable Ollama model.

    Returns a dict:
        { "ok": bool, "text": str, "raw": Any, "error": Optional[str] }

    `text` is the model's free-form response. The caller decides
    what to do with it — no parsing is performed here.
    """
    if not image_bytes:
        return {"ok": False, "text": "", "raw": None,
                "error": "No image bytes supplied."}

    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [b64],
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{endpoint}/api/generate",
            json=payload, timeout=timeout,
        )
    except requests.exceptions.ConnectionError as exc:
        return {"ok": False, "text": "", "raw": None,
                "error": f"Cannot reach Ollama at {endpoint} — "
                         f"is the server running? ({exc})"}
    except requests.exceptions.Timeout:
        return {"ok": False, "text": "", "raw": None,
                "error": f"Ollama timed out after {timeout}s. "
                         f"Try a smaller model or a shorter prompt."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": "", "raw": None,
                "error": f"Inference error: {exc}"}

    if resp.status_code != 200:
        return {"ok": False, "text": "", "raw": resp.text,
                "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return {"ok": False, "text": "", "raw": resp.text,
                "error": "Ollama response was not valid JSON."}

    return {
        "ok": True,
        "text": data.get("response", "").strip(),
        "raw": data,
        "error": None,
    }


# -----------------------------------------------------------------------------
# Inference — text-only (plain Ollama models)
# -----------------------------------------------------------------------------
def run_text_inference(
    text: str,
    prompt_template: str,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """
    Send extracted text from an inspection report to a text-capable
    Ollama model. `prompt_template` should contain `{text}` where
    the report content goes.
    """
    if not text:
        return {"ok": False, "text": "", "raw": None,
                "error": "No text supplied."}

    payload = {
        "model": model,
        "prompt": prompt_template.format(text=text),
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{endpoint}/api/generate",
            json=payload, timeout=timeout,
        )
    except requests.exceptions.ConnectionError as exc:
        return {"ok": False, "text": "", "raw": None,
                "error": f"Cannot reach Ollama at {endpoint} ({exc})"}
    except requests.exceptions.Timeout:
        return {"ok": False, "text": "", "raw": None,
                "error": f"Timed out after {timeout}s."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": "", "raw": None,
                "error": f"Inference error: {exc}"}

    if resp.status_code != 200:
        return {"ok": False, "text": "", "raw": resp.text,
                "error": f"HTTP {resp.status_code}"}

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return {"ok": False, "text": "", "raw": resp.text,
                "error": "Response was not valid JSON."}

    return {
        "ok": True,
        "text": data.get("response", "").strip(),
        "raw": data,
        "error": None,
    }


# -----------------------------------------------------------------------------
# Suggested prompts — usable defaults the operator can customise
# -----------------------------------------------------------------------------
DEFAULT_IMAGE_PROMPT = (
    "You are a tunnel-inspection assistant analysing a single "
    "photograph of a road-tunnel lining. Look at the image and "
    "describe ONLY what you can directly observe. Cover:\n"
    "1. Defect type (crack, spall, leak, staining, void, "
    "delamination, joint failure, other)\n"
    "2. Approximate position on the tunnel cross-section "
    "(crown / springline-left / springline-right / sidewall-left / "
    "sidewall-right / invert) — only if visible in the image\n"
    "3. Approximate size (crack width in mm, spall depth in mm, "
    "affected area in cm² — give a coarse estimate)\n"
    "4. Severity hint (low / medium / high) and your reasoning\n"
    "5. Anything visible that suggests active vs dormant "
    "(moisture, salt staining, rust, growth)\n"
    "Do NOT invent measurements you cannot infer from the image. "
    "If something is not visible, say so."
)

DEFAULT_TEXT_PROMPT = (
    "Read the following tunnel inspection report excerpt and extract:\n"
    "1. Defect type\n"
    "2. Location (ring number and chainage in metres if mentioned)\n"
    "3. Quantitative measurements (crack width, spall depth, area)\n"
    "4. Position on tunnel cross-section if specified\n"
    "5. Severity\n\n"
    "Report excerpt:\n---\n{text}\n---\n\n"
    "Respond as a short structured list. Do NOT invent values that "
    "aren't in the text."
)
