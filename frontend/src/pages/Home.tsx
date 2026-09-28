import { Link } from "react-router-dom";
import { Empty, ErrorBox, SkeletonCards } from "../components/common";
import {
  IconBook,
  IconChart,
  IconImage,
  IconNext,
  IconSearch,
  IconSettings,
  IconShuffle,
  IconSparkle,
  IconStar,
  IconTimeline,
  IconWave,
} from "../components/Icons";
import { api } from "../lib/api";
import { agoText, daysBetween, formatDay, num, toDayString } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useApp } from "../lib/store";

export default function Home() {
  const { t, lang, copy, settings, nameOf } = useApp();
  const ov = useAsync(() => api.overview(), []);
  const years = useAsync(() => api.years(), []);

  if (ov.error) return <div className="page"><ErrorBox error={ov.error} onRetry={ov.reload} /></div>;
  if (!ov.data || !copy) return <div className="page"><SkeletonCards n={3} h={160} /></div>;
  const o = ov.data;

  if (!o.has_data) {
    return (
      <div className="page">
        <header className="page-header">
          <div className="eyebrow">{copy.museumSubtitleEn}</div>
          <h1>{copy.museumTitle}</h1>
        </header>
        <Empty glyph="馆" title={t("empty.title")}>
          {copy.emptyMuseum}
        </Empty>
        <pre className="card flat small" style={{ whiteSpace: "pre-wrap", fontFamily: "var(--mono)" }}>
          python -m memory_museum import --chat private-data/chat --media private-data/media
        </pre>
      </div>
    );
  }

  const cover =
    o.cover ?? years.data?.flatMap((y) => y.months).find((m) => m.cover)?.cover ?? null;
  const names = o.participants.slice(0, 2).map((p) => nameOf(p.id));
  const start = settings?.relationship_start;
  const today = toDayString(new Date());

  return (
    <div className="page">
      <header className="page-header">
        <div className="eyebrow">{copy.museumTitle}</div>
        <h1>{names.join(lang === "en" ? " & " : " 和 ")}</h1>
        {o.totals.first_day && o.totals.last_day && (
          <p>
            {t("home.since", {
              first: formatDay(o.totals.first_day, lang, settings?.date_format),
              last: formatDay(o.totals.last_day, lang, settings?.date_format),
            })}
            {start && ` · ${t("random.together", { n: daysBetween(start, today) + 1 })}`}
          </p>
        )}
        <p className="small row wrap" style={{ gap: "2px 10px" }}>
          {[
            t("common.days", { n: num(o.totals.days, lang) }),
            t("common.messages", { n: num(o.totals.messages, lang) }),
            t("common.photos", { n: num(o.totals.photos, lang) }),
            t("common.voices", { n: num(o.totals.voices, lang) }),
          ].map((x) => (
            <span key={x} style={{ whiteSpace: "nowrap" }}>{x}</span>
          ))}
        </p>
      </header>

      <Link to="/random" className="hero-random" aria-label={t("random.title")}>
        {cover && <div className="bg" style={{ backgroundImage: `url(${cover})` }} aria-hidden />}
        <div className="dice" aria-hidden>
          <IconShuffle width={22} height={22} />
        </div>
        <h2>{copy.randomDayTitle}</h2>
        <p>{t("home.randomHint")}</p>
      </Link>

      {o.on_this_day.length > 0 && (
        <section className="section" aria-labelledby="otd">
          <h2 className="section-title" id="otd">
            {t("home.onThisDay")}
          </h2>
          <div className="otd">
            {o.on_this_day.map((d) => (
              <Link key={d.day} to={`/day/${d.day}`}>
                <div style={{ fontFamily: "var(--serif)", fontSize: 18 }}>{d.day.slice(0, 4)}</div>
                <div className="tiny muted">{agoText(d.day, lang)}</div>
                <div className="tiny muted" style={{ marginTop: 6 }}>
                  {t("common.messages", { n: d.msg_count })}
                  {d.photo_count > 0 && ` · ${t("common.photos", { n: d.photo_count })}`}
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section className="section" aria-labelledby="explore">
        <h2 className="section-title" id="explore">
          {t("home.explore")}
        </h2>
        <div className="tiles">
          <Link to="/sounds" className="tile">
            <IconWave />
            <div>
              <b>{copy.soundMuseumTitle}</b>
              <small>{t("common.voices", { n: num(o.totals.voices, lang) })}</small>
            </div>
          </Link>
          <Link to="/gallery" className="tile">
            <IconImage />
            <div>
              <b>{copy.galleryTitle}</b>
              <small>{t("common.photos", { n: num(o.totals.photos, lang) })}</small>
            </div>
          </Link>
          <Link to="/timeline" className="tile">
            <IconTimeline />
            <div>
              <b>{copy.timelineTitle}</b>
              <small>{t("common.messages", { n: num(o.totals.messages, lang) })}</small>
            </div>
          </Link>
          <Link to="/moments" className="tile">
            <IconSparkle />
            <div>
              <b>{copy.momentsTitle}</b>
              <small>&nbsp;</small>
            </div>
          </Link>
          <Link to="/favorites" className="tile">
            <IconStar />
            <div>
              <b>{copy.favoritesTitle}</b>
              <small>&nbsp;</small>
            </div>
          </Link>
          <Link to="/stats" className="tile">
            <IconChart />
            <div>
              <b>{copy.statsTitle}</b>
              <small>&nbsp;</small>
            </div>
          </Link>
        </div>
      </section>

      <section className="section card" style={{ padding: "4px 16px" }}>
        <Link to="/search" className="list-link">
          <IconSearch width={20} className="muted" />
          <span className="grow">{t("home.search")}</span>
          <IconNext width={18} className="chev" />
        </Link>
        <Link to="/review" className="list-link">
          <IconBook width={20} className="muted" />
          <span className="grow">{t("home.review")}</span>
          <IconNext width={18} className="chev" />
        </Link>
        <Link to="/settings" className="list-link">
          <IconSettings width={20} className="muted" />
          <span className="grow">{t("home.settings")}</span>
          <IconNext width={18} className="chev" />
        </Link>
      </section>
      <p className="tiny muted" style={{ textAlign: "center", marginTop: 28 }}>
        {copy.footer}
      </p>
    </div>
  );
}
