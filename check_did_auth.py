"""
Vérifie la construction du header Authorization D-ID sans afficher de secret.
Usage: python check_did_auth.py
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    key_set = bool((os.getenv("DID_API_KEY") or "").strip())
    base = os.getenv("DID_API_BASE", "https://api.d-id.com")
    print(f"DID_API_KEY défini: {key_set}")
    print(f"DID_API_BASE: {base}")

    if not key_set:
        print("Erreur: DID_API_KEY vide — impossible de construire Authorization.")
        raise SystemExit(1)

    from did_auth import did_authorization_value

    try:
        auth = did_authorization_value()
    except ValueError as e:
        print(f"Erreur: {e}")
        raise SystemExit(1)

    ok_basic = auth.startswith("Basic ")
    after = auth[6:] if ok_basic else auth
    print(f"Authorization commence par 'Basic ': {ok_basic}")
    print(f"Longueur totale de la valeur Authorization: {len(auth)} caractères")
    print(f"Longueur du segment après 'Basic ' (token): {len(after)} caractères")
    if not ok_basic:
        print(
            "ATTENTION: la valeur devrait commencer par 'Basic ' — "
            "l’API D-ID / AWS peut refuser la requête."
        )


if __name__ == "__main__":
    main()
