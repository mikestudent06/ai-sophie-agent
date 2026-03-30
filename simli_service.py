"""
Session Simli (WebRTC) — clé API en x-simli-api-key, sans Basic D-ID.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

SIMLI_API_BASE = os.getenv("SIMLI_API_BASE", "https://api.simli.ai").rstrip("/")
SIMLI_API_KEY = os.getenv("SIMLI_API_KEY")
SIMLI_FACE_ID = os.getenv("SIMLI_FACE_ID", "tmp9i8bbq7c")


def _headers() -> dict[str, str]:
    if not SIMLI_API_KEY:
        raise ValueError("SIMLI_API_KEY manquant dans .env")
    return {
        "Content-Type": "application/json",
        "x-simli-api-key": SIMLI_API_KEY,
    }


def compose_token() -> tuple[int, dict[str, Any]]:
    url = f"{SIMLI_API_BASE}/compose/token"
    body: dict[str, Any] = {
        "faceId": SIMLI_FACE_ID,
        "apiVersion": "v2",
        "handleSilence": True,
        "maxSessionLength": 3600,
        "maxIdleTime": 300,
        "audioInputFormat": "pcm16",
    }
    r = requests.post(url, headers=_headers(), json=body, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def get_ice_servers() -> tuple[int, Any]:
    url = f"{SIMLI_API_BASE}/compose/ice"
    r = requests.get(url, headers=_headers(), timeout=30)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def get_session_bundle() -> dict[str, Any]:
    """Token + ICE pour le navigateur."""
    ts, td = compose_token()
    if ts >= 400:
        raise ValueError(td.get("detail", td) if isinstance(td, dict) else str(td))
    if not isinstance(td, dict) or "session_token" not in td:
        raise ValueError("Réponse compose/token invalide")

    ist, ice = get_ice_servers()
    if ist >= 400:
        raise ValueError(ice if not isinstance(ice, dict) else ice.get("detail", ice))

    return {"session_token": td["session_token"], "ice_servers": ice}
