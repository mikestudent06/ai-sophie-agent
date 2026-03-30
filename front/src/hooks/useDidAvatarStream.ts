import { useCallback, useEffect, useRef, useState } from "react";

export type DidStreamStatus =
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


async function postInterruptBestEffort(streamId: string, sessionId: string): Promise<void> {
  try {
    await fetch(apiUrl("/streaming/" + streamId + "/interrupt"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch {
    /* ignore */
  }
}

type CreateStreamResponse = {
  id: string;
  offer: RTCSessionDescriptionInit;
  ice_servers: RTCIceServer[];
  session_id: string;
  /** Image présentatrice tant que le flux WebRTC n’a pas encore de frame */
  idle_poster_url?: string;
};

export function useDidAvatarStream() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const streamIdRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const readyRef = useRef(false);
  const fallbackTimerRef = useRef<number | null>(null);
  const outputDuckedRef = useRef(false);
  const speechBusyTimerRef = useRef<number | null>(null);
  const warmupDoneRef = useRef(false);

  const [status, setStatus] = useState<DidStreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [streamId, setStreamId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [streamReady, setStreamReady] = useState(false);
  const [needsSoundTap, setNeedsSoundTap] = useState(false);
  const [speechBusy, setSpeechBusy] = useState(false);
  const [idlePosterUrl, setIdlePosterUrl] = useState<string | null>(null);
  /** Masque le spinner natif du navigateur (waiting / stalled entre frames WebRTC). */
  const [streamCoverVisible, setStreamCoverVisible] = useState(false);

  const clearSpeechBusy = useCallback(() => {
    if (speechBusyTimerRef.current != null) {
      window.clearTimeout(speechBusyTimerRef.current);
      speechBusyTimerRef.current = null;
    }
    setSpeechBusy(false);
  }, []);

  /**
   * Le POST /speak revient avant la fin de la lecture WebRTC. On estime une fenêtre
   * pour éviter d enchaîner une 2e réplique pendant que la 1re joue encore (chevauchement / stitch).
   * Réinitialisé par interruptSpeaking (coupure / nouveau tour).
   */
  const registerSpeechEstimate = useCallback((text: string) => {
    clearSpeechBusy();
    const t = (text || "").trim();
    const ms = Math.min(
      120_000,
      Math.max(2500, t.length * 72),
    );
    setSpeechBusy(true);
    speechBusyTimerRef.current = window.setTimeout(() => {
      speechBusyTimerRef.current = null;
      setSpeechBusy(false);
    }, ms);
  }, [clearSpeechBusy]);

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
    clearSpeechBusy();
    duckOutput();
    const sid = sessionIdRef.current;
    const stid = streamIdRef.current;
    if (sid && stid) {
      await postInterruptBestEffort(stid, sid);
    }
    const dc = dcRef.current;
    if (dc?.readyState === "open") {
      try {
        dc.send("stream/interrupt");
      } catch {
        /* ignore */
      }
      try {
        dc.send("did.interrupt");
      } catch {
        /* ignore */
      }
    }
  }, [clearSpeechBusy, duckOutput]);


  const markReady = useCallback(() => {
    if (readyRef.current) return;
    if (fallbackTimerRef.current != null) {
      window.clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    readyRef.current = true;
    setStreamReady(true);
    setStatus("ready");

    const sid = sessionIdRef.current;
    const stid = streamIdRef.current;
    if (sid && stid && !warmupDoneRef.current) {
      warmupDoneRef.current = true;
      void fetchJson(apiUrl("/streaming/" + stid + "/warmup"), {
        method: "POST",
        body: JSON.stringify({ session_id: sid }),
      }).catch(() => {
        // best-effort uniquement
      });
    }
  }, []);

  const cleanupPc = useCallback(() => {
    clearSpeechBusy();
    if (fallbackTimerRef.current != null) {
      window.clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    const v = videoRef.current;
    if (v?.srcObject) {
      (v.srcObject as MediaStream).getTracks().forEach((t) => t.stop());
      v.srcObject = null;
    }
    dcRef.current = null;
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    streamIdRef.current = null;
    sessionIdRef.current = null;
    readyRef.current = false;
    outputDuckedRef.current = false;
    setStreamId(null);
    setSessionId(null);
    setStreamReady(false);
    setNeedsSoundTap(false);
    setIdlePosterUrl(null);
    setStreamCoverVisible(false);
  }, [clearSpeechBusy]);

  useEffect(() => {
    if (!streamId) return;
    const v = videoRef.current;
    if (!v) return;

    const showCover = () => setStreamCoverVisible(true);
    const hideCover = () => setStreamCoverVisible(false);

    v.addEventListener("waiting", showCover);
    v.addEventListener("stalled", showCover);
    v.addEventListener("playing", hideCover);

    return () => {
      v.removeEventListener("waiting", showCover);
      v.removeEventListener("stalled", showCover);
      v.removeEventListener("playing", hideCover);
    };
  }, [streamId]);

  const destroy = useCallback(async () => {
    const sid = sessionIdRef.current;
    const stid = streamIdRef.current;
    cleanupPc();
    setStatus("idle");
    if (sid && stid) {
      try {
        await fetchJson(apiUrl("/streaming/" + stid), {
          method: "DELETE",
          body: JSON.stringify({ session_id: sid }),
        });
      } catch {
        /* ignore */
      }
    }
  }, [cleanupPc]);

  const connect = useCallback(async () => {
    setError(null);
    readyRef.current = false;
    cleanupPc();
    setStatus("creating");

    try {
      const created = await fetchJson<CreateStreamResponse>(apiUrl("/streaming/create"), {
        method: "POST",
      });

      const { id: newStreamId, offer, ice_servers: iceServers, session_id: newSessionId } =
        created;
      setIdlePosterUrl(
        typeof created.idle_poster_url === "string" && created.idle_poster_url.length > 0
          ? created.idle_poster_url
          : null,
      );
      streamIdRef.current = newStreamId;
      sessionIdRef.current = newSessionId;
      warmupDoneRef.current = false;
      setStreamId(newStreamId);
      setSessionId(newSessionId);

      const RTC = window.RTCPeerConnection || (window as unknown as { webkitRTCPeerConnection?: typeof RTCPeerConnection }).webkitRTCPeerConnection;
      if (!RTC) throw new Error("WebRTC non supporté");

      setStatus("webrtc");
      const pc = new RTC({ iceServers: iceServers ?? [] });
      pcRef.current = pc;

      const dc = pc.createDataChannel("JanusDataChannel");
      dcRef.current = dc;
      dc.addEventListener("message", (ev) => {
        const raw = String(ev.data);
        const [event] = raw.split(":");
        if (event === "stream/ready") {
          setTimeout(() => markReady(), 800);
        }
      });

      pc.addEventListener("icecandidate", (ev) => {
        const sid = sessionIdRef.current;
        const stid = streamIdRef.current;
        if (!sid || !stid) return;
        if (ev.candidate) {
          const c = ev.candidate;
          void fetchJson(apiUrl("/streaming/" + stid + "/ice"), {
            method: "POST",
            body: JSON.stringify({
              session_id: sid,
              candidate: c.candidate,
              sdpMid: c.sdpMid,
              sdpMLineIndex: c.sdpMLineIndex,
            }),
          }).catch(() => {});
        } else {
          void fetchJson(apiUrl("/streaming/" + stid + "/ice"), {
            method: "POST",
            body: JSON.stringify({ session_id: sid }),
          }).catch(() => {});
        }
      });

      pc.addEventListener("track", (ev) => {
        const v = videoRef.current;
        if (!ev.streams[0] || !v) return;
        const ms = ev.streams[0];
        v.srcObject = ms;
        if (!outputDuckedRef.current) {
          v.muted = false;
          v.volume = 1;
          ms.getAudioTracks().forEach((t) => {
            t.enabled = true;
          });
        }
        void v.play().catch(() => {
          setNeedsSoundTap(true);
        });
      });

      await pc.setRemoteDescription(offer);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);

      await fetchJson(apiUrl("/streaming/" + newStreamId + "/sdp"), {
        method: "POST",
        body: JSON.stringify({
          session_id: newSessionId,
          answer: {
            type: pc.localDescription?.type,
            sdp: pc.localDescription?.sdp,
          },
        }),
      });

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
    streamId,
    sessionId,
    streamReady,
    needsSoundTap,
    unlockAudio,
    duckOutput,
    restoreOutput,
    interruptSpeaking,
    connect,
    destroy,
    speechBusy,
    registerSpeechEstimate,
    clearSpeechBusy,
    idlePosterUrl,
    streamCoverVisible,
  };
}
