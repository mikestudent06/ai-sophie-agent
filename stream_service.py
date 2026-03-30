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

# Présentatrice D-ID par défaut (talks + source_url) — plus sobre / « corporate » que Emma_f.
DID_DEFAULT_STREAM_SOURCE_URL = os.getenv(
    "DID_DEFAULT_STREAM_SOURCE_URL",
    "https://create-images-results.d-id.com/DefaultPresenters/Noelle_f/v1_image.jpeg",
)


def did_headers() -> dict[str, str]:
    return did_headers_json()


def _alb_cookie_from_session(session_id: str) -> dict[str, str]:
    """
    Quand D-ID renvoie session_id avec des cookies ALB (AWSALB=…), les repasser en en-tête
    Cookie peut être nécessaire pour que certaines routes (ex. interrupt) atteignent le bon nœud.
    """
    if not session_id or "AWSALB=" not in session_id:
        return {}
    pairs: list[str] = []
    for segment in session_id.split(";"):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        low = segment.split("=", 1)[0].strip().lower()
        if low in (
            "path",
            "expires",
            "max-age",
            "domain",
            "secure",
            "httponly",
            "samesite",
        ):
            continue
        pairs.append(segment.strip())
    if not pairs:
        return {}
    return {"Cookie": "; ".join(pairs)}


def stream_headers(session_id: str | None = None) -> dict[str, str]:
    h = did_headers_json()
    if session_id:
        h.update(_alb_cookie_from_session(session_id))
    return h


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
        "source_url": DID_DEFAULT_STREAM_SOURCE_URL,
        "stream_warmup": warmup,
    }


def idle_poster_url() -> str:
    """
    Image affichée côté client en poster= sur <video> tant que WebRTC n a pas encore de frame
    (souvent seulement après le 1er speak). Même logique visuelle que build_create_stream_body.
    """
    override = (os.getenv("DID_STREAM_IDLE_POSTER_URL") or "").strip()
    if override:
        return override
    if DID_STREAM_SERVICE == "clips":
        return DID_DEFAULT_STREAM_SOURCE_URL
    source = os.getenv("DID_STREAM_SOURCE_URL")
    if source:
        return source
    pid = os.getenv("DID_STREAM_PRESENTER_ID")
    did = os.getenv("DID_STREAM_DRIVER_ID")
    if pid and did:
        return DID_DEFAULT_STREAM_SOURCE_URL
    return DID_DEFAULT_STREAM_SOURCE_URL


def warmup_text() -> str:
    """
    Texte très court utilisé pour « réveiller » le flux vidéo dès que le stream
    est prêt, avant la première vraie question utilisateur.
    """
    return os.getenv(
        "DID_STREAM_WARMUP_TEXT",
        "Bonjour, je suis Sophie.",
    )


def create_stream() -> tuple[int, dict[str, Any]]:
    sp = _service_path()
    url = f"{DID_API_BASE}/{sp}/streams"
    r = requests.post(url, headers=stream_headers(), json=build_create_stream_body(), timeout=120)
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
        headers=stream_headers(session_id),
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
    r = requests.post(url, headers=stream_headers(session_id), json=payload, timeout=60)
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
        url, headers=stream_headers(session_id), json={"session_id": session_id}, timeout=30
    )
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def warmup_stream(stream_id: str, session_id: str) -> tuple[int, dict[str, Any]]:
    """
    Envoie une courte réplique de warmup pour forcer D-ID à commencer à pousser des
    frames vidéo WebRTC, même avant la première demande utilisateur.
    """
    return speak_stream(stream_id, session_id, warmup_text())


def speak_stream(stream_id: str, session_id: str, text: str) -> tuple[int, dict[str, Any]]:
    sp = _service_path()
    if os.getenv("DID_INTERRUPT_BEFORE_SPEAK", "true").lower() in ("1", "true", "yes"):
        ist, _ = interrupt_stream(stream_id, session_id)
        if ist >= 400 and ist != 404:
            pass
    url = f"{DID_API_BASE}/{sp}/streams/{stream_id}"
    voice = os.getenv("DID_STREAM_VOICE_ID", "fr-FR-DeniseNeural")
    stitch = os.getenv("DID_STREAM_STITCH", "true").lower() in ("1", "true", "yes")
    body: dict[str, Any] = {
        "script": {
            "type": "text",
            "subtitles": "false",
            "provider": {"type": "microsoft", "voice_id": voice},
            "ssml": "false",
            "input": text,
        },
        "config": {"stitch": stitch},
        "session_id": session_id,
    }
    if sp == "clips":
        body["background"] = {"color": "#FFFFFF"}
    r = requests.post(url, headers=stream_headers(session_id), json=body, timeout=120)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def delete_stream(stream_id: str, session_id: str) -> tuple[int, dict[str, Any]]:
    sp = _service_path()
    url = f"{DID_API_BASE}/{sp}/streams/{stream_id}"
    r = requests.delete(
        url, headers=stream_headers(session_id), json={"session_id": session_id}, timeout=60
    )
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text} if r.text else {}
    return r.status_code, data

