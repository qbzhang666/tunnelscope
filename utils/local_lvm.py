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
import io
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5vl:7b"
# Text model used for auto-extracting fields from inspection REPORTS.
# Any locally-installed instruct model works; this is a sensible default.
DEFAULT_TEXT_CLASSIFY_MODEL = "qwen3:8b"
DEFAULT_TIMEOUT_S = 300  # first call cold-starts the model; be generous
# Keep the model resident between calls so only the FIRST classification in a
# session pays the multi-GB load cost; later photos/reports are much faster.
DEFAULT_KEEP_ALIVE = "30m"
# Cap generated tokens: the reply is a small JSON object (or a short raw
# description), so this bounds runaway generation without truncating output.
DEFAULT_NUM_PREDICT = 768


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
        "keep_alive": DEFAULT_KEEP_ALIVE,
        "options": {"num_predict": DEFAULT_NUM_PREDICT},
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
                "error": f"Ollama timed out after {timeout:.0f}s. The first "
                         f"run loads the model into memory and is the "
                         f"slowest — click again to retry on the now-warm "
                         f"model, raise the timeout in the config panel, or "
                         f"pull a smaller vision model (e.g. qwen2.5vl:3b, "
                         f"moondream)."}
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
        "keep_alive": DEFAULT_KEEP_ALIVE,
        "options": {"num_predict": DEFAULT_NUM_PREDICT},
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


# =============================================================================
# Automatic defect recognition — parse model output into the ingest form
# =============================================================================
# Unlike the manual functions above, these prompt the model for STRICT JSON
# and parse it into the exact field values the ingest form expects, so the
# form can be pre-filled automatically. A human still confirms before
# registering — the model's output is a suggestion, never the final record.

# Canonical option values (must match utils.ingest DEFECT_TYPE_OPTIONS /
# POSITION_OPTIONS). Kept here so this module stays import-decoupled.
_ALLOWED_DEFECT_TYPES = [
    "Cracks", "Spalls", "LeakingJoints", "Efflorescence", "RebarCorrosion",
    "Delamination", "Honeycombing", "ConstructionJointDefect", "Unclassified",
]
_ALLOWED_POSITIONS = [
    "Crown", "Springline_L", "Springline_R", "Invert",
    "Sidewall_L", "Sidewall_R",
]

CLASSIFY_IMAGE_PROMPT = (
    "You are a tunnel-lining inspection assistant. Look at this single "
    "photograph and classify the most prominent defect. Respond with ONLY "
    "a JSON object — no markdown fences, no commentary — using EXACTLY "
    "these keys:\n"
    '{"defect_type": one of '
    '["Cracks","Spalls","LeakingJoints","Efflorescence","RebarCorrosion",'
    '"Delamination","Honeycombing","ConstructionJointDefect","Unclassified"], '
    '"position": one of '
    '["Crown","Springline_L","Springline_R","Invert","Sidewall_L",'
    '"Sidewall_R","Unknown"], '
    '"severity": one of ["low","medium","high"], '
    '"moisture": one of ["dry","damp","wet","active_leak"], '
    '"crack_width_mm": number or null, '
    '"spall_depth_mm": number or null, '
    '"area_cm2": number or null, '
    '"confidence": number between 0 and 1, '
    '"reasoning": one short sentence citing what you see}\n'
    "Report ONLY what is visible. Use null for any measurement you cannot "
    "estimate. Do not invent numbers."
)

CLASSIFY_TEXT_PROMPT = (
    "You extract structured data from tunnel inspection reports. From the "
    "report below, return ONLY a JSON object (no commentary) with EXACTLY "
    "these keys:\n"
    '{"defect_type": one of '
    '["Cracks","Spalls","LeakingJoints","Efflorescence","RebarCorrosion",'
    '"Delamination","Honeycombing","ConstructionJointDefect","Unclassified"], '
    '"position": one of '
    '["Crown","Springline_L","Springline_R","Invert","Sidewall_L",'
    '"Sidewall_R","Unknown"], '
    '"ring_id": integer or null, '
    '"chainage_m": number or null, '
    '"severity": one of ["low","medium","high"], '
    '"moisture": one of ["dry","damp","wet","active_leak"], '
    '"crack_width_mm": number or null, '
    '"spall_depth_mm": number or null, '
    '"area_cm2": number or null, '
    '"confidence": number between 0 and 1, '
    '"reasoning": one short sentence}\n'
    "Use null for anything the report does not state. Do NOT invent values.\n"
    "Report:\n---\n{text}\n---"
)


