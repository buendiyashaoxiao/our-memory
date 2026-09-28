import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorBox, FavButton, SkeletonCards } from "../components/common";
import { IconClose, IconPrev } from "../components/Icons";
import { Lightbox } from "../components/Lightbox";
import { MessageList } from "../components/MessageList";
import { Sheet } from "../components/Sheet";
import { Thumb } from "../components/Thumb";
import { VoicePlayer } from "../components/VoicePlayer";
import { api } from "../lib/api";
import { addDays, formatDay } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Moment } from "../lib/types";

export default function MomentView() {
  const { id = "0" } = useParams();
  const { t, lang, settings } = useApp();
  const navigate = useNavigate();
  const mo = useAsync(() => api.moment(Number(id)), [id]);
  const [editing, setEditing] = useState(false);
  const [lb, setLb] = useState<number | null>(null);

  if (mo.error) return <div className="page"><ErrorBox error={mo.error} onRetry={mo.reload} /></div>;
  if (!mo.data) return <div className="page"><SkeletonCards n={1} h={300} /></div>;
  const m = mo.data;
  const visual = (m.media ?? []).filter((x) => x.type === "image" || x.type === "video");
  const sounds = (m.media ?? []).filter((x) => x.type === "voice" || x.type === "audio");

  const days: string[] = [];
  if (m.start_day) {
    const end = m.end_day && m.end_day >= m.start_day ? m.end_day : m.start_day;
    for (let d = m.start_day; d <= end && days.length < 31; d = addDays(d, 1)) days.push(d);
  }

  const removeItem = async (kind: "message" | "media", ref: number) => {
    const updated = await api.removeMomentItem(m.id, kind, ref);
    mo.setData(() => updated);
  };

  return (
    <div className="page">
      <div className="topbar">
        <button className="icon-btn" onClick={() => navigate(-1)} aria-label={t("common.back")}><IconPrev /></button>
        <div className="row" style={{ gap: 0 }}>
          <FavButton on={m.favorite} onToggle={async () => {
            await api.setFavorite("moment", m.id, !m.favorite);
            mo.setData((p) => (p ? { ...p, favorite: !p.favorite } : p));
          }} />
          <button className="btn small ghost" onClick={() => setEditing(true)}>{t("common.edit")}</button>
        </div>
      </div>

      <header className="page-header">
        <div className="eyebrow">
          {m.start_day && formatDay(m.start_day, lang, settings?.date_format)}
          {m.end_day && m.end_day !== m.start_day && ` — ${formatDay(m.end_day, lang, settings?.date_format)}`}
        </div>
        <h1>{m.title}</h1>
      </header>
      {m.description && (
        <p style={{ fontFamily: "var(--serif)", fontSize: 17, lineHeight: 1.9, whiteSpace: "pre-wrap", color: "var(--ink-2)" }}>
          {m.description}
        </p>
      )}

      {days.length > 0 && (
        <div className="chips" style={{ marginTop: 12 }}>
          {days.map((d) => (
            <Link key={d} to={`/day/${d}`} className="chip">{formatDay(d, lang, "numeric")}</Link>
          ))}
        </div>
      )}

      {visual.length > 0 && (
        <section className="section">
          <div className="grid" style={{ borderRadius: 14, overflow: "hidden" }}>
            {visual.map((x, i) => (
              <div key={x.id} style={{ position: "relative" }}>
                <Thumb media={x} onOpen={() => setLb(i)} />
                <RemoveBtn onClick={() => removeItem("media", x.id)} />
              </div>
            ))}
          </div>
        </section>
      )}
      {sounds.length > 0 && (
        <section className="section">
          {sounds.map((s) => (
            <div key={s.id} className="sound-card">
              <div className="row between">
                <span className="tiny muted">{s.day && formatDay(s.day, lang)} {s.title && `· ${s.title}`}</span>
                <RemoveBtn inline onClick={() => removeItem("media", s.id)} />
              </div>
              <VoicePlayer media={s} queue={sounds} />
            </div>
          ))}
        </section>
      )}
      {(m.messages ?? []).length > 0 && (
        <section className="section">
          <MessageList messages={m.messages ?? []} onAction={(msg) => removeItem("message", msg.id)} />
          <p className="tiny muted" style={{ textAlign: "center" }}>
            {lang === "en" ? "Tap a message to remove it from this moment." : "点一下消息可以把它从片段中移除。"}
          </p>
        </section>
      )}

      <EditMoment open={editing} onClose={() => setEditing(false)} moment={m}
        onSaved={(u) => { mo.setData(() => u); setEditing(false); }}
        onDeleted={() => navigate("/moments", { replace: true })} />
      {lb !== null && (
        <Lightbox items={visual} index={lb} onClose={() => setLb(null)} onIndex={setLb} />
      )}
    </div>
  );
}

function RemoveBtn({ onClick, inline }: { onClick: () => void; inline?: boolean }) {
  const { lang } = useApp();
  return (
    <button type="button" className="icon-btn" onClick={onClick} aria-label={lang === "en" ? "Remove from moment" : "从片段中移除"}
      style={inline ? { width: 36, height: 36 } : { position: "absolute", top: 2, right: 2, width: 32, height: 32, color: "#fff",
        background: "rgba(0,0,0,.35)" }}>
      <IconClose width={16} />
    </button>
  );
}

function EditMoment({ open, onClose, moment, onSaved, onDeleted }: {
  open: boolean;
  onClose: () => void;
  moment: Moment;
  onSaved: (m: Moment) => void;
  onDeleted: () => void;
}) {
  const { t } = useApp();
  const [title, setTitle] = useState(moment.title);
  const [description, setDescription] = useState(moment.description ?? "");
  const [start, setStart] = useState(moment.start_day ?? "");
  const [end, setEnd] = useState(moment.end_day ?? "");

  const save = async () => {
    const u = await api.patchMoment(moment.id, { title, description, start_day: start || null, end_day: end || null });
    onSaved(u);
  };
  const del = async () => {
    if (!window.confirm(t("moments.deleteConfirm"))) return;
    await api.deleteMoment(moment.id);
    onDeleted();
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("common.edit")} labelledBy="edit-moment">
      <label className="field">
        <span>{t("moments.title")}</span>
        <input className="input" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <div className="row" style={{ gap: 12 }}>
        <label className="field" style={{ flex: 1 }}>
          <span>{t("moments.start")}</span>
          <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="field" style={{ flex: 1 }}>
          <span>{t("moments.end")}</span>
          <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>
      <label className="field">
        <span>{t("moments.description")}</span>
        <textarea className="textarea" value={description} maxLength={10000} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <button className="btn accent block" onClick={save} disabled={!title.trim()}>{t("common.save")}</button>
      <button className="btn block" style={{ marginTop: 10, color: "var(--accent)" }} onClick={del}>{t("common.delete")}</button>
    </Sheet>
  );
}
