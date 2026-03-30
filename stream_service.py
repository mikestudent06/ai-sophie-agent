"""
Proxy D-ID Talks/Clips Streams (WebRTC) — la clé API reste côté serveur.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from did_auth import did_headers_json

load_dotenv()

DID_API_BASE = os.getenv("DID_API_BASE", "https://api.d-id.com")
DID_STREAM_SERVICE = os.getenv("DID_STREAM_SERVICE", "talks").lower()


def did_headers() -> dict[str, str]:
    return did_headers_json()


def _service_path() -> str:
    return "clips" if DID_STREAM_SERVICE == "clips" else "talks"


def build_create_stream_body() -> dict[str, Any]:
    warmup = os.getenv("DID_STREAM_WARMUP", "true").lower() in ("1", "true", "yes")
    if DID_STREAM_SERVICE == "clips":
        return {
            "presenter_id": os.getenv(
                "DID_STREAM_PRESENTER_ID", "v2_public_alex@qcvo4gupoy"
            ),
            "driver_id": os.getenv("DID_STREAM_DRIVER_ID", "e3nbserss8"),
            "stream_warmup": warmup,
        }
    source = os.getenv("DID_STREAM_SOURCE_URL")
    if source:
        return {"source_url": source, "stream_warmup": warmup}
    pid = os.getenv("DID_STREAM_PRESENTER_ID")
    did = os.getenv("DID_STREAM_DRIVER_ID")
    if pid and did:
        return {"presenter_id": pid, "driver_id": did, "stream_warmup": warmup}
    return {
        "source_url": "https://create-images-results.d-id.com/DefaultPresenters/Emma_f/v1_image.jpeg",
        "stream_warmup": warmup,
    }


def create_stream() -> tuple[int, dict[str, Any]]:
    sp = _service_path()
    url = f"{DID_API_BASE}/{sp}/streams"
    r = requests.post(url, headers=did_headers(), json=build_create_stream_body(), timeout=120)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def post_sdp(stream_id: str, answer: dict[str, Any], session_id: str) -> tuple[int, dict[str, Any]]:
    sp = _service_path()
    url = f"{DID_API_BASE}/{sp}/streams/{stream_id}/sdp"
    r = requests.post(
        url,
        headers=did_headers(),
        json={"answer": answer, "session_id": session_id},
        timeout=120,
    )
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def post_ice(
    stream_id: str,
    session_id: str,
    candidate: Any | None,
    sdp_mid: str | None = None,
    sdp_mline_index: int | None = None,
) -> tuple[int, dict[str, Any]]:
    sp = _service_path()
    url = f"{DID_API_BASE}/{sp}/streams/{stream_id}/ice"
    payload: dict[str, Any] = {"session_id": session_id}
    if candidate is not None:
        payload["candidate"] = candidate
        if sdp_mid is not None:
            payload["sdpMid"] = sdp_mid
        if sdp_mline_index is not None:
            payload["sdpMLineIndex"] = sdp_mline_index
    r = requests.post(url, headers=did_headers(), json=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data




def interrupt_stream(stream_id: str, session_id: str) -> tuple[int, dict[str, Any]]:
    """Tente d arrêter la réplique en cours (barge-in)."""
    sp = _service_path()
    url = f"{DID_API_BASE}/{sp}/streams/{stream_id}/interrupt"
    r = requests.post(
        url, headers=did_headers(), json={"session_id": session_id}, timeout=30
    )
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data

def speak_stream(stream_id: str, session_id: str, text: str) -> tuple[int, dict[str, Any]]:
    sp = _service_path()
    if os.getenv("DID_INTERRUPT_BEFORE_SPEAK", "true").lower() in ("1", "true", "yes"):
        ist, _ = interrupt_stream(stream_id, session_id)
        if ist >= 400 and ist != 404:
            pass
    url = f"{DID_API_BASE}/{sp}/streams/{stream_id}"
    voice = os.getenv("DID_STREAM_VOICE_ID", "fr-FR-DeniseNeural")
    body: dict[str, Any] = {
        "script": {
            "type": "text",
            "subtitles": "false",
            "provider": {"type": "microsoft", "voice_id": voice},
            "ssml": "false",
            "input": text,
        },
        "config": {"stitch": True},
        "session_id": session_id,
    }
    if sp == "clips":
        body["background"] = {"color": "#FFFFFF"}
    r = requests.post(url, headers=did_headers(), json=body, timeout=120)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def delete_stream(stream_id: str, session_id: str) -> tuple[int, dict[str, Any]]:
    sp = _service_path()
    url = f"{DID_API_BASE}/{sp}/streams/{stream_id}"
    r = requests.delete(
        url, headers=did_headers(), json={"session_id": session_id}, timeout=60
    )
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text} if r.text else {}
    return r.status_code, data

