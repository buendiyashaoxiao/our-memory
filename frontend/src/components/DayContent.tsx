import { useState } from "react";
import { Link } from "react-router-dom";
import { formatDuration, formatTime } from "../lib/format";
import { useApp } from "../lib/store";
import type { DayDetail, Media } from "../lib/types";
import { Avatar } from "./common";
import { Lightbox } from "./Lightbox";
import { Thumb } from "./Thumb";
import { VoicePlayer } from "./VoicePlayer";

export function DayStats({ d }: { d: DayDetail }) {
  const { t, lang } = useApp();
  const s = d.stats;
  const cells: { v: string; k: string }[] = [];
  if (s.messages) cells.push({ v: String(s.messages), k: lang === "en" ? "messages" : "条消息" });
  if (s.photos) cells.push({ v: String(s.photos), k: lang === "en" ? "photos" : "张照片" });
  if (s.videos) cells.push({ v: String(s.videos), k: lang === "en" ? "videos" : "段视频" });
  if (s.voices) cells.push({ v: String(s.voices), k: lang === "en" ? `voices · ${formatDuration(s.audio_seconds)}` : `段语音 · ${formatDuration(s.audio_seconds)}` });
  if (!cells.length) return null;
  const notes: string[] = [];
  if (s.first_ts && s.last_ts && s.messages > 1)
    notes.push(t("day.span", { first: formatTime(s.first_ts), last: formatTime(s.last_ts) }));
  if (s.longest_session_minutes >= 10) notes.push(t("day.longest", { n: s.longest_session_minutes }));
  return (
    <>
      <div className="stat-row" style={{ gridTemplateColumns: `repeat(${cells.length}, 1fr)` }}>
        {cells.map((c) => (
          <div className="stat" key={c.k}>
            <b>{c.v}</b>
            <span>{c.k}</span>
          </div>
        ))}
      </div>
      {notes.length > 0 && (
        <p className="tiny muted" style={{ marginTop: 10 }}>
          {notes.join(" · ")}
        </p>
      )}
    </>
  );
}

export function DayMedia({ d }: { d: DayDetail }) {
  const { t, nameOf } = useApp();
  const [lb, setLb] = useState<{ items: Media[]; index: number } | null>(null);
  return (
    <>
      {d.moments.length > 0 && (
        <div className="row wrap" style={{ marginTop: 16, gap: 6 }}>
          {d.moments.map((m) => (
            <Link key={m.id} to={`/moments/${m.id}`} className="chip">
              {m.title}
            </Link>
          ))}
        </div>
      )}
      {d.media.length > 0 && (
        <section className="section" aria-labelledby="day-photos">
          <h2 className="section-title" id="day-photos">
            {t("day.photos")} <small>{d.media.length}</small>
          </h2>
          <div className="strip">
            {d.media.map((m, i) => (
              <Thumb key={m.id} media={m} showTime onOpen={() => setLb({ items: d.media, index: i })} />
            ))}
          </div>
        </section>
      )}
      {d.voices.length > 0 && (
        <section className="section" aria-labelledby="day-voices">
          <h2 className="section-title" id="day-voices">
            {t("day.voices")} <small>{d.voices.length}</small>
          </h2>
          <div className="card" style={{ padding: "8px 16px" }}>
            {d.voices.map((v) => (
              <div key={v.id} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
                <Avatar senderId={v.sender_id} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="tiny muted">
                    {v.sender_id ? nameOf(v.sender_id) : ""} {formatTime(v.ts)} {v.title && `· ${v.title}`}
                  </div>
                  <VoicePlayer media={v} queue={d.voices} size="sm" />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {lb && (
        <Lightbox items={lb.items} index={lb.index} onClose={() => setLb(null)} onIndex={(index) => setLb({ ...lb, index })}
          onChange={(m) => setLb({ ...lb, items: lb.items.map((x) => (x.id === m.id ? m : x)) })} />
      )}
    </>
  );
}
