import os
import requests
import time
from dotenv import load_dotenv
import asyncio

from did_auth import did_authorization_value

load_dotenv()

# --- HeyGen : uniquement pour les routes proxy /heygen/* dans main.py ---
HEYGEN_BASE = "https://api.heygen.com"
HEYGEN_AVATARS_URL = f"{HEYGEN_BASE}/v2/avatars"
HEYGEN_VOICES_URL = f"{HEYGEN_BASE}/v2/voices"
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")


def heygen_headers() -> dict:
    return {
        "X-Api-Key": HEYGEN_API_KEY or "",
        "Content-Type": "application/json",
    }


def fetch_heygen_avatars():
    if not HEYGEN_API_KEY:
        raise ValueError("HEYGEN_API_KEY manquant dans l'environnement (.env)")
    return requests.get(HEYGEN_AVATARS_URL, headers=heygen_headers(), timeout=60)


def fetch_heygen_voices():
    if not HEYGEN_API_KEY:
        raise ValueError("HEYGEN_API_KEY manquant dans l'environnement (.env)")
    return requests.get(HEYGEN_VOICES_URL, headers=heygen_headers(), timeout=120)


# --- D-ID : génération vidéo pour Sophie (ask-full-avatar) ---
DID_URL = "https://api.d-id.com/talks"


async def generate_sophie_video(text: str):
    try:
        headers = {
            "Authorization": did_authorization_value(),
            "Content-Type": "application/json",
        }
    except ValueError:
        return "Erreur : Clé DID_API_KEY manquante."

    data = {
        "script": {
            "type": "text",
            "subtitles": "false",
            "provider": {
                "type": "microsoft",
                "voice_id": "fr-FR-DeniseNeural",
            },
            "ssml": "false",
            "input": text,
        },
        "config": {
            "fluent": "false",
            "pad_audio": "0.0",
        },
        "presenter_id": "dani-j_Lp64_D6q",
        "driver_id": "mX7X8s64_D6q",
    }

    response = requests.post(DID_URL, headers=headers, json=data, timeout=120)

    if not response.ok:
        return f"Erreur D-ID ({response.status_code}): {response.text}"

    talk_id = response.json().get("id")
    print(f"Vidéo D-ID lancée ! ID: {talk_id}")

    status_url = f"{DID_URL}/{talk_id}"
    max_polls = 200

    for _ in range(max_polls):
        res = requests.get(status_url, headers=headers, timeout=60)
        status_data = res.json()
        status = status_data.get("status")

        print(f"Statut D-ID : {status}")

        # D-ID renvoie "done" quand c'est prêt (pas "completed")
        if status in ("done", "completed"):
            result_url = status_data.get("result_url")
            if result_url:
                return result_url
            # Parfois "done" avant que result_url soit rempli — on repolle
        if status in ("error", "rejected"):
            return "Échec de la génération chez D-ID."

        await asyncio.sleep(3)

    return "Délai dépassé en attendant la vidéo D-ID."