import { useEffect, useState, type ReactNode } from "react";
import { useApp } from "../lib/store";
import { agoText, formatMonthDay, parseDay, weekday } from "../lib/format";
import type { Confidence } from "../lib/types";
import { IconStar } from "./Icons";

export function Loading({ label }: { label?: string }) {
  const { t } = useApp();
  return (
    <div className="loading-line" role="status" aria-live="polite">
      {label ?? t("common.loading")}
    </div>
  );
}

export function SkeletonCards({ n = 2, h = 320 }: { n?: number; h?: number }) {
  return (
    <div aria-hidden>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: h, marginBottom: 18 }} />
      ))}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const { t } = useApp();
  const offline = error instanceof TypeError;
  return (
    <div className="error-box" role="alert">
      <div>{offline ? t("error.offline") : `${t("common.error")}: ${error.message}`}</div>
      {onRetry && (
        <button className="btn small ghost" style={{ marginTop: 10 }} onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function Empty({ glyph = "空", title, children }: { glyph?: string; title?: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="glyph" aria-hidden>
        {glyph}
      </div>
      {title && <div>{title}</div>}
      {children && <p>{children}</p>}
    </div>
  );
}

export function PageHeader({ eyebrow, title, sub, right }: { eyebrow?: string; title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <header className="page-header row between" style={{ alignItems: "flex-end" }}>
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {right}
    </header>
  );
}

export function DateBlock({ day, size = "md", showAgo = false }: { day: string; size?: "md" | "xl"; showAgo?: boolean }) {
  const { lang } = useApp();
  const d = parseDay(day);
  return (
    <div className="date-block">
      <span className="year">{d.getFullYear()}</span>
      <time className={`md ${size === "xl" ? "xl" : ""}`} dateTime={day}>
        {formatMonthDay(day, lang)}
      </time>
      <span className="wk">
        {weekday(day, lang)}
        {showAgo && ` · ${agoText(day, lang)}`}
      </span>
    </div>
  );
}

export function Avatar({ senderId, size }: { senderId: string | null; size?: "lg" }) {
  const { nameOf, avatarOf } = useApp();
  const src = avatarOf(senderId);
  const name = nameOf(senderId);
  return (
    <span className={`avatar ${size ?? ""}`} aria-hidden>
      {src ? <img src={src} alt="" /> : name.slice(0, 1)}
    </span>
  );
}

export function FavButton({ on, onToggle, label, className }: { on: boolean; onToggle: () => void; label?: string; className?: string }) {
  const { t } = useApp();
  return (
    <button
      type="button"
      className={`icon-btn ${on ? "on" : ""} ${className ?? ""}`}
      aria-pressed={on}
      aria-label={label ?? (on ? t("common.unfavorite") : t("common.favorite"))}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
    >
      <IconStar filled={on} />
    </button>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence | null | undefined }) {
  const { t } = useApp();
  if (!confidence) return null;
  return <span className={`badge-conf ${confidence}`}>{t(`confidence.${confidence}`)}</span>;
}

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return;
    const id = window.setTimeout(onDone, 1800);
    return () => window.clearTimeout(id);
  }, [message, onDone]);
  if (!message) return null;
  return (
    <div className="toast" role="status" aria-live="polite">
      {message}
    </div>
  );
}

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  return { msg, show: setMsg, node: <Toast message={msg} onDone={() => setMsg(null)} /> };
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
