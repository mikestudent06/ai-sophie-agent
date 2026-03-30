# voice_service.py
import os
import asyncio
import tempfile
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


async def text_to_pcm16_mono_16k(text: str) -> bytes:
    """
    TTS Edge → PCM s16le 16 kHz mono (format attendu par Simli WebRTC).
    Nécessite ffmpeg dans le PATH (ou la variable FFMPEG_PATH vers l'exécutable).
    """
    raw = (text if isinstance(text, str) else str(text or "")).strip()
    if not raw:
        return b""

    # Limite prudente pour Edge TTS (évite timeouts / réponses énormes du LLM)
    max_chars = int(os.getenv("SIMLI_TTS_MAX_CHARS", "12000"))
    if len(raw) > max_chars:
        raw = raw[:max_chars].rsplit(" ", 1)[0] + "…"

    voice = os.getenv("SIMLI_TTS_VOICE", "fr-FR-DeniseNeural")
    ffmpeg_bin = os.getenv("FFMPEG_PATH", "ffmpeg")

    communicate = edge_tts.Communicate(raw, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
        mp3_path = tf.name
    try:
        try:
            await communicate.save(mp3_path)
        except Exception as e:
            raise RuntimeError(f"Edge TTS (synthèse): {type(e).__name__}: {e}") from e

        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg_bin,
                "-nostdin",
                "-y",
                "-i",
                mp3_path,
                "-f",
                "s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-acodec",
                "pcm_s16le",
                "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"ffmpeg introuvable ({ffmpeg_bin}). Installez ffmpeg ou définissez FFMPEG_PATH dans .env."
            ) from e

        out, err = await proc.communicate()
        err_s = (err or b"").decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            if not err_s:
                err_s = f"code de sortie {proc.returncode}"
            raise RuntimeError(f"ffmpeg: {err_s[:1200]}")
        if not out:
            hint = err_s[-400:] if err_s else "(stderr vide)"
            raise RuntimeError(
                "ffmpeg n'a produit aucun PCM sur stdout. "
                "Sous Windows, vérifiez FFMPEG_PATH et que le MP3 TTS est valide. "
                f"Détails: {hint}"
            )
        return out
    finally:
        try:
            os.unlink(mp3_path)
        except OSError:
            pass

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