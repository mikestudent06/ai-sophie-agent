"""
En-tête Authorization Basic pour l'API D-ID (RFC 7617).
La clé Studio est au format API_USERNAME:API_PASSWORD ; elle doit être encodée en Base64.

Sans « : » dans la variable : soit un segment Base64 déjà calculé pour user:pass (décodage UTF-8
contient « : »), soit une clé / secret seul — D-ID attend alors base64(f"{secret}:").
"""
from __future__ import annotations

import base64
import os
import re

from dotenv import load_dotenv

load_dotenv()


def _try_preencoded_user_pass(raw: str) -> str | None:
    """
    Si raw est le Base64 de « user:pass », renvoie la valeur Authorization complète.
    Sinon None (évite d'envoyer un blob binaire pris pour du Base64 valide).
    """
    raw = raw.strip()
    if not raw or ":" in raw:
        return None
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", raw):
        return None
    try:
        pad = len(raw) % 4
        padded = raw + ("=" * ((4 - pad) % 4))
        decoded = base64.b64decode(padded, validate=True)
        text = decoded.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in text:
        return None
    return f"Basic {raw}"


def did_authorization_value() -> str:
    """
    Valeur complète du header Authorization, ex. 'Basic xxxxx'.
    """
    raw = (os.getenv("DID_API_KEY") or "").strip()
    if not raw:
        raise ValueError("DID_API_KEY manquant dans .env")
    low = raw.lower()
    if low.startswith("basic "):
        return raw if raw.startswith("Basic ") else "Basic " + raw[6:].strip()

    if ":" in raw:
        token = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    pre = _try_preencoded_user_pass(raw)
    if pre is not None:
        return pre

    # Clé seule (sans « : ») : convention D-ID / outils — base64(secret + ":")
    token = base64.b64encode(f"{raw}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def did_headers_json() -> dict[str, str]:
    return {
        "Authorization": did_authorization_value(),
        "Content-Type": "application/json",
    }
