import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AddToMoment } from "../components/AddToMoment";
import { DateBlock, ErrorBox, FavButton, Loading, SkeletonCards, useToast } from "../components/common";
import { DayMedia, DayStats } from "../components/DayContent";
import { IconEye, IconMore, IconNext, IconPlus, IconPrev, IconStar } from "../components/Icons";
import { Lightbox } from "../components/Lightbox";
import { MessageList } from "../components/MessageList";
import { Sheet } from "../components/Sheet";
import { api } from "../lib/api";
import { agoText, daysBetween, formatDay } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Media, Message } from "../lib/types";

export default function DayView() {
  const { day = "" } = useParams();
  const { t, lang, settings } = useApp();
  const navigate = useNavigate();
  const detail = useAsync(() => api.day(day), [day]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [menu, setMenu] = useState(false);
  const [msgAction, setMsgAction] = useState<Message | null>(null);
  const [momentItem, setMomentItem] = useState<{ kind: "message" | "media"; ref: number } | null | undefined>(undefined);
  const [lb, setLb] = useState<{ items: Media[]; index: number } | null>(null);
  const toast = useToast();

  useEffect(() => {
    if (detail.data) {
      setMessages(detail.data.messages.items);
      setCursor(detail.data.messages.next_cursor);
    }
  }, [detail.data]);

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.dayMessages(day, cursor);
      setMessages((m) => [...m, ...page.items]);
      setCursor(page.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  };

  if (detail.error) return <div className="page"><ErrorBox error={detail.error} onRetry={detail.reload} /></div>;
  if (!detail.data) return <div className="page"><SkeletonCards n={2} h={200} /></div>;
  const d = detail.data;

  const toggleDayFav = async () => {
    await api.setFavorite("day", d.day, !d.favorite);
    detail.setData((p) => (p ? { ...p, favorite: !p.favorite } : p));
  };
  const toggleHidden = async () => {
    await api.hideDay(d.day, !d.hidden);
    setMenu(false);
    detail.reload();
  };
  const toggleMsgFav = async (m: Message) => {
    await api.setFavorite("message", m.id, !m.favorite);
    setMessages((ms) => ms.map((x) => (x.id === m.id ? { ...x, favorite: !x.favorite } : x)));
    setMsgAction(null);
  };
  const hideMsg = async (m: Message) => {
    await api.hideMessage(m.id, true);
    setMessages((ms) => ms.filter((x) => x.id !== m.id));
    setMsgAction(null);
  };

  const chatMedia = messages.map((m) => m.media).filter((m): m is Media => !!m && (m.type === "image" || m.type === "video"));
  const chatVoices = messages.map((m) => m.media).filter((m): m is Media => !!m && (m.type === "voice" || m.type === "audio"));
  const gapPrev = d.prev_day ? daysBetween(d.prev_day, d.day) - 1 : 0;

  return (
    <div className="page">
      <div className="topbar">
        <button className="icon-btn" onClick={() => navigate(-1)} aria-label={t("common.back")}>
          <IconPrev />
        </button>
        <div className="row" style={{ gap: 0 }}>
          <FavButton on={d.favorite} onToggle={toggleDayFav} />
          <button className="icon-btn" onClick={() => setMenu(true)} aria-label={t("nav.more")}>
            <IconMore />
          </button>
        </div>
      </div>

      <DateBlock day={d.day} size="xl" />
      <div className="ago">{agoText(d.day, lang)}</div>

      {d.hidden ? (
        <p className="muted" style={{ marginTop: 24 }}>{t("day.hidden")}</p>
      ) : (
        <>
          <DayStats d={d} />
          <DayMedia d={d} />
          <section className="section" aria-labelledby="day-chat">
            <h2 className="section-title" id="day-chat">
              {t("day.chat")} <small>{d.stats.messages}</small>
            </h2>
            {messages.length === 0 ? (
              <p className="muted">{t("day.noChat")}</p>
            ) : (
              <MessageList messages={messages} voiceQueue={chatVoices} onAction={setMsgAction}
                onOpenMedia={(m) => setLb({ items: chatMedia, index: Math.max(0, chatMedia.findIndex((x) => x.id === m.id)) })} />
            )}
            {cursor && (
              <div style={{ textAlign: "center", marginTop: 16 }}>
                {loadingMore ? <Loading /> : (
                  <button className="btn line small" onClick={loadMore}>{t("common.loadMore")}</button>
                )}
              </div>
            )}
          </section>
        </>
      )}

      <nav className="row between section" aria-label="days">
        {d.prev_day ? (
          <Link to={`/day/${d.prev_day}`} className="btn line small">
            <IconPrev width={16} /> {formatDay(d.prev_day, lang, settings?.date_format)}
          </Link>
        ) : <span />}
        {d.next_day ? (
          <Link to={`/day/${d.next_day}`} className="btn line small">
            {formatDay(d.next_day, lang, settings?.date_format)} <IconNext width={16} />
          </Link>
        ) : <span />}
      </nav>
      {gapPrev > 0 && <p className="tiny muted" style={{ textAlign: "center" }}>{t("day.gap", { n: gapPrev })}</p>}

      <Sheet open={menu} onClose={() => setMenu(false)} title={formatDay(d.day, lang, settings?.date_format)} labelledBy="day-menu">
        <button className="list-link" style={{ width: "100%" }} onClick={() => { setMenu(false); setMomentItem(null); }}>
          <IconPlus width={20} /> <span className="grow" style={{ textAlign: "left" }}>{t("day.addToMoment")}</span>
        </button>
        <button className="list-link" style={{ width: "100%" }} onClick={toggleHidden}>
          <IconEye off={!d.hidden} width={20} />
          <span className="grow" style={{ textAlign: "left" }}>{d.hidden ? t("day.unhideDay") : t("day.hideDay")}</span>
        </button>
      </Sheet>

      <Sheet open={!!msgAction} onClose={() => setMsgAction(null)} labelledBy="msg-menu">
        {msgAction && (
          <>
            <p style={{ margin: "0 0 12px", whiteSpace: "pre-wrap" }}>{msgAction.text}</p>
            <button className="list-link" style={{ width: "100%" }} onClick={() => toggleMsgFav(msgAction)}>
              <IconStar filled={msgAction.favorite} width={20} />
              <span className="grow" style={{ textAlign: "left" }}>{msgAction.favorite ? t("common.unfavorite") : t("common.favorite")}</span>
            </button>
            <button className="list-link" style={{ width: "100%" }} onClick={() => { setMomentItem({ kind: "message", ref: msgAction.id }); setMsgAction(null); }}>
              <IconPlus width={20} /> <span className="grow" style={{ textAlign: "left" }}>{t("day.addToMoment")}</span>
            </button>
            <button className="list-link" style={{ width: "100%" }} onClick={() => hideMsg(msgAction)}>
              <IconEye off width={20} /> <span className="grow" style={{ textAlign: "left" }}>{t("common.hide")}</span>
            </button>
          </>
        )}
      </Sheet>

      <AddToMoment open={momentItem !== undefined} onClose={() => setMomentItem(undefined)} item={momentItem ?? null}
        day={d.day} onDone={toast.show} />
      {lb && (
        <Lightbox items={lb.items} index={lb.index} onClose={() => setLb(null)} onIndex={(index) => setLb({ ...lb, index })}
          onChange={(m) => setLb({ ...lb, items: lb.items.map((x) => (x.id === m.id ? m : x)) })} />
      )}
      {toast.node}
    </div>
  );
}
