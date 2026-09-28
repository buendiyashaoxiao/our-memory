import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ConfidenceBadge, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/common";
import { MessageList } from "../components/MessageList";
import { Sheet } from "../components/Sheet";
import { Thumb } from "../components/Thumb";
import { VoicePlayer } from "../components/VoicePlayer";
import { api } from "../lib/api";
import { formatDay, formatTime } from "../lib/format";
import { useAsync, useInfinite } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { MediaDetail, Message, ReviewSummary } from "../lib/types";

const FILTERS: (keyof ReviewSummary)[] = ["low", "medium", "unlinked", "problems", "hidden", "manual", "duplicates"];

export default function Review() {
  const { t } = useApp();
  const [params, setParams] = useSearchParams();
  const summary = useAsync(() => api.reviewSummary(), []);
  const fallback = summary.data ? FILTERS.find((f) => summary.data![f] > 0) ?? "low" : null;
  const filter = (params.get("filter") as keyof ReviewSummary) || fallback || "low";
  const ready = !!params.get("filter") || !!summary.data;
  const list = useInfinite<MediaDetail>(
    (cursor) => (ready ? api.reviewMedia(filter, cursor) : Promise.resolve({ items: [], next_cursor: null })),
    [filter, ready],
  );
  const [picking, setPicking] = useState<MediaDetail | null>(null);
  const toast = useToast();

  const replace = (m: MediaDetail | null, id: number) => {
    list.setItems((items) => (m ? items.map((x) => (x.id === id ? m : x)) : items.filter((x) => x.id !== id)));
    summary.reload();
  };

  return (
    <div className="page">
      <PageHeader title={t("review.title")} sub={t("review.intro")} />
      <div className="chips" role="group" aria-label="filter" style={{ marginBottom: 18 }}>
        {FILTERS.map((f) => (
          <button key={f} className="chip" aria-pressed={filter === f} onClick={() => setParams({ filter: f })}>
            {t(`review.${f}`)} <span className="tiny muted">{summary.data?.[f] ?? ""}</span>
          </button>
        ))}
      </div>
      {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
      {!list.loading && !list.error && list.items.length === 0 && <Empty glyph="✓">{t("review.empty")}</Empty>}
      {list.items.map((m) => (
        <ReviewCard key={m.id} m={m} onChanged={(u) => replace(u, m.id)} onPick={() => setPicking(m)} toast={toast.show} />
      ))}
      <div ref={list.sentinel} />
      {list.loading && <Loading />}
      <PickMessage media={picking} onClose={() => setPicking(null)}
        onPicked={(u) => { if (picking) replace(u, picking.id); setPicking(null); toast.show(t("common.saved")); }} />
      {toast.node}
    </div>
  );
}

function MsgPreview({ m }: { m: Message }) {
  const { nameOf, lang } = useApp();
  return (
    <Link to={`/day/${m.day}`} className="small" style={{ display: "block", padding: "6px 10px", borderRadius: 10, background: "var(--bg-2)" }}>
      <span className="tiny muted">
        {nameOf(m.sender_id)} · {m.day && formatDay(m.day, lang, "numeric")} {formatTime(m.ts)} · {m.type}
      </span>
      <br />
      {m.text ?? m.media_ref ?? ""}
    </Link>
  );
}

function ReviewCard({ m, onChanged, onPick, toast }: {
  m: MediaDetail;
  onChanged: (m: MediaDetail | null) => void;
  onPick: () => void;
  toast: (s: string) => void;
}) {
  const { t, lang } = useApp();
  const [dateEdit, setDateEdit] = useState(false);
  const [date, setDate] = useState((m.ts ?? "").slice(0, 16));
  const refresh = async () => onChanged(await api.media(m.id));
  const act = async (fn: () => Promise<unknown>) => {
    await fn();
    await refresh();
    toast(t("common.saved"));
  };
  const visual = m.type === "image" || m.type === "video";
  return (
    <article className="card" style={{ marginBottom: 14 }}>
      <div className="row" style={{ alignItems: "flex-start", gap: 14 }}>
        {visual && (
          <div style={{ width: 96, height: 96, borderRadius: 12, overflow: "hidden", flex: "none" }}>
            <Thumb media={m} />
          </div>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="small" style={{ fontWeight: 500, overflowWrap: "anywhere" }}>{m.filename}</div>
          <div className="tiny muted">
            {m.day ? `${formatDay(m.day, lang, "numeric")} ${formatTime(m.ts)}` : "—"}
            {m.ts_source && ` · ${t(`tsSource.${m.ts_source}` as never)}`}
          </div>
          {m.status !== "ok" && <div className="tiny" style={{ color: "var(--accent)" }}>{m.status}: {m.error}</div>}
          {m.rel_path && <div className="tiny muted" style={{ overflowWrap: "anywhere" }}>{m.rel_path}</div>}
        </div>
      </div>
      {!visual && m.status === "ok" && <div style={{ marginTop: 10 }}><VoicePlayer media={m} size="sm" /></div>}

      {m.message && (
        <div style={{ marginTop: 12 }}>
          <div className="tiny muted row" style={{ gap: 6, marginBottom: 4 }}>
            {t("review.linked")} <ConfidenceBadge confidence={m.association?.confidence} />
          </div>
          <MsgPreview m={m.message} />
        </div>
      )}
      {m.suggested_message && !m.message && (
        <div style={{ marginTop: 12 }}>
          <div className="tiny muted row" style={{ gap: 6, marginBottom: 4 }}>
            {t("review.suggested")} <ConfidenceBadge confidence="low" />
          </div>
          <MsgPreview m={m.suggested_message} />
        </div>
      )}

      <div className="row wrap" style={{ marginTop: 12, gap: 8 }}>
        {m.suggested_message && !m.message && (
          <button className="btn small accent" onClick={() => act(() => api.linkMedia(m.id, m.suggested_message!.id))}>
            {t("review.accept")}
          </button>
        )}
        {m.message && (
          <button className="btn small line" onClick={() => act(() => api.linkMedia(m.id, null))}>{t("review.unlink")}</button>
        )}
        {m.status === "ok" && <button className="btn small line" onClick={onPick}>{t("review.pick")}</button>}
        <button className="btn small line" onClick={() => setDateEdit(!dateEdit)}>{t("review.changeDate")}</button>
        <button className="btn small line" onClick={() => act(() => api.patchMedia(m.id, { hidden: !m.hidden }))}>
          {m.hidden ? t("common.unhide") : t("common.hide")}
        </button>
        {m.association?.locked && (
          <button className="btn small ghost" onClick={() => act(() => api.resetLink(m.id))}>{t("review.resetAuto")}</button>
        )}
      </div>
      {dateEdit && (
        <div className="row wrap" style={{ marginTop: 10 }}>
          <input className="input" type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)}
            style={{ flex: 1, minWidth: 200 }} aria-label={t("review.changeDate")} />
          <button className="btn small primary" disabled={!date}
            onClick={() => act(() => api.patchMedia(m.id, { ts: date })).then(() => setDateEdit(false))}>
            {t("common.save")}
          </button>
          {m.ts_source === "manual" && (
            <button className="btn small ghost" onClick={() => act(() => api.patchMedia(m.id, { ts: null }))}>
              {t("review.resetDate")}
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function PickMessage({ media, onClose, onPicked }: { media: MediaDetail | null; onClose: () => void; onPicked: (m: MediaDetail) => void }) {
  const { t } = useApp();
  const cands = useAsync(() => (media ? api.mediaCandidates(media.id) : Promise.resolve([])), [media?.id]);
  return (
    <Sheet open={!!media} onClose={onClose} title={t("review.pick")} labelledBy="pick">
      {cands.loading && <Loading />}
      {cands.data && cands.data.length === 0 && <p className="muted">{t("search.empty")}</p>}
      {cands.data && media && (
        <MessageList messages={cands.data} onAction={async (msg) => onPicked(await api.linkMedia(media.id, msg.id))} />
      )}
    </Sheet>
  );
}
