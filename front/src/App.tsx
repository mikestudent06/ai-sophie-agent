import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import "./App.css";
import { useSimliAvatarStream } from "./hooks/useSimliAvatarStream";

type Screen = "login" | "chat" | "avatar";
type Role = "user" | "bot";
type Message = { id: number; role: Role; text: string };

const BOT_INTRO =
  "Bonjour, je suis Sophie, votre conseillère bancaire IA. Je peux vous aider sur vos comptes, crédits, épargne et démarches.";

const AVATAR_TIMESLICE_MS = 300;
const AVATAR_SILENCE_MS = 900;

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const r = reader.result as string;
      const comma = r.indexOf(",");
      resolve(comma >= 0 ? r.slice(comma + 1) : r);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

type WsStatus = "idle" | "connecting" | "open" | "closed" | "error";

function App() {
  const [screen, setScreen] = useState<Screen>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState("");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    { id: 1, role: "bot", text: BOT_INTRO },
  ]);
  const [isRecording, setIsRecording] = useState(false);
  const [wsStatus, setWsStatus] = useState<WsStatus>("idle");
  const [sending, setSending] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);

  const [avatarDraft, setAvatarDraft] = useState("");
  const [avatarSending, setAvatarSending] = useState(false);
  const [avatarVoiceBusy, setAvatarVoiceBusy] = useState(false);
  const [isAvatarRecording, setIsAvatarRecording] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const avatarRecRef = useRef<MediaRecorder | null>(null);
  const avatarVoiceWsRef = useRef<WebSocket | null>(null);
  const avatarSilenceTimerRef = useRef<number | null>(null);
  const hasPendingChunksRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);

  const userId = useMemo(() => email.trim(), [email]);

  const userLabel = useMemo(
    () => email.split("@")[0] || "Client",
    [email],
  );

  const appendBot = useCallback((text: string) => {
    setMessages((prev) => [...prev, { id: Date.now(), role: "bot", text }]);
  }, []);

  useEffect(() => {
    if (screen !== "chat" || !userId) {
      wsRef.current?.close();
      wsRef.current = null;
      setWsStatus("idle");
      return;
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/chat`);
    wsRef.current = ws;
    setWsStatus("connecting");

    ws.onopen = () => setWsStatus("open");
    ws.onclose = () => setWsStatus("closed");
    ws.onerror = () => setWsStatus("error");

    ws.onmessage = (event) => {
      let data: { type?: string; text?: string; detail?: string };
      try {
        data = JSON.parse(event.data as string);
      } catch {
        appendBot("Réponse serveur illisible.");
        setSending(false);
        return;
      }
      setSending(false);
      if (data.type === "reply" && typeof data.text === "string") {
        appendBot(data.text);
        return;
      }
      if (data.type === "error") {
        appendBot(`Erreur: ${data.detail ?? "inconnue"}`);
        return;
      }
      if (data.type === "pong") return;
    };

    return () => {
      ws.close();
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [screen, userId, appendBot]);

  const avatarStream = useSimliAvatarStream();

  useEffect(() => {
    if (screen !== "avatar") {
      if (avatarSilenceTimerRef.current != null) {
        window.clearTimeout(avatarSilenceTimerRef.current);
        avatarSilenceTimerRef.current = null;
      }
      avatarVoiceWsRef.current?.close();
      avatarVoiceWsRef.current = null;
      avatarRecRef.current?.stop();
      void avatarStream.destroy();
    }
  }, [screen, avatarStream.destroy]);

  const submitLogin = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const isValidEmail = /\S+@\S+\.\S+/.test(email.trim());
    if (!isValidEmail || password.trim().length < 3) {
      setAuthError("Merci de saisir un email valide et un mot de passe.");
      return;
    }
    setAuthError("");
    setScreen("chat");
  };



  const clearAvatarSilenceTimer = () => {
    if (avatarSilenceTimerRef.current != null) {
      window.clearTimeout(avatarSilenceTimerRef.current);
      avatarSilenceTimerRef.current = null;
    }
  };

  const scheduleAvatarSilenceFlush = (ws: WebSocket) => {
    clearAvatarSilenceTimer();
    avatarSilenceTimerRef.current = window.setTimeout(() => {
      avatarSilenceTimerRef.current = null;
      if (ws.readyState !== WebSocket.OPEN || !hasPendingChunksRef.current) return;
      hasPendingChunksRef.current = false;
      setAvatarVoiceBusy(true);
      ws.send(JSON.stringify({ type: "flush" }));
    }, AVATAR_SILENCE_MS);
  };

  const stopAvatarRecording = () => {
    clearAvatarSilenceTimer();
    setIsAvatarRecording(false);
    avatarRecRef.current?.stop();
  };

  const startAvatarRecording = async () => {
    if (!("MediaRecorder" in window)) {
      appendBot("Micro non supporté.");
      return;
    }
    if (!avatarStream.streamReady || avatarVoiceBusy) return;
    try {
      await avatarStream.interruptSpeaking();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const q = new URLSearchParams({
        user_id: userId,
      });
      const ws = new WebSocket(`${proto}//${window.location.host}/ws/avatar/voice?${q}`);
      avatarVoiceWsRef.current = ws;
      hasPendingChunksRef.current = false;

      ws.onclose = () => {
        setAvatarVoiceBusy(false);
        avatarStream.restoreOutput();
        if (avatarVoiceWsRef.current === ws) {
          avatarVoiceWsRef.current = null;
        }
      };

      ws.onmessage = (event) => {
        let data: {
          type?: string;
          user_said?: string;
          sophie_text?: string;
          detail?: string;
        };
        try {
          data = JSON.parse(event.data as string);
        } catch {
          return;
        }
        if (data.type === "pong") return;
        if (data.type === "error") {
          if (data.detail !== "buffer vide") {
            appendBot("Erreur vocal avatar: " + (data.detail ?? "inconnue"));
          }
          avatarStream.restoreOutput();
          setAvatarVoiceBusy(false);
          return;
        }
        if (data.type === "reply") {
          const said = data.user_said ?? "";
          const bot = data.sophie_text ?? "";
          const pcm = (data as { pcm_base64?: string }).pcm_base64;
          setMessages((prev) => [
            ...prev,
            { id: Date.now(), role: "user", text: "Vous: " + said },
            { id: Date.now() + 1, role: "bot", text: bot },
          ]);
          if (pcm) avatarStream.playPcmBase64(pcm);
          void avatarStream.unlockAudio();
          avatarStream.restoreOutput();
          setAvatarVoiceBusy(false);
        }
      };

      ws.onerror = () => {
        appendBot("WebSocket vocal indisponible.");
        avatarStream.restoreOutput();
        setAvatarVoiceBusy(false);
      };

      await new Promise<void>((resolve, reject) => {
        const to = window.setTimeout(() => reject(new Error("timeout")), 15000);
        ws.addEventListener(
          "open",
          () => {
            window.clearTimeout(to);
            resolve();
          },
          { once: true },
        );
        ws.addEventListener(
          "error",
          () => {
            window.clearTimeout(to);
            reject(new Error("ws"));
          },
          { once: true },
        );
      });

      const recorder = new MediaRecorder(stream);
      avatarRecRef.current = recorder;

      recorder.addEventListener("dataavailable", (event) => {
        void (async () => {
          if (event.data.size === 0 || ws.readyState !== WebSocket.OPEN) return;
          hasPendingChunksRef.current = true;
          const b64 = await blobToBase64(event.data);
          ws.send(JSON.stringify({ type: "chunk", data: b64 }));
          scheduleAvatarSilenceFlush(ws);
        })();
      });

      recorder.addEventListener("stop", () => {
        clearAvatarSilenceTimer();
        stream.getTracks().forEach((track) => track.stop());
        if (ws.readyState === WebSocket.OPEN) {
          if (hasPendingChunksRef.current) {
            hasPendingChunksRef.current = false;
            setAvatarVoiceBusy(true);
          }
          ws.send(JSON.stringify({ type: "end" }));
        }
        avatarRecRef.current = null;
      });

      recorder.start(AVATAR_TIMESLICE_MS);
      setIsAvatarRecording(true);
    } catch {
      appendBot("Micro refusé ou connexion vocal impossible.");
      avatarStream.restoreOutput();
      setAvatarVoiceBusy(false);
    }
  };

  const toggleAvatarRecording = () => {
    if (isAvatarRecording) {
      stopAvatarRecording();
      return;
    }
    void startAvatarRecording();
  };

  const sendAvatarTurn = async () => {
    const msg = avatarDraft.trim();
    if (!msg || !avatarStream.streamReady || avatarSending) return;
    setAvatarSending(true);
    setAvatarDraft("");
    setMessages((prev) => [...prev, { id: Date.now(), role: "user", text: msg }]);
    try {
      await avatarStream.interruptSpeaking();
      const q = new URLSearchParams({
        user_id: userId,
        message: msg,
      });
      const res = await fetch("/api/avatar/stream/turn?" + q.toString(), { method: "POST" });
      const j = (await res.json()) as {
        sophie_text?: string;
        pcm_base64?: string;
        detail?: unknown;
      };
      if (!res.ok) throw new Error(String(j.detail ?? res.statusText));
      const botText = j.sophie_text;
      if (botText) {
        setMessages((prev) => [...prev, { id: Date.now() + 1, role: "bot", text: botText }]);
      }
      if (j.pcm_base64) avatarStream.playPcmBase64(j.pcm_base64);
    } catch (e) {
      appendBot("Erreur avatar: " + (e instanceof Error ? e.message : "inconnue"));
    } finally {
      avatarStream.restoreOutput();
      setAvatarSending(false);
    }
  };

  const sendViaHttp = async (payload: string) => {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, message: payload }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t || res.statusText);
    }
    const j = (await res.json()) as { sophie_answer?: string };
    if (!j.sophie_answer) throw new Error("Réponse vide");
    appendBot(j.sophie_answer);
  };

  const sendText = async () => {
    const payload = draft.trim();
    if (!payload || sending) return;
    setMessages((prev) => [...prev, { id: Date.now(), role: "user", text: payload }]);
    setDraft("");
    setSending(true);

    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "chat", user_id: userId, message: payload }));
      return;
    }

    try {
      await sendViaHttp(payload);
    } catch (e) {
      appendBot(
        `Impossible de joindre Sophie (${e instanceof Error ? e.message : "erreur"}). Vérifiez que l'API tourne sur le port 8000.`,
      );
    } finally {
      setSending(false);
    }
  };

  const handleComposerSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void sendText();
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setIsRecording(false);
  };

  const startRecording = async () => {
    if (!("MediaRecorder" in window)) {
      appendBot("Votre navigateur ne supporte pas l'enregistrement audio.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorderRef.current = recorder;

      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      });

      recorder.addEventListener("stop", () => {
        void (async () => {
          const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
          stream.getTracks().forEach((track) => track.stop());
          if (!audioBlob.size) {
            appendBot("Enregistrement vide.");
            return;
          }
          setVoiceBusy(true);
          const fd = new FormData();
          fd.append("file", audioBlob, "message.webm");
          try {
            const res = await fetch(`/api/ask-voice?user_id=${encodeURIComponent(userId)}`, {
              method: "POST",
              body: fd,
            });
            if (!res.ok) {
              const t = await res.text();
              throw new Error(t || res.statusText);
            }
            const j = (await res.json()) as {
              user_said?: string;
              sophie_answered?: string;
              audio_url?: string;
            };
            setMessages((prev) => [
              ...prev,
              { id: Date.now(), role: "user", text: `Vous: ${j.user_said ?? "(transcription)"}` },
              { id: Date.now() + 1, role: "bot", text: j.sophie_answered ?? "" },
            ]);
            const url = j.audio_url?.startsWith("http")
              ? j.audio_url
              : `${window.location.origin}${j.audio_url ?? ""}`;
            if (j.audio_url) {
              const a = new Audio(url);
              void a.play().catch(() => {
                appendBot("(Lecture audio bloquée par le navigateur — cliquez sur la page puis réessayez.)");
              });
            }
          } catch (e) {
            appendBot(
              `Erreur vocal: ${e instanceof Error ? e.message : "inconnue"}`,
            );
          } finally {
            setVoiceBusy(false);
          }
        })();
      });

      recorder.start();
      setIsRecording(true);
    } catch {
      appendBot("Accès micro refusé. Autorisez le micro pour envoyer de l'audio.");
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
      return;
    }
    void startRecording();
  };

  const wsLabel =
    wsStatus === "open"
      ? "Temps réel connecté"
      : wsStatus === "connecting"
        ? "Connexion…"
        : wsStatus === "error"
          ? "Erreur WebSocket"
          : wsStatus === "closed"
            ? "Déconnecté"
            : "";

  return (
    <main className="app-shell">
      {screen === "login" && (
        <section className="screen login-screen">
          <aside className="login-visual">
            <span className="login-chip">● Secure Banking Assistant</span>
            <div className="login-copy">
              <h1>Parcours client IA bancaire</h1>
              <p>
                Connectez-vous pour discuter avec Sophie, votre conseillère IA en texte, audio ou avatar temps réel.
              </p>
            </div>
            <div className="login-stats">
              <div>Auth simple email + mot de passe</div>
              <div>Chat IA guidé</div>
              <div>Entrée audio micro</div>
              <div>Mode avatar temps réel</div>
            </div>
          </aside>

          <div className="login-form-wrap">
            <h2>Connexion</h2>
            <p className="subtitle">Accédez à votre espace d'assistance Sophie.</p>
            <form className="form" onSubmit={submitLogin}>
              <label>
                Email
                <input
                  type="email"
                  placeholder="vous@banque.fr"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>

              <label>
                Mot de passe
                <span className="password-row">
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  <button
                    className="ghost-action"
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                  >
                    {showPassword ? "Masquer" : "Voir"}
                  </button>
                </span>
              </label>

              {authError && <p className="error">{authError}</p>}
              <button className="primary-btn" type="submit">
                Se connecter
              </button>
            </form>
          </div>
        </section>
      )}

      {screen === "chat" && (
        <section className="screen chat-screen">
          <aside className="chat-sidebar">
            <h3>Espace client</h3>
            <p className="subtitle">Bienvenue {userLabel}</p>
            {wsLabel && <p className="subtitle ws-pill">{wsLabel}</p>}
            <div className="agent-card">
              <p>
                <span className="dot" />
                Sophie - Conseiller bancaire IA
              </p>
              <p className="subtitle">Disponible pour vos questions compte, crédit, épargne.</p>
            </div>
          </aside>

          <div className="chat-main">
            <header className="chat-header">
              <strong>Chat avec Sophie</strong>
              <button className="secondary-btn" onClick={() => setScreen("avatar")}>
                Ouvrir le chat avatar temps réel
              </button>
            </header>

            <div className="messages">
              {messages.map((message) => (
                <article key={message.id} className={`msg ${message.role === "user" ? "user" : "bot"}`}>
                  {message.text}
                </article>
              ))}
            </div>

            <form className="composer" onSubmit={handleComposerSubmit}>
              <button
                type="button"
                className={`round-btn ${isRecording ? "recording" : ""}`}
                onClick={toggleRecording}
                disabled={voiceBusy}
                title={isRecording ? "Arrêter l'enregistrement" : "Enregistrer un vocal"}
              >
                {isRecording ? "■" : "🎤"}
              </button>
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={sending ? "Sophie réfléchit…" : "Tapez votre message…"}
                disabled={sending}
              />
              <button type="submit" className="primary-btn" disabled={sending}>
                {sending ? "…" : "Envoyer"}
              </button>
            </form>
          </div>
        </section>
      )}

      {screen === "avatar" && (
        <section className="screen avatar-screen">
          <header className="avatar-head">
            <div>
              <strong>Sophie Avatar — Simli (temps réel)</strong>
              <p className="subtitle">
                WebRTC temps réel. Connectez le stream, attendez « ready », puis envoyez une question (même historique que le chat).
              </p>
            </div>
            <button className="secondary-btn" onClick={() => setScreen("chat")}>
              Retour au chat texte
            </button>
          </header>

          <div className="avatar-stage">
            <div className={"avatar-orb " + (avatarStream.streamReady ? "live" : "")}>
              <video ref={avatarStream.videoRef} className="avatar-video" playsInline autoPlay />
              {!avatarStream.streamReady && (
                <div className="avatar-placeholder">
                  <h3>Sophie</h3>
                  <p>Connectez le flux vidéo pour afficher l avatar.</p>
                </div>
              )}
            </div>
          </div>

          {avatarStream.error && <p className="error">{avatarStream.error}</p>}
            {avatarStream.needsSoundTap && (
              <p className="subtitle">
                <button type="button" className="primary-btn" onClick={() => avatarStream.unlockAudio()}>
                  Activer le son (navigateur)
                </button>
              </p>
            )}
          <p className="subtitle avatar-status">
            Flux Simli: {avatarStream.status}
            {avatarStream.streamReady ? " · prêt pour les répliques" : ""}
          </p>

          <footer className="avatar-panel avatar-panel-stack">
            <div className="button-row">
              <button
                type="button"
                className="primary-btn"
                onClick={() => void avatarStream.connect()}
                disabled={
                  avatarStream.status === "creating" || avatarStream.status === "webrtc"
                }
              >
                {avatarStream.streamReady ? "Reconnecter" : "Connecter l’avatar"}
              </button>
              <button type="button" className="secondary-btn" onClick={() => void avatarStream.destroy()}>
                Déconnecter
              </button>
            </div>
            <form
              className="composer avatar-composer"
              onSubmit={(e) => {
                e.preventDefault();
                void sendAvatarTurn();
              }}
            >
              <button
                type="button"
                className={`round-btn ${isAvatarRecording ? "recording" : ""}`}
                onClick={toggleAvatarRecording}
                disabled={!avatarStream.streamReady || (avatarVoiceBusy && !isAvatarRecording)}
                title={isAvatarRecording ? "Arrêter" : "Parler à Sophie"}
              >
                {isAvatarRecording ? "■" : "🎤"}
              </button>
              <input
                value={avatarDraft}
                onChange={(e) => setAvatarDraft(e.target.value)}
                placeholder={
                  avatarStream.streamReady ? "Écrire ou utiliser le micro…" : "Attente connexion stream…"
                }
                disabled={!avatarStream.streamReady || avatarSending}
              />
              <button
                type="submit"
                className="primary-btn"
                disabled={!avatarStream.streamReady || avatarSending || !avatarDraft.trim()}
              >
                {avatarSending ? "…" : "Envoyer"}
              </button>
            </form>
          </footer>
        </section>
      )}
    </main>
  );
}

export default App;
