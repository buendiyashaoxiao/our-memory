import { useState } from "react";
import { Link } from "react-router-dom";
import { DayCard } from "../components/DayCard";
import { Empty, ErrorBox, FavButton, PageHeader, SkeletonCards } from "../components/common";
import { Lightbox } from "../components/Lightbox";
import { Thumb } from "../components/Thumb";
import { VoicePlayer } from "../components/VoicePlayer";
import { api } from "../lib/api";
import { formatDay, formatTime } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { DayCardData, Favorite, FavoriteKind, Media, Message, Moment } from "../lib/types";

const KINDS: FavoriteKind[] = ["day", "media", "message", "moment"];

export default function Favorites() {
  const { t, lang, copy, nameOf, settings } = useApp();
  const [kind, setKind] = useState<FavoriteKind | null>(null);
  const favs = useAsync(() => api.favorites(kind ?? undefined), [kind]);
  const [lb, setLb] = useState<{ items: Media[]; index: number } | null>(null);

  const remove = async (f: Favorite) => {
    await api.setFavorite(f.kind, f.ref, false);
    favs.setData((d) => (d ? d.filter((x) => !(x.kind === f.kind && x.ref === f.ref)) : d));
  };

  const label: Record<FavoriteKind, string> = {
    day: t("favorites.days"),
    media: t("favorites.media"),
    message: t("favorites.messages"),
    moment: t("favorites.moments"),
  };

  const items = favs.data ?? [];
  const visual = items.filter((f) => f.kind === "media" && ["image", "video"].includes((f.item as Media).type)).map((f) => f.item as Media);

  return (
    <div className="page">
      <PageHeader title={copy?.favoritesTitle ?? t("nav.favorites")} />
      <div className="chips" role="group" aria-label="kind" style={{ marginBottom: 18 }}>
        <button className="chip" aria-pressed={kind === null} onClick={() => setKind(null)}>{t("timeline.allYears")}</button>
        {KINDS.map((k) => (
          <button key={k} className="chip" aria-pressed={kind === k} onClick={() => setKind(k)}>{label[k]}</button>
        ))}
      </div>
      {favs.error && <ErrorBox error={favs.error} onRetry={favs.reload} />}
      {favs.loading && !favs.data && <SkeletonCards n={2} h={200} />}
      {favs.data && items.length === 0 && <Empty glyph="☆">{t("favorites.empty")}</Empty>}

      {visual.length > 0 && (
        <div className="grid" style={{ marginBottom: 20, borderRadius: 14, overflow: "hidden" }}>
          {visual.map((m, i) => <Thumb key={m.id} media={m} onOpen={() => setLb({ items: visual, index: i })} />)}
        </div>
      )}

      {items.map((f) => {
        if (f.kind === "day") {
          return <DayCard key={`d${f.ref}`} data={f.item as DayCardData} onToggleFavorite={() => remove(f)} />;
        }
        if (f.kind === "media") {
          const m = f.item as Media;
          if (m.type === "image" || m.type === "video") return null;
          return (
            <div key={`m${f.ref}`} className="sound-card">
              <div className="row between">
                <div>
                  {m.title && <h3 className="title">{m.title}</h3>}
                  <div className="tiny muted">
                    {m.day && formatDay(m.day, lang, settings?.date_format)} {formatTime(m.ts)} {m.sender_id && `· ${nameOf(m.sender_id)}`}
                  </div>
                </div>
                <FavButton on onToggle={() => remove(f)} />
              </div>
              <div style={{ marginTop: 10 }}><VoicePlayer media={m} /></div>
            </div>
          );
        }
        if (f.kind === "message") {
          const m = f.item as Message;
          return (
            <div key={`t${f.ref}`} className="card" style={{ marginBottom: 14 }}>
              <div className="row between">
                <Link to={`/day/${m.day}`} className="tiny muted">
                  {nameOf(m.sender_id)} · {m.day && formatDay(m.day, lang, settings?.date_format)} {formatTime(m.ts)}
                </Link>
                <FavButton on onToggle={() => remove(f)} />
              </div>
              <p style={{ margin: "4px 0 0", fontFamily: "var(--serif)", fontSize: 17, whiteSpace: "pre-wrap" }}>{m.text}</p>
            </div>
          );
        }
        const mo = f.item as Moment;
        return (
          <Link key={`o${f.ref}`} to={`/moments/${mo.id}`} className="card" style={{ display: "block", marginBottom: 14 }}>
            <div className="tiny muted">{mo.start_day && formatDay(mo.start_day, lang, settings?.date_format)}</div>
            <div style={{ fontFamily: "var(--serif)", fontSize: 18 }}>{mo.title}</div>
          </Link>
        );
      })}

      {lb && (
        <Lightbox items={lb.items} index={lb.index} onClose={() => { setLb(null); favs.reload(); }}
          onIndex={(index) => setLb({ ...lb, index })}
          onChange={(m) => setLb({ ...lb, items: lb.items.map((x) => (x.id === m.id ? m : x)) })} />
      )}
    </div>
  );
}
