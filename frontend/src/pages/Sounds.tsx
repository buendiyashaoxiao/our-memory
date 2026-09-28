import { useState } from "react";
import { Link } from "react-router-dom";
import { Avatar, Empty, ErrorBox, FavButton, Loading, PageHeader, Segmented, SkeletonCards } from "../components/common";
import { Sheet } from "../components/Sheet";
import { VoicePlayer } from "../components/VoicePlayer";
import { api } from "../lib/api";
import { formatDay, formatDurationLong, formatTime, num } from "../lib/format";
import { useInfinite } from "../lib/hooks";
import { usePlayer } from "../lib/player";
import { useApp } from "../lib/store";
import type { Media } from "../lib/types";

export default function Sounds() {
  const { t, lang, copy, nameOf, settings } = useApp();
  const player = usePlayer();
  const [filter, setFilter] = useState<"all" | "fav">("all");
  const [sender, setSender] = useState<string | null>(null);
  const [edit, setEdit] = useState<Media | null>(null);
  const [total, setTotal] = useState<{ n: number; s: number } | null>(null);

  const list = useInfinite<Media>(async (cursor) => {
    const page = await api.sounds({ cursor, favorites: filter === "fav", sender });
    setTotal({ n: page.total, s: page.total_seconds });
    return page;
  }, [filter, sender]);

  const update = (m: Media) => list.setItems((items) => items.map((x) => (x.id === m.id ? { ...x, ...m, context: x.context } : x)));

  const toggleFav = async (m: Media) => {
    await api.setFavorite("media", m.id, !m.favorite);
    update({ ...m, favorite: !m.favorite });
  };

  const participants = settings?.participants_detected ?? [];

  return (
    <div className="page">
      <PageHeader
        eyebrow="Sound Museum"
        title={copy?.soundMuseumTitle ?? t("nav.sounds")}
        sub={
          <>
            {copy?.soundMuseumIntro}
            {total && total.n > 0 && (
              <>
                <br />
                {t("sounds.count", { n: num(total.n, lang), d: formatDurationLong(total.s, lang) })}
              </>
            )}
          </>
        }
      />

      <div className="row between wrap" style={{ marginBottom: 18 }}>
        <Segmented label={t("nav.sounds")} value={filter} onChange={setFilter}
          options={[{ value: "all", label: t("sounds.all") }, { value: "fav", label: t("sounds.favorites") }]} />
        {participants.length > 1 && (
          <div className="seg" role="group" aria-label="sender">
            <button aria-pressed={sender === null} onClick={() => setSender(null)}>{t("sounds.all")}</button>
            {participants.slice(0, 2).map((p) => (
              <button key={p.id} aria-pressed={sender === p.id} onClick={() => setSender(p.id)}>{nameOf(p.id)}</button>
            ))}
          </div>
        )}
      </div>

      {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
      {list.items.length === 0 && list.loading && <SkeletonCards n={3} h={170} />}
      {!list.loading && !list.error && list.items.length === 0 && (
        <Empty glyph="声">{filter === "fav" ? t("favorites.empty") : t("sounds.empty")}</Empty>
      )}

      {list.items.map((m) => {
        const playing = player.current?.id === m.id;
        return (
          <article key={m.id} className={`sound-card ${playing ? "playing" : ""}`} aria-label={`${m.day ?? ""} ${m.title ?? ""}`}>
            <div className="row between" style={{ alignItems: "flex-start", marginBottom: 12 }}>
              <div className="row" style={{ minWidth: 0 }}>
                <Avatar senderId={m.sender_id} />
                <div style={{ minWidth: 0 }}>
                  <Link to={`/day/${m.day}`} className="small" style={{ fontWeight: 500 }}>
                    {m.day ? formatDay(m.day, lang, settings?.date_format) : ""}
                  </Link>
                  <div className="tiny muted">
                    {m.sender_id ? nameOf(m.sender_id) : t("common.unknownSender")} · {formatTime(m.ts)}
                  </div>
                </div>
              </div>
              <FavButton on={m.favorite} onToggle={() => toggleFav(m)} />
            </div>

            <button type="button" onClick={() => setEdit(m)} style={{ textAlign: "left", width: "100%" }}
              aria-label={m.title ? `${t("common.edit")}: ${m.title}` : t("sounds.addTitle")}>
              {m.title ? <h3 className="title">{m.title}</h3> : <p className="title placeholder">+ {t("sounds.addTitle")}</p>}
            </button>

            <div style={{ marginTop: 10 }}>
              <VoicePlayer media={m} queue={list.items} />
            </div>
            {!m.playable && <p className="tiny muted" style={{ margin: "6px 0 0" }}>{t("sounds.unplayable")}</p>}
            {m.note && <p className="note">{m.note}</p>}

            {m.context && m.context.length > 0 && (
              <div className="ctx" aria-label={t("sounds.context")}>
                {m.context.map((c) => (
                  <p key={c.id}>
                    <span className="tiny">{nameOf(c.sender_id)} {formatTime(c.ts)}</span>　{c.text}
                  </p>
                ))}
              </div>
            )}
          </article>
        );
      })}

      <div ref={list.sentinel} />
      {list.loading && list.items.length > 0 && <Loading />}

      <EditSheet media={edit} onClose={() => setEdit(null)} onSaved={(m) => { update(m); setEdit(null); }} />
    </div>
  );
}

function EditSheet({ media, onClose, onSaved }: { media: Media | null; onClose: () => void; onSaved: (m: Media) => void }) {
  const { t } = useApp();
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastId, setLastId] = useState<number | null>(null);
  if (media && media.id !== lastId) {
    setLastId(media.id);
    setTitle(media.title ?? "");
    setNote(media.note ?? "");
  }
  const save = async () => {
    if (!media) return;
    setBusy(true);
    try {
      onSaved(await api.patchMedia(media.id, { title, note }));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet open={!!media} onClose={onClose} title={t("sounds.addTitle")} labelledBy="edit-sound">
      <label className="field">
        <span>{t("moments.title")}</span>
        <input className="input" value={title} maxLength={120} placeholder={t("sounds.titlePlaceholder")}
          onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="field">
        <span>{t("sounds.addNote")}</span>
        <textarea className="textarea" value={note} maxLength={4000} onChange={(e) => setNote(e.target.value)} />
      </label>
      <button className="btn accent block" onClick={save} disabled={busy}>{t("common.save")}</button>
    </Sheet>
  );
}
