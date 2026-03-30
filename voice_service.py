# voice_service.py
import os
import asyncio
import edge_tts
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# --- PARTIE 1 : SOPHIE PARLE (Gratuit via Edge) ---
async def generate_speech(text: str, output_path: str = "sophie_speech.mp3"):
    """
    Génère une voix française gratuitement via Microsoft Edge.
    Voix suggérées : fr-FR-DeniseNeural (Femme) ou fr-FR-EloiseNeural
    """
    VOICE = "fr-FR-DeniseNeural"
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(output_path)
    return output_path

# --- PARTIE 2 : SOPHIE ÉCOUTE (Gratuit via Groq) ---
def transcribe_audio(audio_file_path: str):
    """
    Transforme ton audio en texte via Groq Whisper.
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    with open(audio_file_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(audio_file_path, file.read()),
            model="whisper-large-v3",
            language="fr",
            response_format="text"
        )
    return transcription

# --- TEST RAPIDE ---
if __name__ == "__main__":
    # Pour tester l'audio (qui est asynchrone)
    test_text = "Bonjour, je suis Sophie. Votre système audio est maintenant opérationnel et gratuit !"
    asyncio.run(generate_speech(test_text))
    print("Fichier sophie_speech.mp3 généré gratuitement !")