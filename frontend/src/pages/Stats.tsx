import { Link } from "react-router-dom";
import { ErrorBox, PageHeader, SkeletonCards } from "../components/common";
import { api } from "../lib/api";
import { formatDay, formatDurationLong, formatMonth, hourLabel, num } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useApp } from "../lib/store";

export default function StatsPage() {
  const { t, lang, copy, nameOf, settings } = useApp();
  const s = useAsync(() => api.stats(), []);
  if (s.error) return <div className="page"><ErrorBox error={s.error} onRetry={s.reload} /></div>;
  if (!s.data) return <div className="page"><SkeletonCards n={3} h={150} /></div>;
  const d = s.data;
  const fd = (day: string) => formatDay(day, lang, settings?.date_format);
  const maxHour = Math.max(1, ...d.hours);
  const maxMonth = Math.max(1, ...d.months.map((m) => m.messages));
  const weekNames = lang === "en" ? ["M", "T", "W", "T", "F", "S", "S"] : ["一", "二", "三", "四", "五", "六", "日"];
  const maxWeek = Math.max(1, ...d.weekdays);

  const big: { v: string; k: string }[] = [
    { v: num(d.totals.days, lang), k: t("stats.days") },
    { v: num(d.totals.messages, lang), k: t("stats.messages") },
    { v: num(d.totals.photos, lang), k: t("stats.photos") },
    { v: num(d.totals.voices, lang), k: t("stats.voices") },
  ];
  if (d.totals.videos) big.push({ v: num(d.totals.videos, lang), k: t("stats.videos") });

  return (
    <div className="page">
      <PageHeader title={copy?.statsTitle ?? t("home.stats")} sub={copy?.statsIntro} />

      <div className="stat" style={{ padding: "18px 20px" }}>
        <b className="big-number">{big[0].v}</b>
        <span>{big[0].k}</span>
      </div>
      <div className="stat-row" style={{ marginTop: 10, gridTemplateColumns: `repeat(${big.length - 1}, 1fr)` }}>
        {big.slice(1).map((b) => (
          <div className="stat" key={b.k}>
            <b>{b.v}</b>
            <span>{b.k}</span>
          </div>
        ))}
      </div>

      <section className="section card">
        {d.totals.voice_seconds > 0 && (
          <div className="fact">
            <div className="k">{t("stats.voiceTime")}</div>
            <div className="v">{formatDurationLong(d.totals.voice_seconds, lang)}</div>
          </div>
        )}
        {d.busiest_day && (
          <Link to={`/day/${d.busiest_day.day}`} className="fact" style={{ display: "block" }}>
            <div className="k">{t("stats.busiestDay")}</div>
            <div className="v">{fd(d.busiest_day.day)} · {t("common.messages", { n: d.busiest_day.value })}</div>
          </Link>
        )}
        {d.busiest_month && (
          <div className="fact">
            <div className="k">{t("stats.busiestMonth")}</div>
            <div className="v">{formatMonth(d.busiest_month.month, lang)} · {t("common.messages", { n: num(d.busiest_month.messages, lang) })}</div>
          </div>
        )}
        {d.peak_hour !== null && (
          <div className="fact">
            <div className="k">{t("stats.peakHour")}</div>
            <div className="v">{hourLabel(d.peak_hour, lang)} – {hourLabel((d.peak_hour + 1) % 24, lang)}</div>
          </div>
        )}
        {d.longest_conversation_day && (
          <Link to={`/day/${d.longest_conversation_day.day}`} className="fact" style={{ display: "block" }}>
            <div className="k">{t("stats.longestConversation")}</div>
            <div className="v">{fd(d.longest_conversation_day.day)} · {t("common.minutes", { n: d.longest_conversation_day.value })}</div>
          </Link>
        )}
        {d.most_photos_day && (
          <Link to={`/day/${d.most_photos_day.day}`} className="fact" style={{ display: "block" }}>
            <div className="k">{t("stats.mostPhotos")}</div>
            <div className="v">{fd(d.most_photos_day.day)} · {t("common.photos", { n: d.most_photos_day.value })}</div>
          </Link>
        )}
        {d.longest_voice && (
          <Link to={`/day/${d.longest_voice.day}`} className="fact" style={{ display: "block" }}>
            <div className="k">{t("stats.longestVoice")}</div>
            <div className="v">{fd(d.longest_voice.day)} · {formatDurationLong(d.longest_voice.duration, lang)}</div>
          </Link>
        )}
        {d.first_message && (
          <Link to={`/day/${d.first_message.day}`} className="fact" style={{ display: "block" }}>
            <div className="k">{t("stats.firstMessage")} · {fd(d.first_message.day)}</div>
            <div className="v">「{d.first_message.text}」<span className="small muted"> — {nameOf(d.first_message.sender_id)}</span></div>
          </Link>
        )}
      </section>

      <section className="section">
        <h2 className="section-title">{t("stats.hours")}</h2>
        <div className="bars" role="img" aria-label={t("stats.hours")}>
          {d.hours.map((v, h) => (
            <div key={h} className={`b ${h === d.peak_hour ? "peak" : ""}`} title={`${hourLabel(h, lang)}: ${v}`}>
              <i style={{ height: `${(v / maxHour) * 100}%` }} />
              <small>{h % 6 === 0 ? h : ""}</small>
            </div>
          ))}
        </div>
      </section>

      {d.months.length > 1 && (
        <section className="section">
          <h2 className="section-title">{t("stats.months")}</h2>
          <div className="bars" role="img" aria-label={t("stats.months")}>
            {d.months.map((m) => (
              <div key={m.month} className={`b ${m.month === d.busiest_month?.month ? "peak" : ""}`} title={`${m.month}: ${m.messages}`}>
                <i style={{ height: `${(m.messages / maxMonth) * 100}%` }} />
                <small>{Number(m.month.slice(5))}</small>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="section">
        <h2 className="section-title">{t("stats.weekdays")}</h2>
        <div className="bars" style={{ height: 80 }} role="img" aria-label={t("stats.weekdays")}>
          {d.weekdays.map((v, i) => (
            <div key={i} className="b" title={`${weekNames[i]}: ${v}`}>
              <i style={{ height: `${(v / maxWeek) * 100}%` }} />
              <small>{weekNames[i]}</small>
            </div>
          ))}
        </div>
      </section>

      {d.by_sender.length > 0 && (
        <section className="section">
          <h2 className="section-title">{t("stats.bySender")}</h2>
          {d.by_sender.slice(0, 4).map((b) => (
            <div key={b.sender_id} style={{ marginBottom: 12 }}>
              <div className="row between small">
                <span>{nameOf(b.sender_id)}</span>
                <span className="muted">{num(b.messages, lang)}</span>
              </div>
              <div className="wave flat" style={{ marginTop: 6 }}>
                <span className="fill" style={{ width: `${(b.messages / Math.max(1, d.totals.messages)) * 100}%` }} />
              </div>
            </div>
          ))}
        </section>
      )}

      {d.words.words.length > 0 && (
        <section className="section">
          <h2 className="section-title">{t("stats.words")}</h2>
          <div className="words">
            {d.words.words.slice(0, 30).map(([w, n]) => (
              <span key={w}>{w}<small>{n}</small></span>
            ))}
          </div>
          <p className="tiny muted" style={{ marginTop: 12 }}>
            {d.words.method === "jieba" ? t("stats.wordsNote.jieba") : t("stats.wordsNote.bigram")}
          </p>
        </section>
      )}
      {d.words.emojis.length > 0 && (
        <section className="section">
          <h2 className="section-title">{t("stats.emojis")}</h2>
          <div className="words">
            {d.words.emojis.map(([e, n]) => (
              <span key={e} style={{ fontSize: 18 }}>{e}<small>{n}</small></span>
            ))}
          </div>
          {d.words.laugh_messages > 0 && (
            <p className="small muted" style={{ marginTop: 12 }}>{t("stats.laughs", { n: num(d.words.laugh_messages, lang) })}</p>
          )}
        </section>
      )}
    </div>
  );
}
