import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import { formatDuration } from "../lib/format";
import { usePlayer } from "../lib/player";
import { useApp } from "../lib/store";
import type { Media } from "../lib/types";
import { IconPause, IconPlay } from "./Icons";

/**
 * Play button + real waveform (peaks computed locally at import) or a plain
 * progress bar when no waveform is available. Never auto-plays.
 */
export function VoicePlayer({ media, queue, size }: { media: Media; queue?: Media[]; size?: "sm" }) {
  const { t, lang } = useApp();
  const player = usePlayer();
  const isCurrent = player.current?.id === media.id;
  const playing = isCurrent && player.playing;
  const dur = (isCurrent && player.duration) || media.duration || 0;
  const progress = isCurrent && dur ? player.position / dur : 0;
  const waveRef = useRef<HTMLDivElement>(null);

  const seekFromEvent = (e: PointerEvent<HTMLDivElement>) => {
    if (!isCurrent || !waveRef.current) return;
    const r = waveRef.current.getBoundingClientRect();
    player.seek((e.clientX - r.left) / r.width);
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!isCurrent || !dur) return;
    if (e.key === "ArrowRight") player.seek(Math.min(1, progress + 5 / dur));
    if (e.key === "ArrowLeft") player.seek(Math.max(0, progress - 5 / dur));
  };

  const peaks = media.waveform;
  const label = lang === "en" ? "Voice" : "语音";
  const unplayable = !media.playable || (isCurrent && player.error);

  return (
    <div className={`voice ${size ?? ""}`}>
      <button
        type="button"
        className={`play ${size ?? ""}`}
        onClick={() => player.toggle(media, queue)}
        disabled={!media.playable}
        aria-label={`${playing ? (lang === "en" ? "Pause" : "暂停") : lang === "en" ? "Play" : "播放"} ${label} ${formatDuration(dur)}`}
        title={unplayable ? t("sounds.unplayable") : undefined}
      >
        {playing ? <IconPause /> : <IconPlay />}
      </button>
      <div
        ref={waveRef}
        className={`wave ${peaks?.length ? "" : "flat"}`}
        role="slider"
        tabIndex={isCurrent ? 0 : -1}
        aria-label={lang === "en" ? "Playback position" : "播放进度"}
        aria-valuemin={0}
        aria-valuemax={Math.round(dur)}
        aria-valuenow={Math.round(progress * dur)}
        onPointerDown={seekFromEvent}
        onKeyDown={onKey}
      >
        {peaks?.length ? (
          peaks.map((p, i) => (
            <i key={i} className={i / peaks.length < progress ? "on" : ""} style={{ height: `${Math.max(8, p * 100)}%` }} />
          ))
        ) : (
          <span className="fill" style={{ width: `${progress * 100}%` }} />
        )}
      </div>
      <span className="dur">{isCurrent && player.position > 0 ? formatDuration(player.position) : formatDuration(dur)}</span>
      {unplayable && <span className="sr-only">{t("sounds.unplayable")}</span>}
    </div>
  );
}
