import { Fragment, useState } from "react";
import { DayCard } from "../components/DayCard";
import { Empty, ErrorBox, Loading, PageHeader, Segmented, SkeletonCards } from "../components/common";
import { Lightbox } from "../components/Lightbox";
import { api } from "../lib/api";
import { formatMonth, monthName, num } from "../lib/format";
import { useAsync, useInfinite } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { DayCardData, Media } from "../lib/types";

export default function Timeline() {
  const { t, lang, copy } = useApp();
  const [mode, setMode] = useState<"curated" | "all">("curated");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [year, setYear] = useState<number | null>(null);
  const [month, setMonth] = useState<number | null>(null);
  const [lb, setLb] = useState<{ items: Media[]; index: number } | null>(null);
  const years = useAsync(() => api.years(), []);

  const list = useInfinite<DayCardData>(
    (cursor) => api.timeline({ cursor, mode, order, year: year ?? undefined, month: month ?? undefined, limit: 8 }),
    [mode, order, year, month],
  );

  const toggleFav = async (d: DayCardData) => {
    await api.setFavorite("day", d.day, !d.favorite);
    list.setItems((items) => items.map((x) => (x.day === d.day ? { ...x, favorite: !x.favorite } : x)));
  };

  const selectedYear = years.data?.find((y) => y.year === year);
  let lastMonth = "";

  return (
    <div className="page">
      <PageHeader
        title={copy?.timelineTitle ?? t("nav.timeline")}
        right={
          <Segmented
            label={t("nav.timeline")}
            value={mode}
            onChange={setMode}
            options={[
              { value: "curated", label: t("timeline.curated") },
              { value: "all", label: t("timeline.all") },
            ]}
          />
        }
      />

      {years.data && years.data.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div className="chips" role="group" aria-label="year">
            <button className="chip" aria-pressed={year === null} onClick={() => (setYear(null), setMonth(null))}>
              {t("timeline.allYears")}
            </button>
            {years.data.map((y) => (
              <button key={y.year} className="chip" aria-pressed={year === y.year} onClick={() => (setYear(y.year), setMonth(null))}>
                {y.year}
              </button>
            ))}
            <button className="chip" onClick={() => setOrder(order === "asc" ? "desc" : "asc")} aria-label={order === "asc" ? t("timeline.oldest") : t("timeline.newest")}>
              {order === "asc" ? "↓ " + t("timeline.oldest") : "↑ " + t("timeline.newest")}
            </button>
          </div>
          {selectedYear && (
            <div className="chips" role="group" aria-label="month" style={{ marginTop: 8 }}>
              {selectedYear.months.map((m) => (
                <button key={m.month} className="chip" aria-pressed={month === m.month}
                  onClick={() => setMonth(month === m.month ? null : m.month)}>
                  {monthName(m.month, lang)}
                  <span className="tiny muted">{num(m.memory_days)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
      {!list.error && list.items.length === 0 && list.loading && <SkeletonCards n={2} h={380} />}
      {!list.loading && !list.error && list.items.length === 0 && <Empty glyph="日">{copy?.emptyMuseum}</Empty>}

      {list.items.map((d) => {
        const ym = d.day.slice(0, 7);
        const head = ym !== lastMonth;
        lastMonth = ym;
        return (
          <Fragment key={d.day}>
            {head && <div className="year-mark">{formatMonth(ym, lang)}</div>}
            <DayCard data={d} onToggleFavorite={() => toggleFav(d)}
              onOpenMedia={(items, index) => setLb({ items, index })} />
          </Fragment>
        );
      })}

      <div ref={list.sentinel} />
      {list.loading && list.items.length > 0 && <Loading />}
      {list.done && list.items.length > 0 && <p className="loading-line">{t("timeline.end")}</p>}

      {lb && (
        <Lightbox items={lb.items} index={lb.index} onClose={() => setLb(null)}
          onIndex={(index) => setLb({ ...lb, index })}
          onChange={(m) => setLb({ ...lb, items: lb.items.map((x) => (x.id === m.id ? m : x)) })} />
      )}
    </div>
  );
}
