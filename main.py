from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from brain import sophie_brain # On importe le cerveau qu'on vient de tester
import shutil # Pour manipuler les fichiers
from fastapi import UploadFile, File # Pour recevoir des fichiers audio
from voice_service import transcribe_audio, generate_speech # Nos outils de voix
import os
from video_service import generate_sophie_video, fetch_heygen_avatars, fetch_heygen_voices

# 1. Créer l'application FastAPI
app = FastAPI(title="Sophie AI - Financial Advisor")

# --- NOUVEAU : La mémoire de Sophie ---
# On crée un dictionnaire pour stocker l'historique des discussions
# Structure : {"user_1": [historique], "user_2": [historique]}
chat_histories = {}

# 2. Définir le format de la question que le client doit envoyer (Schéma Pro)
class ChatRequest(BaseModel):
    user_id: str
    message: str


@app.get("/heygen/avatars")
async def heygen_list_avatars():
    """
    Proxy vers l'API HeyGen `GET https://api.heygen.com/v2/avatars` avec ta clé `.env`.
    À tester comme Postman : `GET http://127.0.0.1:8000/heygen/avatars`
    """
    try:
        r = fetch_heygen_avatars()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text}
    return JSONResponse(status_code=r.status_code, content=body)


@app.get("/heygen/voices")
async def heygen_list_voices():
    """
    Proxy vers `GET https://api.heygen.com/v2/voices` — cherche un `voice_id` (ex. français) puis
    `HEYGEN_VOICE_ID=...` dans `.env` si le défaut ne convient pas.
    """
    try:
        r = fetch_heygen_voices()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text}
    return JSONResponse(status_code=r.status_code, content=body)


# 3. Créer la "Route" (l'URL) pour parler à Sophie
@app.post("/ask")
async def ask_sophie(request: ChatRequest):
    """
    Endpoint pour envoyer un message à Sophie.
    Format attendu : {"user_id": "user_1", "message": "Quel est mon solde ?"}
    """

    # 1. On récupère l'historique de cet utilisateur (ou on crée un vide)
    if request.user_id not in chat_histories:
        chat_histories[request.user_id] = []



    # 2. On prépare l'entrée pour l'IA avec le contexte
    # On lui donne l'ID et l'historique actuel
    input_data = {
        "input": f"Utilisateur {request.user_id} : {request.message}",
        "chat_history": chat_histories[request.user_id]
    }

    # 3. On fait réfléchir Sophie
    resultat = sophie_brain.invoke(input_data)
    
    # 4. On sauvegarde l'échange dans la mémoire pour la prochaine fois
    chat_histories[request.user_id].append({"human": request.message, "ai": resultat["output"]})
    
    # On renvoie la réponse au format JSON
    return {
        "status": "success",
        "sophie_answer": resultat["output"]
    }

@app.post("/ask-voice")
async def ask_sophie_voice(user_id: str, file: UploadFile = File(...)):
    """
    Reçoit un fichier audio, fait réfléchir Sophie, et génère une réponse vocale.
    """
    # 1. Sauvegarder temporairement le fichier audio envoyé par l'utilisateur
    temp_audio_name = f"temp_{user_id}.wav"
    with open(temp_audio_name, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. ÉTAPE STT : Transformer l'audio en texte via Groq
    user_text = transcribe_audio(temp_audio_name)
    print(f"L'utilisateur a dit : {user_text}")

    # 3. ÉTAPE BRAIN : Faire réfléchir Sophie (on réutilise notre logique précédente)
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    
    input_data = {
        "input": f"Utilisateur {user_id} : {user_text}",
        "chat_history": chat_histories[user_id]
    }
    
    resultat = sophie_brain.invoke(input_data)
    sophie_text = resultat["output"]

    # 4. ÉTAPE TTS : Faire parler Sophie (on génère le MP3)
    output_audio_path = f"response_{user_id}.mp3"
    await generate_speech(sophie_text, output_audio_path)

    # 5. On nettoie le fichier temporaire de l'utilisateur
    os.remove(temp_audio_name)

    # On renvoie le texte et le nom du fichier audio généré
    return {
        "user_said": user_text,
        "sophie_answered": sophie_text,
        "audio_url": output_audio_path
    }

@app.post("/ask-full-avatar")
async def ask_sophie_avatar(user_id: str, message: str):
    """
    Sophie répond avec une vidéo d'avatar !
    """
    # 1. Réflexion de l'IA (Brain)
    if user_id not in chat_histories:
        chat_histories[user_id] = []
        
    res = sophie_brain.invoke({"input": message, "chat_history": chat_histories[user_id]})
    sophie_text = res["output"]
    
    # 2. Génération de la vidéo (HeyGen)
    # C'est cette ligne qui fait le "POST" magique
    video_url = await generate_sophie_video(sophie_text) # <--- Ajoute 'await'
    
    # 3. Sauvegarde historique
    chat_histories[user_id].append({"human": message, "ai": sophie_text})
    
    return {
        "sophie_text": sophie_text,
        "video_url": video_url # Tu recevras un lien vers la vidéo MP4 !
    }
# Pour lancer : uvicorn main:app --reload