import { Fragment, type CSSProperties } from "react";
import { formatTime } from "../lib/format";
import { useApp } from "../lib/store";
import type { Media, Message } from "../lib/types";
import { Avatar } from "./common";
import { Thumb } from "./Thumb";
import { VoicePlayer } from "./VoicePlayer";

const GAP_MINUTES = 20;

function minutes(ts: string | null): number {
  if (!ts) return 0;
  return new Date(ts).getTime() / 60000;
}

export function MessageList({ messages, onOpenMedia, onAction, highlightId, voiceQueue }: {
  messages: Message[];
  onOpenMedia?: (m: Media) => void;
  onAction?: (m: Message) => void;
  highlightId?: number | null;
  voiceQueue?: Media[];
}) {
  const { t, isSelf, nameOf } = useApp();
  return (
    <div className="chat">
      {messages.map((m, i) => {
        const prev = messages[i - 1];
        const gap = !prev || minutes(m.ts) - minutes(prev.ts) > GAP_MINUTES;
        const first = gap || prev.sender_id !== m.sender_id || prev.type === "system";
        const self = isSelf(m.sender_id);
        const sep = gap && m.ts ? <div className="time-sep">{formatTime(m.ts)}</div> : null;

        if (m.type === "system") {
          return (
            <Fragment key={m.id}>
              {sep}
              <div className="msg-system">{m.text}</div>
            </Fragment>
          );
        }

        let body;
        let mediaBubble = false;
        if (m.type === "image" || m.type === "video") {
          if (m.media && m.media.status === "ok") {
            mediaBubble = true;
            const ar = m.media.width && m.media.height ? `${m.media.width} / ${m.media.height}` : undefined;
            body = (
              <span style={ar ? ({ "--ar": ar } as CSSProperties) : undefined}>
                <Thumb media={m.media} onOpen={onOpenMedia} />
              </span>
            );
          } else {
            body = (
              <span className="muted small">
                {m.type === "image" ? "[图片]" : "[视频]"} {t("day.missingMedia")}
              </span>
            );
          }
        } else if (m.type === "voice" || m.type === "audio") {
          body =
            m.media && m.media.status === "ok" ? (
              <span style={{ display: "block", width: 220, maxWidth: "100%" }}>
                <VoicePlayer media={m.media} queue={voiceQueue} size="sm" />
              </span>
            ) : (
              <span className="muted small">
                [语音{m.duration ? ` ${m.duration}″` : ""}] {t("day.missingMedia")}
              </span>
            );
        } else if (m.type === "sticker") {
          body = <span className="muted">{t("day.sticker")}</span>;
        } else if (m.type === "file") {
          body = <span className="muted">{t("day.file")} {m.media_ref ?? m.text}</span>;
        } else if (m.type === "unknown") {
          body = <span className="muted">{m.text ?? t("day.unknownType")}</span>;
        } else {
          body = m.text;
        }

        const clickable = !!onAction && !mediaBubble && m.type !== "voice";
        return (
          <Fragment key={m.id}>
            {sep}
            <div className={`msg ${self ? "self" : ""} ${first ? "first" : ""}`} data-message-id={m.id}>
              <Avatar senderId={m.sender_id} />
              <div
                className={`bubble ${mediaBubble ? "media" : ""} ${m.favorite ? "fav" : ""} ${highlightId === m.id ? "highlight" : ""}`}
                role={clickable ? "button" : undefined}
                tabIndex={clickable ? 0 : undefined}
                aria-label={clickable ? `${nameOf(m.sender_id)} ${formatTime(m.ts)}: ${m.text ?? ""}` : undefined}
                onClick={clickable ? () => onAction!(m) : undefined}
                onKeyDown={clickable ? (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onAction!(m)) : undefined}
              >
                {m.reply_to && <span className="quote">{m.reply_to.text}</span>}
                {body}
              </div>
              <span className="time">{formatTime(m.ts)}</span>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
