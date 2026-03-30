import asyncio
import base64
import json
import os
import re
import uuid
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage

from brain import sophie_brain
from video_service import fetch_heygen_avatars, fetch_heygen_voices, generate_sophie_video
from voice_service import generate_speech, transcribe_audio
import stream_service

app = FastAPI(title="Sophie AI - Financial Advisor")

AUDIO_DIR = Path(__file__).resolve().parent / "generated_audio"
AUDIO_DIR.mkdir(exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_histories: dict[str, list] = {}


def safe_user_id(user_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", user_id)[:120] or "user"


async def avatar_voice_pipeline(
    user_id: str, stream_id: str, session_id: str, audio_bytes: bytes
) -> dict[str, Any]:
    """Transcription → Sophie → D-ID speak_stream."""
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio vide")
    safe = safe_user_id(user_id)
    temp_audio = AUDIO_DIR / f"temp_av_{safe}_{uuid.uuid4().hex[:12]}.webm"
    temp_audio.write_bytes(audio_bytes)
    try:
        user_text = await asyncio.to_thread(transcribe_audio, str(temp_audio))
    finally:
        if temp_audio.is_file():
            os.remove(temp_audio)
    if not (user_text or "").strip():
        raise HTTPException(status_code=400, detail="Transcription vide")
    sophie_text = await asyncio.to_thread(run_sophie_turn, user_id, user_text.strip())
    status, data = await asyncio.to_thread(
        stream_service.speak_stream, stream_id, session_id, sophie_text
    )
    if status >= 400:
        raise HTTPException(status_code=status, detail=data)
    return {"user_said": user_text, "sophie_text": sophie_text, "stream": data}


def run_sophie_turn(user_id: str, message: str) -> str:
    if user_id not in chat_histories:
        chat_histories[user_id] = []

    turn_human = f"Utilisateur {user_id} : {message}"
    input_data = {
        "input": turn_human,
        "chat_history": chat_histories[user_id],
    }
    resultat = sophie_brain.invoke(input_data)
    out = resultat["output"]
    chat_histories[user_id].extend(
        [HumanMessage(content=turn_human), AIMessage(content=out)]
    )
    return out


class ChatRequest(BaseModel):
    user_id: str
    message: str


@app.get("/heygen/avatars")
async def heygen_list_avatars():
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
    try:
        r = fetch_heygen_voices()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text}
    return JSONResponse(status_code=r.status_code, content=body)


@app.post("/ask")
async def ask_sophie(request: ChatRequest):
    sophie_answer = await asyncio.to_thread(
        run_sophie_turn, request.user_id, request.message
    )
    return {"status": "success", "sophie_answer": sophie_answer}


@app.websocket("/ws/chat")
async def chat_socket(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "detail": "JSON invalide"})
                continue

            msg_type = payload.get("type")
            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if msg_type != "chat":
                await ws.send_json(
                    {"type": "error", "detail": "Type inconnu (attendu: chat ou ping)"}
                )
                continue

            user_id = payload.get("user_id") or ""
            message = (payload.get("message") or "").strip()
            if not user_id or not message:
                await ws.send_json(
                    {"type": "error", "detail": "user_id et message requis"}
                )
                continue

            try:
                answer = await asyncio.to_thread(run_sophie_turn, user_id, message)
            except Exception as e:
                await ws.send_json({"type": "error", "detail": str(e)})
                continue

            await ws.send_json({"type": "reply", "text": answer})
    except WebSocketDisconnect:
        return


@app.websocket("/ws/avatar/voice")
async def avatar_voice_socket(ws: WebSocket):
    """
    Chunks audio (base64) + flush pour transcription quasi temps réel.
    Query: user_id, stream_id, session_id
    Messages JSON: {type:'start'}, {type:'chunk', data: base64}, {type:'flush'|'end'}, {type:'ping'}
    """
    await ws.accept()
    q = ws.query_params
    user_id = (q.get("user_id") or "").strip()
    stream_id = (q.get("stream_id") or "").strip()
    session_id = (q.get("session_id") or "").strip()
    if not user_id or not stream_id or not session_id:
        await ws.send_json(
            {"type": "error", "detail": "user_id, stream_id et session_id requis (query)"}
        )
        await ws.close(code=4000)
        return

    buffer = bytearray()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "detail": "JSON invalide"})
                continue

            msg_type = payload.get("type")
            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if msg_type == "start":
                await asyncio.to_thread(
                    stream_service.interrupt_stream, stream_id, session_id
                )
                await ws.send_json({"type": "started"})
                continue

            if msg_type == "chunk":
                b64 = payload.get("data") or ""
                try:
                    buffer.extend(base64.b64decode(b64))
                except Exception:
                    await ws.send_json({"type": "error", "detail": "chunk base64 invalide"})
                continue

            if msg_type in ("flush", "end"):
                if buffer:
                    audio_bytes = bytes(buffer)
                    buffer.clear()
                    try:
                        result = await avatar_voice_pipeline(
                            user_id, stream_id, session_id, audio_bytes
                        )
                    except HTTPException as e:
                        detail = e.detail
                        await ws.send_json(
                            {
                                "type": "error",
                                "detail": detail if isinstance(detail, str) else str(detail),
                            }
                        )
                    else:
                        await ws.send_json({"type": "reply", **result})
                elif msg_type == "flush":
                    await ws.send_json({"type": "error", "detail": "buffer vide"})
                if msg_type == "end":
                    break
                continue

            await ws.send_json({"type": "error", "detail": "type inconnu"})
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@app.get("/media/audio/{filename}")
async def serve_generated_audio(filename: str):
    if not re.match(r"^response_[a-zA-Z0-9._-]+\.mp3$", filename):
        raise HTTPException(status_code=404, detail="Fichier non autorisé")
    path = AUDIO_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio introuvable")
    return FileResponse(path, media_type="audio/mpeg", filename=filename)


