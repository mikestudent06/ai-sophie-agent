import { useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import "./App.css";

type Screen = "login" | "chat" | "avatar";
type Role = "user" | "bot";
type Message = { id: number; role: Role; text: string };

const BOT_INTRO =
  "Bonjour, je suis Sophie, votre conseillère bancaire IA. Je peux vous aider sur vos comptes, crédits, épargne et démarches.";

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
  const [isAvatarLive, setIsAvatarLive] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const userLabel = useMemo(
    () => email.split("@")[0] || "Client",
    [email],
  );

  const addBotResponse = (source: string) => {
    const cannedResponses = [
      "Très bonne question. Souhaitez-vous une simulation ou un résumé de vos options ?",
      "Je peux vous guider étape par étape. Dites-moi votre objectif principal du moment.",
      "Parfait, je m'en occupe. Je peux aussi basculer en mode avatar pour un échange plus naturel.",
    ];
    const index = Math.abs(source.length) % cannedResponses.length;
    setMessages((prev) => [
      ...prev,
      { id: Date.now() + 1, role: "bot", text: cannedResponses[index] },
    ]);
  };

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

  const sendText = () => {
    const payload = draft.trim();
    if (!payload) return;
    setMessages((prev) => [...prev, { id: Date.now(), role: "user", text: payload }]);
    setDraft("");
    window.setTimeout(() => addBotResponse(payload), 450);
  };

  const handleComposerSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    sendText();
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setIsRecording(false);
  };

  const startRecording = async () => {
    if (!("MediaRecorder" in window)) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "bot",
          text: "Votre navigateur ne supporte pas l'enregistrement audio.",
        },
      ]);
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
        const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        const seconds = Math.max(1, Math.round(audioBlob.size / 9000));
        const text = `Message vocal (${seconds}s): "J'ai une question sur mon compte et mes options d'épargne."`;
        setMessages((prev) => [...prev, { id: Date.now(), role: "user", text }]);
        window.setTimeout(() => addBotResponse(text), 550);
        stream.getTracks().forEach((track) => track.stop());
      });

      recorder.start();
      setIsRecording(true);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "bot",
          text: "Accès micro refusé. Autorisez le micro pour envoyer de l'audio.",
        },
      ]);
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
      return;
    }
    void startRecording();
  };

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
                title={isRecording ? "Arrêter l'enregistrement" : "Enregistrer un vocal"}
              >
                {isRecording ? "■" : "🎤"}
              </button>
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Tapez votre message..."
              />
              <button type="submit" className="primary-btn">
                Envoyer
              </button>
            </form>
          </div>
        </section>
      )}

      {screen === "avatar" && (
        <section className="screen avatar-screen">
          <header className="avatar-head">
            <div>
              <strong>Sophie Avatar - discussion temps réel</strong>
              <p className="subtitle">Mode conversation vocale et visuelle</p>
            </div>
            <button className="secondary-btn" onClick={() => setScreen("chat")}>
              Retour au chat texte
            </button>
          </header>

          <div className="avatar-stage">
            <div className={`avatar-orb ${isAvatarLive ? "live" : ""}`}>
              <div>
                <h3>Sophie</h3>
                <p>
                  {isAvatarLive
                    ? "Je vous écoute en direct. Posez votre question bancaire."
                    : "Activez le mode live pour démarrer la discussion temps réel."}
                </p>
              </div>
            </div>
          </div>

          <footer className="avatar-panel">
            <p className="subtitle">
              Statut: {isAvatarLive ? "Session live active (micro + réponses instantanées)." : "Session en pause."}
            </p>
            <button className="primary-btn" onClick={() => setIsAvatarLive((prev) => !prev)}>
              {isAvatarLive ? "Mettre en pause" : "Démarrer le live avatar"}
            </button>
          </footer>
        </section>
      )}
    </main>
  );
}

export default App;
