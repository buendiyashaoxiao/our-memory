import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { formatDay, formatTime } from "../lib/format";
import { useApp } from "../lib/store";
import type { Media, Message } from "../lib/types";
import { AddToMoment } from "./AddToMoment";
import { ConfidenceBadge, Loading } from "./common";
import { IconBook, IconChat, IconClose, IconNext, IconPlus, IconPrev, IconStar } from "./Icons";
import { MessageList } from "./MessageList";
import { Sheet } from "./Sheet";

const WEAK_SOURCES = new Set(["mtime", "filename_date"]);

export function Lightbox({ items, index, onClose, onIndex, onChange }: {
  items: Media[];
  index: number;
  onClose: () => void;
  onIndex: (i: number) => void;
  onChange?: (m: Media) => void;
}) {
  const { t, lang, settings } = useApp();
  const navigate = useNavigate();
  const m = items[index];
  const [ctxOpen, setCtxOpen] = useState(false);
  const [ctx, setCtx] = useState<{ messages: Message[]; anchor: number | null } | null>(null);
  const [momentOpen, setMomentOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const [undecodable, setUndecodable] = useState(false);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const go = useCallback((d: number) => {
    const n = index + d;
    if (n >= 0 && n < items.length) onIndex(n);
  }, [index, items.length, onIndex]);

  useEffect(() => {
    setFailed(false);
    setUndecodable(false);
    setCtx(null);
  }, [m?.id]);

  useEffect(() => {
    closeRef.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (ctxOpen || momentOpen) return;
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onClose, ctxOpen, momentOpen]);

  if (!m) return null;

  const openContext = async () => {
    setCtxOpen(true);
    if (!ctx) {
      const r = await api.mediaContext(m.id);
      setCtx({ messages: r.messages, anchor: r.anchor_message_id });
    }
  };

  const toggleFav = async () => {
    await api.setFavorite("media", m.id, !m.favorite);
    onChange?.({ ...m, favorite: !m.favorite });
  };

  const assoc = m.association;
  const weak = m.ts_source && WEAK_SOURCES.has(m.ts_source);

  return createPortal(
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={m.filename}>
      <div className="lb-top">
        <div style={{ flex: 1, minWidth: 0 }} className="caption">
          {m.day && <b>{formatDay(m.day, lang, settings?.date_format)}</b>}
          {formatTime(m.ts)}
          <span style={{ marginLeft: 8, opacity: 0.6 }}>
            {index + 1} / {items.length}
          </span>
        </div>
        <button type="button" className={`icon-btn ${m.favorite ? "on" : ""}`} aria-pressed={m.favorite}
          aria-label={m.favorite ? t("common.unfavorite") : t("common.favorite")} onClick={toggleFav}>
          <IconStar filled={m.favorite} />
        </button>
        <button ref={closeRef} type="button" className="icon-btn" aria-label={t("common.close")} onClick={onClose}>
          <IconClose />
        </button>
      </div>

      <div
        className="stage"
        onPointerDown={(e) => (touch.current = { x: e.clientX, y: e.clientY })}
        onPointerUp={(e) => {
          const s = touch.current;
          touch.current = null;
          if (!s) return;
          const dx = e.clientX - s.x;
          const dy = e.clientY - s.y;
          if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
          else if (dy > 110 && Math.abs(dy) > Math.abs(dx) && m.type === "image") onClose();
        }}
      >
        {failed || m.status !== "ok" ? (
          <div className="caption" role="alert">{t("day.missingMedia")}</div>
        ) : m.type === "video" && undecodable ? (
          <div className="caption" role="alert" style={{ textAlign: "center", padding: 24 }}>
            {m.thumb && <img src={m.thumb} alt="" style={{ maxHeight: "50vh", margin: "0 auto 16px", borderRadius: 12 }} />}
            <p>{t("gallery.cannotPlay")}</p>
            <a className="btn ghost small" href={m.url} target="_blank" rel="noreferrer">{t("gallery.openOriginal")}</a>
          </div>
        ) : m.type === "video" ? (
          <video key={m.id} src={m.url} poster={m.thumb ?? undefined} controls playsInline preload="metadata"
            autoPlay={!!settings?.autoplay} aria-label={m.filename}
            onError={(e) => {
              // MEDIA_ERR_SRC_NOT_SUPPORTED / DECODE: the file exists but this browser cannot decode it
              const code = e.currentTarget.error?.code;
              if (code === 3 || code === 4) setUndecodable(true);
              else setFailed(true);
            }} />
        ) : (
          <img key={m.id} src={m.url} alt={m.title ?? `${m.day ?? ""} ${formatTime(m.ts)}`} onError={() => setFailed(true)}
            draggable={false} />
        )}
        {index > 0 && (
          <button type="button" className="icon-btn nav left" aria-label={t("day.prev")} onClick={() => go(-1)}>
            <IconPrev />
          </button>
        )}
        {index < items.length - 1 && (
          <button type="button" className="icon-btn nav right" aria-label={t("day.next")} onClick={() => go(1)}>
            <IconNext />
          </button>
        )}
      </div>

      <div className="lb-bottom">
        {(weak || (assoc?.confidence && assoc.confidence !== "exact")) && (
          <div className="caption row wrap" style={{ gap: 8, marginBottom: 10 }}>
            {weak && <span>{t("gallery.approxTime", { src: t(`tsSource.${m.ts_source}` as never) })}</span>}
            {assoc?.message_id && assoc.confidence !== "exact" && <ConfidenceBadge confidence={assoc.confidence} />}
          </div>
        )}
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="btn ghost small" style={{ flex: 1 }} onClick={openContext}>
            <IconChat width={16} /> {t("gallery.context")}
          </button>
          {m.day && (
            <button type="button" className="btn ghost small" onClick={() => navigate(`/day/${m.day}`)} aria-label={t("gallery.openDay")}>
              <IconBook width={16} />
            </button>
          )}
          <button type="button" className="btn ghost small" onClick={() => setMomentOpen(true)} aria-label={t("day.addToMoment")}>
            <IconPlus width={16} />
          </button>
        </div>
      </div>

      <Sheet open={ctxOpen} onClose={() => setCtxOpen(false)} title={t("gallery.context")} labelledBy="ctx-title">
        {!ctx ? <Loading /> : ctx.messages.length ? (
          <MessageList messages={ctx.messages} highlightId={ctx.anchor} />
        ) : (
          <p className="muted">{t("day.noChat")}</p>
        )}
      </Sheet>
      <AddToMoment open={momentOpen} onClose={() => setMomentOpen(false)} item={{ kind: "media", ref: m.id }} day={m.day} />
    </div>,
    document.body,
  );
}
