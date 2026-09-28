import { Link } from "react-router-dom";
import { formatTime } from "../lib/format";
import { useApp } from "../lib/store";
import type { DayCardData, Media } from "../lib/types";
import { DateBlock, FavButton } from "./common";
import { IconCamera, IconChat, IconMic, IconVideo } from "./Icons";
import { Thumb } from "./Thumb";
import { VoicePlayer } from "./VoicePlayer";

export function DayMeta({ stats }: { stats: DayCardData["stats"] }) {
  const { t } = useApp();
  return (
    <div className="meta-line">
      {stats.messages > 0 && (
        <span>
          <IconChat />
          {t("common.messages", { n: stats.messages })}
        </span>
      )}
      {stats.photos > 0 && (
        <span>
          <IconCamera />
          {t("common.photos", { n: stats.photos })}
        </span>
      )}
      {stats.videos > 0 && (
        <span>
          <IconVideo />
          {t("common.videos", { n: stats.videos })}
        </span>
      )}
      {stats.voices > 0 && (
        <span>
          <IconMic />
          {t("common.voices", { n: stats.voices })}
        </span>
      )}
    </div>
  );
}

export function DayCard({ data, onOpenMedia, onToggleFavorite }: {
  data: DayCardData;
  onOpenMedia?: (items: Media[], index: number) => void;
  onToggleFavorite?: () => void;
}) {
  const { nameOf, t } = useApp();
  const visual = data.media.slice(0, 6);
  return (
    <article className="day-card" aria-labelledby={`day-${data.day}`}>
      {visual.length > 0 && (
        <div className={`mosaic n${visual.length}`}>
          {visual.map((m, i) => (
            <Thumb key={m.id} media={m} onOpen={onOpenMedia ? () => onOpenMedia(data.media, i) : undefined} />
          ))}
        </div>
      )}
      <div className="day-card-body">
        <div className="date-row">
          <Link to={`/day/${data.day}`} id={`day-${data.day}`} aria-label={`${t("timeline.fullDay")} ${data.day}`}>
            <DateBlock day={data.day} />
          </Link>
          {onToggleFavorite && <FavButton on={data.favorite} onToggle={onToggleFavorite} />}
        </div>
        {data.moments.length > 0 && (
          <div className="row wrap" style={{ marginTop: 10, gap: 6 }}>
            {data.moments.map((mo) => (
              <Link key={mo.id} to={`/moments/${mo.id}`} className="chip" style={{ minHeight: 28 }}>
                {mo.title}
              </Link>
            ))}
          </div>
        )}
        {data.excerpts.length > 0 && (
          <ul className="excerpts">
            {data.excerpts.map((e) => (
              <li key={e.id}>
                <span className="who">{nameOf(e.sender_id)}</span>
                {e.text}
                <span className="t">{formatTime(e.ts)}</span>
              </li>
            ))}
          </ul>
        )}
        {data.voices.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <VoicePlayer media={data.voices[0]} queue={data.voices} />
          </div>
        )}
        <div className="row between" style={{ marginTop: 16 }}>
          <DayMeta stats={data.stats} />
          <Link to={`/day/${data.day}`} className="btn small ghost">
            {t("timeline.fullDay")}
          </Link>
        </div>
      </div>
    </article>
  );
}
