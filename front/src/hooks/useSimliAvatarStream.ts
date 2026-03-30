import { useCallback, useRef, useState } from "react";

export type SimliStreamStatus =
  | "idle"
  | "creating"
  | "webrtc"
  | "connected"
  | "ready"
  | "error";

function apiUrl(path: string): string {
  return "/api" + path;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const text = await res.text();
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : res.statusText;
    throw new Error(detail);
  }
  return data as T;
}

const SIMLI_WSS = "wss://api.simli.ai/compose/webrtc/p2p";

function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** PCM s16le → Simli (PLAY_IMMEDIATE puis chunks). */
function sendPcmOnSignalingWs(ws: WebSocket, pcm: Uint8Array) {
  const enc = new TextEncoder();
  const head = enc.encode("PLAY_IMMEDIATE");
  const firstMax = 16000 * 2 * 4;
  const firstPart = Math.min(firstMax, pcm.length);
  const first = new Uint8Array(head.length + firstPart);
  first.set(head, 0);
  first.set(pcm.subarray(0, firstPart), head.length);
  ws.send(first);
  const step = 6000;
  for (let i = firstPart; i < pcm.length; i += step) {
    ws.send(pcm.subarray(i, i + step));
  }
}

type SessionResponse = {
  session_token: string;
  ice_servers: RTCIceServer[];
};

