import { useState } from "react";
import { formatDuration, formatTime } from "../lib/format";
import { useApp } from "../lib/store";
import type { Media } from "../lib/types";
import { IconPlay, IconStar } from "./Icons";

/** Lazy thumbnail that fades in, shows a video badge, and degrades gracefully when a file is missing. */
export function Thumb({ media, onOpen, eager = false, showTime = false }: {
  media: Media;
  onOpen?: (m: Media) => void;
  eager?: boolean;
  showTime?: boolean;
}) {
  const { t } = useApp();
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const src = media.thumb ?? (media.type === "image" ? media.url : null);
  const label =
    `${media.type === "video" ? t("gallery.videos") : t("gallery.photos")} ${media.day ?? ""} ${formatTime(media.ts)}`.trim() +
    (media.title ? ` · ${media.title}` : "");

  const inner =
    !src || failed ? (
      <span className="thumb broken">{media.type === "video" ? "▶" : t("day.missingMedia")}</span>
    ) : (
      <span className="thumb">
        <img
          src={src}
          alt={label}
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          className={loaded ? "loaded" : ""}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
        {media.type === "video" && (
          <span className="badge">
            <IconPlay />
            {formatDuration(media.duration)}
          </span>
        )}
        {showTime && media.type !== "video" && media.ts && <span className="badge">{formatTime(media.ts)}</span>}
        {media.favorite && (
          <span className="fav-dot">
            <IconStar filled />
          </span>
        )}
      </span>
    );

  if (!onOpen) return inner;
  return (
    <button type="button" className="thumb" aria-label={label} onClick={() => onOpen(media)} style={{ borderRadius: "inherit" }}>
      {inner}
    </button>
  );
}
