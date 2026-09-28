import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Media } from "./types";

/** One shared <audio> element: starting a voice pauses any other. Nothing ever plays automatically. */
interface PlayerState {
  current: Media | null;
  playing: boolean;
  position: number;
  duration: number;
  error: string | null;
  queue: Media[];
  play: (item: Media, queue?: Media[]) => void;
  toggle: (item?: Media, queue?: Media[]) => void;
  pause: () => void;
  seek: (fraction: number) => void;
  next: () => void;
  prev: () => void;
  stop: () => void;
}

const Ctx = createContext<PlayerState | null>(null);

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [current, setCurrent] = useState<Media | null>(null);
  const [queue, setQueue] = useState<Media[]>([]);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);

  if (typeof window !== "undefined" && !audioRef.current && typeof Audio !== "undefined") {
    audioRef.current = new Audio();
    audioRef.current.preload = "none";
  }

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onTime = () => setPosition(a.currentTime);
    const onMeta = () => setDuration(isFinite(a.duration) ? a.duration : 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onError = () => {
      setPlaying(false);
      setError("unplayable");
    };
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("play", onPlay);
    a.addEventListener("pause", onPause);
    a.addEventListener("ended", onPause);
    a.addEventListener("error", onError);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("play", onPlay);
      a.removeEventListener("pause", onPause);
      a.removeEventListener("ended", onPause);
      a.removeEventListener("error", onError);
      a.pause();
    };
  }, []);

  const play = useCallback((item: Media, q?: Media[]) => {
    const a = audioRef.current;
    if (!a) return;
    if (q) setQueue(q);
    setError(null);
    if (current?.id !== item.id) {
      a.src = item.url;
      setCurrent(item);
      setPosition(0);
      setDuration(item.duration ?? 0);
    }
    a.play().catch(() => {
      /* autoplay policies / decode errors surface via the error event */
    });
  }, [current?.id]);

  const pause = useCallback(() => audioRef.current?.pause(), []);

  const toggle = useCallback(
    (item?: Media, q?: Media[]) => {
      if (item && item.id !== current?.id) return play(item, q);
      if (playing) pause();
      else if (current) play(current, q);
    },
    [current, playing, pause, play],
  );

  const seek = useCallback((fraction: number) => {
    const a = audioRef.current;
    if (a && isFinite(a.duration)) a.currentTime = Math.max(0, Math.min(1, fraction)) * a.duration;
  }, []);

  const step = useCallback(
    (dir: 1 | -1) => {
      if (!current || !queue.length) return;
      const i = queue.findIndex((m) => m.id === current.id);
      const nextItem = queue[i + dir];
      if (nextItem) play(nextItem);
    },
    [current, queue, play],
  );

  const stop = useCallback(() => {
    const a = audioRef.current;
    if (a) {
      a.pause();
      a.removeAttribute("src");
    }
    setCurrent(null);
    setPlaying(false);
  }, []);

  const value = useMemo<PlayerState>(
    () => ({ current, playing, position, duration, error, queue, play, toggle, pause, seek, stop,
      next: () => step(1), prev: () => step(-1) }),
    [current, playing, position, duration, error, queue, play, toggle, pause, seek, stop, step],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePlayer(): PlayerState {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePlayer outside PlayerProvider");
  return v;
}