def _downscale_image(image_bytes: bytes, max_px: int = 1024,
                     quality: int = 85) -> bytes:
    """Shrink a large inspection photo before sending it to the model.

    Vision models do not need 20+ megapixels; downscaling cuts inference
    time and request size by an order of magnitude (a 22 MB JPEG becomes a
    few hundred KB). Returns the original bytes unchanged on any failure.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((max_px, max_px))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality)
        return out.getvalue()
    except Exception:
        return image_bytes


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response that may be
    wrapped in ```json fences, padded with prose, or preceded by a
    reasoning model's <think>…</think> block."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start:end + 1]
    if candidate is None:
        return None
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _norm_key(s: Any) -> str:
    return re.sub(r"[\s_\-]+", "", str(s or "").strip().lower())


_DEFECT_ALIASES = {
    "crack": "Cracks", "cracks": "Cracks", "cracking": "Cracks",
    "spall": "Spalls", "spalls": "Spalls", "spalling": "Spalls",
    "leak": "LeakingJoints", "leakage": "LeakingJoints",
    "leakingjoint": "LeakingJoints", "leakingjoints": "LeakingJoints",
    "efflorescence": "Efflorescence", "staining": "Efflorescence",
    "stain": "Efflorescence", "stains": "Efflorescence",
    "rebarcorrosion": "RebarCorrosion", "corrosion": "RebarCorrosion",
    "rust": "RebarCorrosion", "rebar": "RebarCorrosion",
    "delamination": "Delamination", "delaminations": "Delamination",
    "delam": "Delamination",
    "honeycombing": "Honeycombing", "honeycomb": "Honeycombing",
    "constructionjointdefect": "ConstructionJointDefect",
    "constructionjoint": "ConstructionJointDefect",
    "jointdefect": "ConstructionJointDefect",
    "unclassified": "Unclassified", "other": "Unclassified",
    "none": "Unclassified", "unknown": "Unclassified",
}

_POSITION_ALIASES = {
    "crown": "Crown", "top": "Crown", "soffit": "Crown",
    "invert": "Invert", "bottom": "Invert", "floor": "Invert",
    "springlinel": "Springline_L", "springlineleft": "Springline_L",
    "leftspringline": "Springline_L",
    "springliner": "Springline_R", "springlineright": "Springline_R",
    "rightspringline": "Springline_R",
    "sidewalll": "Sidewall_L", "leftsidewall": "Sidewall_L",
    "sidewallleft": "Sidewall_L", "left": "Sidewall_L",
    "sidewallr": "Sidewall_R", "rightsidewall": "Sidewall_R",
    "sidewallright": "Sidewall_R", "right": "Sidewall_R",
}


def _to_pos_float(v: Any) -> Optional[float]:
    """Coerce to a positive float, else None (treats 0/negatives as absent)."""
    try:
        if v is None:
            return None
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def _map_classification(parsed: dict) -> Dict[str, Any]:
    """Map a parsed model JSON object onto the ingest form's field values.

    `defect_type` always lands on a valid form option; `position` is None
    when not recognised (the form then keeps its default). Priority follows
    a transparent rule from severity + moisture.
    """
    defect_type = _DEFECT_ALIASES.get(
        _norm_key(parsed.get("defect_type")), "Unclassified")
    position = _POSITION_ALIASES.get(_norm_key(parsed.get("position")))

    severity = str(parsed.get("severity", "")).strip().lower() or None
    moisture = str(parsed.get("moisture", "")).strip().lower() or None
    if moisture == "active_leak" or severity == "high":
        priority = "HIGH"
    elif severity == "medium" or moisture in ("wet", "damp"):
        priority = "MEDIUM"
    else:
        priority = "LOW"

    conf = _to_pos_float(parsed.get("confidence"))
    if conf is not None and conf > 1:        # tolerate a 0–100 scale
        conf = min(conf / 100.0, 1.0)

    return {
        "defect_type": defect_type,
        "position": position if position in _ALLOWED_POSITIONS else None,
        "severity": severity,
        "moisture": moisture,
        "priority": priority,
        "ring_id": _to_int(parsed.get("ring_id")),
        "chainage_m": _to_pos_float(parsed.get("chainage_m")),
        "crack_width_mm": _to_pos_float(parsed.get("crack_width_mm")),
        "spall_depth_mm": _to_pos_float(parsed.get("spall_depth_mm")),
        "area_cm2": _to_pos_float(parsed.get("area_cm2")),
        "confidence": conf,
        "reasoning": str(parsed.get("reasoning", "")).strip(),
    }


def _ollama_generate(prompt: str, model: str, endpoint: str,
                     timeout: float) -> Dict[str, Any]:
    """Low-level /api/generate call that sends the prompt verbatim (no
    str.format), so prompts containing literal JSON braces are safe."""
    payload = {"model": model, "prompt": prompt, "stream": False,
               "keep_alive": DEFAULT_KEEP_ALIVE,
               "options": {"num_predict": DEFAULT_NUM_PREDICT}}
    try:
        resp = requests.post(f"{endpoint}/api/generate",
                             json=payload, timeout=timeout)
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
                "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return {"ok": False, "text": "", "raw": resp.text,
                "error": "Response was not valid JSON."}
    return {"ok": True, "text": data.get("response", "").strip(),
            "raw": data, "error": None}


def classify_defect_image(
    image_bytes: bytes,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Recognise a defect in an inspection photo via a local vision model.

    The image is downscaled, sent with a strict-JSON prompt, and the reply
    parsed into ready-to-use form fields. A human must still confirm before
    registering. Returns:
        {ok, fields{...}, confidence, reasoning, raw, error}
    """
    if not image_bytes:
        return {"ok": False, "error": "No image supplied.",
                "fields": {}, "raw": ""}

    inference = run_image_inference(
        _downscale_image(image_bytes), CLASSIFY_IMAGE_PROMPT,
        model, endpoint, timeout)
    if not inference["ok"]:
        return {"ok": False, "error": inference["error"],
                "fields": {}, "raw": inference.get("raw")}

    parsed = _extract_json(inference["text"])
    if parsed is None:
        return {"ok": False, "fields": {}, "raw": inference["text"],
                "error": "The model did not return parseable JSON — read "
                         "its raw output below and fill the form manually."}

    fields = _map_classification(parsed)
    return {"ok": True, "fields": fields,
            "confidence": fields["confidence"],
            "reasoning": fields["reasoning"],
            "raw": inference["text"], "error": None}


