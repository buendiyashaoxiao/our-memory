import { useState } from "react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { useApp } from "../lib/store";
import { formatDay } from "../lib/format";
import { IconCheck, IconPlus } from "./Icons";
import { Loading } from "./common";
import { Sheet } from "./Sheet";

/** Add a message or media item (or just a date) to an existing or new Memory Moment. */
export function AddToMoment({ open, onClose, item, day, onDone }: {
  open: boolean;
  onClose: () => void;
  item?: { kind: "message" | "media"; ref: number } | null;
  day?: string | null;
  onDone?: (msg: string) => void;
}) {
  const { t, lang } = useApp();
  const moments = useAsync(() => (open ? api.moments() : Promise.resolve([])), [open]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState<number[]>([]);

  const addTo = async (id: number) => {
    if (!item) {
      onDone?.(t("moments.added"));
      return;
    }
    setBusy(true);
    try {
      await api.addMomentItem(id, item.kind, item.ref);
      setAdded((a) => [...a, id]);
      onDone?.(t("moments.added"));
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await api.createMoment({ title: title.trim(), start_day: day ?? null, items: item ? [item] : [] });
      setTitle("");
      moments.reload();
      onDone?.(t("moments.added"));
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("day.addToMoment")} labelledBy="add-moment-title">
      {moments.loading && <Loading />}
      {item && (moments.data ?? []).length > 0 && (
        <div style={{ marginBottom: 20 }}>
          {(moments.data ?? []).map((m) => (
            <button key={m.id} type="button" className="list-link" style={{ width: "100%", textAlign: "left" }}
              disabled={busy || added.includes(m.id)} onClick={() => addTo(m.id)}>
              <div className="grow">
                <div>{m.title}</div>
                {m.start_day && <div className="tiny muted">{formatDay(m.start_day, lang)}</div>}
              </div>
              {added.includes(m.id) ? <IconCheck width={20} /> : <IconPlus width={20} />}
            </button>
          ))}
        </div>
      )}
      <label className="field">
        <span>{t("moments.new")}</span>
        <input className="input" value={title} maxLength={200} placeholder={t("moments.titlePlaceholder")}
          onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()} />
      </label>
      <button className="btn accent block" disabled={busy || !title.trim()} onClick={create}>
        {item ? t("moments.createAndAdd") : t("moments.create")}
      </button>
    </Sheet>
  );
}
