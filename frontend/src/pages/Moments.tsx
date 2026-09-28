import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Empty, ErrorBox, PageHeader, SkeletonCards } from "../components/common";
import { IconPlus, IconStar } from "../components/Icons";
import { Sheet } from "../components/Sheet";
import { api } from "../lib/api";
import { formatDay } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useApp } from "../lib/store";

export default function Moments() {
  const { t, lang, copy, settings } = useApp();
  const moments = useAsync(() => api.moments(), []);
  const [creating, setCreating] = useState(false);

  return (
    <div className="page">
      <PageHeader
        title={copy?.momentsTitle ?? t("home.moments")}
        right={
          <button className="btn accent small" onClick={() => setCreating(true)}>
            <IconPlus width={16} /> {t("moments.new")}
          </button>
        }
      />
      {moments.error && <ErrorBox error={moments.error} onRetry={moments.reload} />}
      {moments.loading && !moments.data && <SkeletonCards n={2} h={140} />}
      {moments.data && moments.data.length === 0 && <Empty glyph="忆">{t("moments.empty")}</Empty>}
      {(moments.data ?? []).map((m) => (
        <Link key={m.id} to={`/moments/${m.id}`} className="day-card" style={{ display: "block" }}>
          {m.cover?.thumb && (
            <div style={{ height: 180 }}>
              <img src={m.cover.thumb} alt="" loading="lazy" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            </div>
          )}
          <div className="day-card-body">
            <div className="tiny muted">
              {m.start_day && formatDay(m.start_day, lang, settings?.date_format)}
              {m.end_day && m.end_day !== m.start_day && ` — ${formatDay(m.end_day, lang, settings?.date_format)}`}
            </div>
            <div className="row between">
              <h2 style={{ fontSize: 21, margin: "4px 0" }}>{m.title}</h2>
              {m.favorite && <IconStar filled width={18} style={{ color: "var(--accent)" }} />}
            </div>
            {m.description && <p className="small" style={{ margin: "4px 0 0", color: "var(--ink-2)" }}>{m.description.slice(0, 120)}</p>}
            <div className="tiny muted" style={{ marginTop: 8 }}>{t("moments.items", { m: m.counts.media, t: m.counts.message })}</div>
          </div>
        </Link>
      ))}
      <CreateMoment open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}

function CreateMoment({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useApp();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      const m = await api.createMoment({ title: title.trim(), description: description || null, start_day: start || null, end_day: end || null });
      onClose();
      navigate(`/moments/${m.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("moments.new")} labelledBy="new-moment">
      <form onSubmit={submit}>
        <label className="field">
          <span>{t("moments.title")}</span>
          <input className="input" required maxLength={200} value={title} placeholder={t("moments.titlePlaceholder")}
            onChange={(e) => setTitle(e.target.value)} />
        </label>
        <div className="row" style={{ gap: 12 }}>
          <label className="field" style={{ flex: 1 }}>
            <span>{t("moments.start")}</span>
            <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="field" style={{ flex: 1 }}>
            <span>{t("moments.end")}</span>
            <input className="input" type="date" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span>{t("moments.description")}</span>
          <textarea className="textarea" maxLength={10000} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        {error && <p className="error-box">{error}</p>}
        <button className="btn accent block" disabled={!title.trim()}>{t("moments.create")}</button>
      </form>
    </Sheet>
  );
}