@app.post("/ask-voice")
async def ask_sophie_voice(user_id: str, file: UploadFile = File(...)):
    safe = safe_user_id(user_id)
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in (".webm", ".wav", ".mp3", ".m4a", ".ogg", ""):
        suffix = ".webm"
    temp_audio = AUDIO_DIR / f"temp_{safe}{suffix or '.webm'}"

    with open(temp_audio, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        user_text = transcribe_audio(str(temp_audio))
    finally:
        if temp_audio.is_file():
            os.remove(temp_audio)

    sophie_text = await asyncio.to_thread(run_sophie_turn, user_id, user_text)

    out_name = f"response_{safe}.mp3"
    output_audio_path = AUDIO_DIR / out_name
    await generate_speech(sophie_text, str(output_audio_path))

    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    audio_path = f"/media/audio/{out_name}"
    audio_url = f"{base}{audio_path}" if base else audio_path

    return {
        "user_said": user_text,
        "sophie_answered": sophie_text,
        "audio_url": audio_url,
    }


@app.post("/ask-full-avatar")
async def ask_sophie_avatar(user_id: str, message: str):
    if user_id not in chat_histories:
        chat_histories[user_id] = []

    res = await asyncio.to_thread(
        lambda: sophie_brain.invoke(
            {"input": message, "chat_history": chat_histories[user_id]}
        )
    )
    sophie_text = res["output"]

    video_url = await generate_sophie_video(sophie_text)

    chat_histories[user_id].extend(
        [HumanMessage(content=message), AIMessage(content=sophie_text)]
    )

    return {"sophie_text": sophie_text, "video_url": video_url}

# --- D-ID streaming (WebRTC) : proxy vers api.d-id.com ---
class SdpAnswerBody(BaseModel):
    session_id: str
    answer: dict[str, Any]


class IceBody(BaseModel):
    session_id: str
    candidate: Any | None = None
    sdpMid: str | None = None
    sdpMLineIndex: int | None = None


class SpeakStreamBody(BaseModel):
    session_id: str
    text: str


class DeleteStreamBody(BaseModel):
    session_id: str


def _did_ok(status: int, data: dict) -> None:
    if status >= 400:
        raise HTTPException(status_code=status, detail=data)


@app.post("/streaming/create")
async def streaming_create():
    try:
        status, data = await asyncio.to_thread(stream_service.create_stream)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    _did_ok(status, data)
    return data


@app.post("/streaming/{stream_id}/sdp")
async def streaming_sdp(stream_id: str, body: SdpAnswerBody):
    status, data = await asyncio.to_thread(
        stream_service.post_sdp, stream_id, body.answer, body.session_id
    )
    _did_ok(status, data)
    return data


@app.post("/streaming/{stream_id}/ice")
async def streaming_ice(stream_id: str, body: IceBody):
    status, data = await asyncio.to_thread(
        stream_service.post_ice,
        stream_id,
        body.session_id,
        body.candidate,
        body.sdpMid,
        body.sdpMLineIndex,
    )
    _did_ok(status, data)
    return data




@app.post("/streaming/{stream_id}/interrupt")
async def streaming_interrupt(stream_id: str, body: DeleteStreamBody):
    """Interrompt la synthèse vocale en cours (best-effort, compatible barge-in)."""
    status, data = await asyncio.to_thread(
        stream_service.interrupt_stream, stream_id, body.session_id
    )
    if status == 404:
        return {"ok": True, "noop": True, "detail": "upstream sans endpoint interrupt"}
    if status >= 400:
        raise HTTPException(status_code=status, detail=data)
    return {"ok": True, "upstream": data}

@app.post("/streaming/{stream_id}/speak")
async def streaming_speak(stream_id: str, body: SpeakStreamBody):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text vide")
    status, data = await asyncio.to_thread(
        stream_service.speak_stream, stream_id, body.session_id, body.text.strip()
    )
    _did_ok(status, data)
    return data


@app.delete("/streaming/{stream_id}")
async def streaming_delete(stream_id: str, body: DeleteStreamBody):
    status, data = await asyncio.to_thread(
        stream_service.delete_stream, stream_id, body.session_id
    )
    if status >= 400:
        raise HTTPException(status_code=status, detail=data)
    return data


@app.post("/avatar/stream/turn")
async def avatar_stream_turn(
    user_id: str,
    message: str,
    stream_id: str,
    session_id: str,
):
    if not message.strip():
        raise HTTPException(status_code=400, detail="message vide")
    sophie_text = await asyncio.to_thread(run_sophie_turn, user_id, message.strip())
    status, data = await asyncio.to_thread(
        stream_service.speak_stream, stream_id, session_id, sophie_text
    )
    _did_ok(status, data)
    return {"sophie_text": sophie_text, "stream": data}

@app.post("/avatar/stream/voice")
async def avatar_stream_voice(
    user_id: str,
    stream_id: str,
    session_id: str,
    file: UploadFile = File(...),
):
    """Vocal: transcription -> Sophie -> stream D-ID (fichier complet)."""
    audio_bytes = await file.read()
    return await avatar_voice_pipeline(user_id, stream_id, session_id, audio_bytes)