def classify_defect_text(
    text: str,
    model: str = DEFAULT_TEXT_CLASSIFY_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Extract structured defect fields from an inspection report via a
    local text model. Same return shape as classify_defect_image."""
    if not text or not text.strip():
        return {"ok": False, "error": "No report text supplied.",
                "fields": {}, "raw": ""}

    inference = _ollama_generate(
        CLASSIFY_TEXT_PROMPT.replace("{text}", text), model, endpoint, timeout)
    if not inference["ok"]:
        return {"ok": False, "error": inference["error"],
                "fields": {}, "raw": inference.get("raw")}

    parsed = _extract_json(inference["text"])
    if parsed is None:
        return {"ok": False, "fields": {}, "raw": inference["text"],
                "error": "The model did not return parseable JSON — read "
                         "its raw output below and fill the form manually."}

    fields = _map_classification(parsed)
    return {"ok": True, "fields": fields,
            "confidence": fields["confidence"],
            "reasoning": fields["reasoning"],
            "raw": inference["text"], "error": None}


def list_vision_models(endpoint: str = DEFAULT_ENDPOINT) -> List[str]:
    """Locally-installed models that can probably see images (name heuristic:
    vl / llava / vision / moondream / minicpm-v / bakllava / gemma3)."""
    hints = ("vl", "llava", "vision", "moondream", "minicpm-v",
             "bakllava", "gemma3")
    return [m for m in list_local_models(endpoint)
            if any(h in m.lower() for h in hints)]
