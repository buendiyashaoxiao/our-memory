import { NavLink } from "react-router-dom";
import { formatDay, formatDuration } from "../lib/format";
import { usePlayer } from "../lib/player";
import { useApp } from "../lib/store";
import { IconClose, IconHome, IconImage, IconPause, IconPlay, IconShuffle, IconSkipNext, IconSkipPrev, IconTimeline, IconWave } from "./Icons";

export function TabBar() {
  const { t } = useApp();
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : "");
  return (
    <nav className="tabbar" aria-label="main">
      <NavLink to="/home" className={link}>
        <IconHome />
        {t("nav.home")}
      </NavLink>
      <NavLink to="/timeline" className={link}>
        <IconTimeline />
        {t("nav.timeline")}
      </NavLink>
      <NavLink to="/random" className={({ isActive }) => `center ${isActive ? "active" : ""}`} aria-label={t("random.title")}>
        <span className="dot">
          <IconShuffle />
        </span>
        {t("nav.random")}
      </NavLink>
      <NavLink to="/sounds" className={link}>
        <IconWave />
        {t("nav.sounds")}
      </NavLink>
      <NavLink to="/gallery" className={link}>
        <IconImage />
        {t("nav.gallery")}
      </NavLink>
    </nav>
  );
}

export function MiniPlayer() {
  const p = usePlayer();
  const { nameOf, lang, t } = useApp();
  if (!p.current) return null;
  const m = p.current;
  const dur = p.duration || m.duration || 0;
  const idx = p.queue.findIndex((x) => x.id === m.id);
  return (
    <div className="mini-player" role="region" aria-label={lang === "en" ? "Now playing" : "正在播放"}>
      <button type="button" className="play sm" onClick={() => p.toggle()} aria-label={p.playing ? "pause" : "play"}>
        {p.playing ? <IconPause /> : <IconPlay />}
      </button>
      <div className="info">
        <b>{m.title || (m.day ? formatDay(m.day, lang) : m.filename)}</b>
        <span className="tiny muted">
          {m.sender_id ? nameOf(m.sender_id) + " · " : ""}
          {formatDuration(p.position)} / {formatDuration(dur)}
          {p.error && ` · ${t("sounds.unplayable")}`}
        </span>
        <div className="bar">
          <i style={{ width: `${dur ? (p.position / dur) * 100 : 0}%` }} />
        </div>
      </div>
      {idx > 0 && (
        <button type="button" className="icon-btn" onClick={p.prev} aria-label={t("day.prev")}>
          <IconSkipPrev />
        </button>
      )}
      {idx >= 0 && idx < p.queue.length - 1 && (
        <button type="button" className="icon-btn" onClick={p.next} aria-label={t("day.next")}>
          <IconSkipNext />
        </button>
      )}
      <button type="button" className="icon-btn" onClick={p.stop} aria-label={t("common.close")}>
        <IconClose />
      </button>
    </div>
  );
}
