import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DateBlock, Empty, ErrorBox, FavButton, SkeletonCards } from "../components/common";
import { DayMedia, DayStats } from "../components/DayContent";
import { IconNext, IconPrev, IconShuffle } from "../components/Icons";
import { api } from "../lib/api";
import { agoText, daysBetween, formatTime, toDayString } from "../lib/format";
import { usePrefersReducedMotion } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { DayDetail } from "../lib/types";

export default function RandomDay() {
  const { t, lang, copy, settings, nameOf } = useApp();
  const [params, setParams] = useSearchParams();
  const [day, setDay] = useState<DayDetail | null>(null);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [phase, setPhase] = useState<"in" | "out">("in");
  const reduced = usePrefersReducedMotion();
  // Ignore responses that arrive after the user left the page or asked for another day.
  const generation = useRef(0);
  useEffect(() => () => {
    generation.current = -1;
  }, []);

  const show = useCallback(
    async (loader: () => Promise<DayDetail | { day: null }>) => {
      const mine = ++generation.current;
      const stale = () => generation.current !== mine;
      setError(null);
      if (!reduced) setPhase("out");
      const wait = reduced ? Promise.resolve() : new Promise((r) => setTimeout(r, 320));
      try {
        const [res] = await Promise.all([loader(), wait]);
        if (stale()) return;
        if (!res.day) {
          setEmpty(true);
          return;
        }
        const d = res as DayDetail;
        setDay(d);
        setParams({ day: d.day }, { replace: true });
        window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
      } catch (e) {
        if (!stale()) setError(e as Error);
      } finally {
        if (!stale()) setPhase("in");
      }
    },
    [reduced, setParams],
  );

  useEffect(() => {
    const initial = params.get("day");
    show(() => (initial ? api.day(initial) : api.randomDay()));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const again = () => show(() => api.randomDay(day?.day));
  const goTo = (target: string | null) => target && show(() => api.day(target));

  if (error) return <div className="page"><ErrorBox error={error} onRetry={again} /></div>;
  if (empty) return <div className="page"><Empty glyph="日">{t("random.empty")}</Empty></div>;

  const start = settings?.relationship_start;
  return (
    <div className="page">
      <header className="page-header" style={{ marginBottom: 18 }}>
        <div className="eyebrow">{copy?.randomDayTitle ?? t("random.title")}</div>
      </header>
      {!day ? (
        <SkeletonCards n={1} h={420} />
      ) : (
        <div className={`random-stage ${phase === "out" ? "out" : ""}`} key={day.day} aria-live="polite">
          <div className="row between" style={{ alignItems: "flex-start" }}>
            <DateBlock day={day.day} size="xl" />
            <FavButton on={day.favorite} onToggle={async () => {
              await api.setFavorite("day", day.day, !day.favorite);
              setDay({ ...day, favorite: !day.favorite });
            }} />
          </div>
          <div className="ago">
            {t("random.ago", { ago: agoText(day.day, lang) })}
            {start && day.day >= start && ` · ${t("random.together", { n: daysBetween(start, day.day) + 1 })}`}
          </div>
          <DayStats d={day} />

          {day.excerpts.length > 0 && (
            <section className="section card" aria-label={t("day.chat")}>
              <ul className="excerpts" style={{ margin: 0 }}>
                {day.excerpts.map((e) => (
                  <li key={e.id} style={{ fontSize: 16 }}>
                    <span className="who">{nameOf(e.sender_id)}</span>
                    {e.text}
                    <span className="t">{formatTime(e.ts)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <DayMedia d={day} />

          <div style={{ textAlign: "center", marginTop: 28 }}>
            <Link to={`/day/${day.day}`} className="btn line">
              {t("random.full")}
            </Link>
          </div>
        </div>
      )}

      <div className="action-bar" role="toolbar" aria-label={t("random.title")}>
        <button className="btn ghost small" onClick={() => goTo(day?.prev_day ?? null)} disabled={!day?.prev_day}
          style={{ paddingLeft: 10 }}>
          <IconPrev width={16} /> {t("day.prev")}
        </button>
        <button className="btn primary" onClick={again} disabled={phase === "out"}>
          <IconShuffle width={18} /> {t("random.again")}
        </button>
        <button className="btn ghost small" onClick={() => goTo(day?.next_day ?? null)}
          disabled={!day?.next_day || (day?.next_day ?? "") > toDayString(new Date())} style={{ paddingRight: 10 }}>
          {t("day.next")} <IconNext width={16} />
        </button>
      </div>
    </div>
  );
}