export function useSimliAvatarStream() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const simliWsRef = useRef<WebSocket | null>(null);
  const combinedStreamRef = useRef<MediaStream | null>(null);
  const readyRef = useRef(false);
  const fallbackTimerRef = useRef<number | null>(null);
  const outputDuckedRef = useRef(false);

  const [status, setStatus] = useState<SimliStreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [streamReady, setStreamReady] = useState(false);
  const [needsSoundTap, setNeedsSoundTap] = useState(false);

  const unlockAudio = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = false;
    v.volume = 1;
    setNeedsSoundTap(false);
    void v.play().catch(() => setNeedsSoundTap(true));
  }, []);

  const duckOutput = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    outputDuckedRef.current = true;
    v.muted = true;
    v.volume = 0;
    const ms = v.srcObject as MediaStream | null;
    ms?.getAudioTracks().forEach((t) => {
      t.enabled = false;
    });
  }, []);

  const restoreOutput = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    outputDuckedRef.current = false;
    v.muted = false;
    v.volume = 1;
    const ms = v.srcObject as MediaStream | null;
    ms?.getAudioTracks().forEach((t) => {
      t.enabled = true;
    });
    void v.play().catch(() => setNeedsSoundTap(true));
  }, []);

  const interruptSpeaking = useCallback(async () => {
    duckOutput();
    const w = simliWsRef.current;
    if (w?.readyState === WebSocket.OPEN) {
      try {
        w.send("SKIP");
      } catch {
        /* ignore */
      }
    }
  }, [duckOutput]);

  const markReady = useCallback(() => {
    if (readyRef.current) return;
    if (fallbackTimerRef.current != null) {
      window.clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    readyRef.current = true;
    setStreamReady(true);
    setStatus("ready");
  }, []);

  const cleanupPc = useCallback(() => {
    if (fallbackTimerRef.current != null) {
      window.clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    const w = simliWsRef.current;
    if (w?.readyState === WebSocket.OPEN) {
      try {
        w.send("DONE");
      } catch {
        /* ignore */
      }
    }
    w?.close();
    simliWsRef.current = null;

    const v = videoRef.current;
    if (v?.srcObject) {
      (v.srcObject as MediaStream).getTracks().forEach((t) => t.stop());
      v.srcObject = null;
    }
    combinedStreamRef.current = null;

    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    readyRef.current = false;
    outputDuckedRef.current = false;
    setStreamReady(false);
    setNeedsSoundTap(false);
  }, []);

  const destroy = useCallback(async () => {
    cleanupPc();
    setStatus("idle");
  }, [cleanupPc]);

  const playPcmBase64 = useCallback(
    (b64: string) => {
      const w = simliWsRef.current;
      if (!b64 || w?.readyState !== WebSocket.OPEN) return;
      try {
        const pcm = b64ToBytes(b64);
        sendPcmOnSignalingWs(w, pcm);
        void unlockAudio();
      } catch {
        /* ignore */
      }
    },
    [unlockAudio],
  );

  const connect = useCallback(async () => {
    setError(null);
    readyRef.current = false;
    cleanupPc();
    setStatus("creating");

    try {
      const session = await fetchJson<SessionResponse>(apiUrl("/simli/session"), {
        method: "POST",
      });

      const iceServers =
        Array.isArray(session.ice_servers) && session.ice_servers.length > 0
          ? session.ice_servers
          : [{ urls: "stun:stun.l.google.com:19302" }];

      const RTC =
        window.RTCPeerConnection ||
        (window as unknown as { webkitRTCPeerConnection?: typeof RTCPeerConnection })
          .webkitRTCPeerConnection;
      if (!RTC) throw new Error("WebRTC non supporté");

      setStatus("webrtc");
      const pc = new RTC({ iceServers });
      pcRef.current = pc;

      const combined = new MediaStream();
      combinedStreamRef.current = combined;

      pc.addEventListener("track", (ev) => {
        if (!ev.track) return;
        combined.addTrack(ev.track);
        const v = videoRef.current;
        if (!v) return;
        v.srcObject = combined;
        if (!outputDuckedRef.current) {
          v.muted = false;
          v.volume = 1;
          combined.getAudioTracks().forEach((t) => {
            t.enabled = true;
          });
        }
        void v.play().catch(() => setNeedsSoundTap(true));
        setTimeout(() => markReady(), 400);
      });

      pc.addTransceiver("audio", { direction: "recvonly" });
      pc.addTransceiver("video", { direction: "recvonly" });

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const token = encodeURIComponent(session.session_token);
      const ws = new WebSocket(`${SIMLI_WSS}?session_token=${token}&enableSFU=true`);
      simliWsRef.current = ws;

      let answer: RTCSessionDescriptionInit | null = null;

      ws.addEventListener("message", (evt) => {
        if (typeof evt.data !== "string") return;
        if (evt.data === "START" || evt.data === "STOP") return;
        if (evt.data.startsWith("pong")) return;
        try {
          const msg = JSON.parse(evt.data) as { type?: string; sdp?: string };
          if (msg.type === "answer" && msg.sdp) {
            answer = { type: "answer", sdp: msg.sdp };
          }
        } catch {
          /* ignore non-JSON */
        }
      });

      await new Promise<void>((resolve, reject) => {
        const to = window.setTimeout(() => reject(new Error("timeout WebSocket Simli")), 20000);
        ws.addEventListener(
          "open",
          () => {
            window.clearTimeout(to);
            const ld = pc.localDescription;
            if (ld) {
              ws.send(JSON.stringify({ type: ld.type, sdp: ld.sdp }));
            }
            resolve();
          },
          { once: true },
        );
        ws.addEventListener(
          "error",
          () => {
            window.clearTimeout(to);
            reject(new Error("WebSocket Simli"));
          },
          { once: true },
        );
      });

      await new Promise<void>((resolve, reject) => {
        const deadline = Date.now() + 25000;
        const t = window.setInterval(() => {
          if (answer) {
            window.clearInterval(t);
            resolve();
          } else if (Date.now() > deadline) {
            window.clearInterval(t);
            reject(new Error("Pas de réponse SDP Simli"));
          }
        }, 30);
      });

      await pc.setRemoteDescription(answer!);

      setStatus("connected");
      setTimeout(() => unlockAudio(), 400);
      fallbackTimerRef.current = window.setTimeout(() => {
        markReady();
      }, 5500);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
      cleanupPc();
    }
  }, [cleanupPc, markReady, unlockAudio]);

  return {
    videoRef,
    status,
    error,
    streamReady,
    needsSoundTap,
    unlockAudio,
    duckOutput,
    restoreOutput,
    interruptSpeaking,
    playPcmBase64,
    connect,
    destroy,
  };
}
