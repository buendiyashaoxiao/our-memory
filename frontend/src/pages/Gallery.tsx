import { Fragment, useState } from "react";
import { Empty, ErrorBox, Loading, PageHeader, Segmented } from "../components/common";
import { IconStar } from "../components/Icons";
import { Lightbox } from "../components/Lightbox";
import { Thumb } from "../components/Thumb";
import { api } from "../lib/api";
import { formatMonth } from "../lib/format";
import { useAsync, useInfinite } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Media } from "../lib/types";

export default function Gallery() {
  const { t, lang, copy } = useApp();
  const [kind, setKind] = useState<"all" | "image" | "video">("all");
  const [month, setMonth] = useState<string | null>(null);
  const [favorites, setFavorites] = useState(false);
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [open, setOpen] = useState<number | null>(null);
  const months = useAsync(() => api.galleryMonths(), []);

  const list = useInfinite<Media>(
    (cursor) => api.gallery({ cursor, kind, month, favorites, order, limit: 60 }),
    [kind, month, favorites, order],
  );

  const groups: { month: string; items: { m: Media; i: number }[] }[] = [];
  list.items.forEach((m, i) => {
    const key = (m.day ?? "").slice(0, 7);
    const last = groups[groups.length - 1];
    if (last && last.month === key) last.items.push({ m, i });
    else groups.push({ month: key, items: [{ m, i }] });
  });

  return (
    <div className="page wide">
      <PageHeader
        title={copy?.galleryTitle ?? t("nav.gallery")}
        right={
          <Segmented label={t("nav.gallery")} value={kind} onChange={setKind}
            options={[
              { value: "all", label: t("gallery.all") },
              { value: "image", label: t("gallery.photos") },
              { value: "video", label: t("gallery.videos") },
            ]} />
        }
      />
      <div className="chips" role="group" aria-label="month" style={{ marginBottom: 8 }}>
        <button className="chip" aria-pressed={favorites} onClick={() => setFavorites(!favorites)}>
          <IconStar filled={favorites} width={14} /> {t("nav.favorites")}
        </button>
        <button className="chip" onClick={() => setOrder(order === "asc" ? "desc" : "asc")}>
          {order === "desc" ? "↑ " + t("timeline.newest") : "↓ " + t("timeline.oldest")}
        </button>
        <button className="chip" aria-pressed={month === null} onClick={() => setMonth(null)}>{t("timeline.allYears")}</button>
        {(months.data ?? []).map((m) => (
          <button key={m.month} className="chip" aria-pressed={month === m.month} onClick={() => setMonth(month === m.month ? null : m.month)}>
            {formatMonth(m.month, lang)} <span className="tiny muted">{m.photos + m.videos}</span>
          </button>
        ))}
      </div>

      {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
      {!list.loading && !list.error && list.items.length === 0 && (
        <Empty glyph="影">{favorites ? t("favorites.empty") : t("gallery.empty")}</Empty>
      )}

      {groups.map((g) => (
        <Fragment key={g.month}>
          <div className="month-head">
            <h2>{g.month ? formatMonth(g.month, lang) : "—"}</h2>
          </div>
          <div className="grid">
            {g.items.map(({ m, i }) => (
              <Thumb key={m.id} media={m} onOpen={() => setOpen(i)} />
            ))}
          </div>
        </Fragment>
      ))}
      <div ref={list.sentinel} />
      {list.loading && <Loading />}

      {open !== null && (
        <Lightbox items={list.items} index={open} onClose={() => setOpen(null)} onIndex={setOpen}
          onChange={(m) => list.setItems((items) => items.map((x) => (x.id === m.id ? m : x)))} />
      )}
    </div>
  );
}
