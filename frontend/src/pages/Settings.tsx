import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Avatar, PageHeader, Segmented, useToast } from "../components/common";
import { IconNext } from "../components/Icons";
import { api, ApiError } from "../lib/api";
import { formatDay } from "../lib/format";
import { useApp } from "../lib/store";
import type { Settings } from "../lib/types";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="section">
      <h2 className="section-title">{title}</h2>
      <div className="card">{children}</div>
    </section>
  );
}

export default function SettingsPage() {
  const { t, lang, settings, setSettings, reload } = useApp();
  const toast = useToast();
  const [pinCurrent, setPinCurrent] = useState("");
  const [pinNew, setPinNew] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);

  if (!settings) return <div className="page" />;
  const s = settings;

  const patch = async (p: Partial<Settings>) => {
    const next = await api.patchSettings(p);
    setSettings(next);
    toast.show(t("common.saved"));
  };

  const setName = (id: string, name: string) => {
    const participants = { ...s.participants, [id]: { ...(s.participants[id] ?? {}), name: name.trim() || undefined } };
    return patch({ participants });
  };

  const upload = async (id: string, file: File | undefined) => {
    if (!file) return;
    await api.uploadAvatar(id, file);
    await reload();
    toast.show(t("common.saved"));
  };

  const savePin = async (remove: boolean) => {
    setPinError(null);
    try {
      await api.changePin(pinCurrent || null, remove ? null : pinNew);
      setPinCurrent("");
      setPinNew("");
      await reload();
      toast.show(t("common.saved"));
    } catch (e) {
      setPinError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const weights = s.random_day;

  return (
    <div className="page">
      <PageHeader title={t("settings.title")} />

      <Section title={t("settings.names")}>
        {s.participants_detected.length === 0 && <p className="muted small">—</p>}
        {s.participants_detected.map((p) => (
          <div key={p.id} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
            <label style={{ cursor: "pointer" }} title={t("settings.uploadAvatar")}>
              <Avatar senderId={p.id} size="lg" />
              <input type="file" accept="image/*" className="sr-only" aria-label={`${t("settings.uploadAvatar")} ${p.id}`}
                onChange={(e) => upload(p.id, e.target.files?.[0])} />
            </label>
            <div style={{ flex: 1 }}>
              <input className="input" defaultValue={s.participants[p.id]?.name ?? p.display_name ?? p.id}
                aria-label={`name ${p.id}`} onBlur={(e) => setName(p.id, e.target.value)} />
              <label className="row small muted" style={{ marginTop: 8, gap: 6, minHeight: 32, cursor: "pointer" }}>
                <input type="radio" name="self" checked={(s.self_id ?? s.participants_detected[0]?.id) === p.id}
                  onChange={() => patch({ self_id: p.id })} />
                {t("settings.me")}
                <span style={{ marginLeft: "auto" }}>{t("common.messages", { n: p.message_count })}</span>
              </label>
            </div>
          </div>
        ))}
      </Section>

      <Section title={t("settings.museum")}>
        <label className="field">
          <span>{t("settings.museumTitle")}</span>
          <input className="input" defaultValue={s.title ?? ""} placeholder={lang === "en" ? "Our Memory Museum" : "我们的回忆馆"}
            onBlur={(e) => patch({ title: e.target.value.trim() || null })} />
        </label>
        <label className="field">
          <span>{t("settings.intro")}</span>
          <textarea className="textarea" defaultValue={(s.intro_lines ?? []).join("\n")}
            onBlur={(e) => {
              const lines = e.target.value.split("\n").map((x) => x.trim()).filter(Boolean);
              patch({ intro_lines: lines.length ? lines : null });
            }} />
        </label>
        <label className="field" style={{ marginBottom: 0 }}>
          <span>{t("settings.start")}</span>
          <input className="input" type="date" defaultValue={s.relationship_start ?? ""}
            onChange={(e) => patch({ relationship_start: e.target.value || null })} />
        </label>
      </Section>

      <Section title={t("settings.display")}>
        <div className="row between wrap" style={{ minHeight: 48 }}>
          <span>{t("settings.language")}</span>
          <Segmented label={t("settings.language")} value={s.language} onChange={(v) => patch({ language: v })}
            options={[{ value: "zh", label: "中文" }, { value: "en", label: "English" }]} />
        </div>
        <div className="row between wrap" style={{ minHeight: 48 }}>
          <span>{t("settings.theme")}</span>
          <Segmented label={t("settings.theme")} value={s.theme} onChange={(v) => patch({ theme: v })}
            options={[
              { value: "auto", label: t("settings.theme.auto") },
              { value: "light", label: t("settings.theme.light") },
              { value: "dark", label: t("settings.theme.dark") },
            ]} />
        </div>
        <div className="row between wrap" style={{ minHeight: 48 }}>
          <span>{t("settings.dateFormat")}</span>
          <Segmented label={t("settings.dateFormat")} value={s.date_format} onChange={(v) => patch({ date_format: v })}
            options={[
              { value: "long", label: t("settings.dateFormat.long") },
              { value: "numeric", label: t("settings.dateFormat.numeric") },
            ]} />
        </div>
        <label className="switch">
          <span>{t("settings.autoplay")}</span>
          <input type="checkbox" checked={s.autoplay} onChange={(e) => patch({ autoplay: e.target.checked })} />
        </label>
      </Section>

      <Section title={t("settings.random")}>
        <Segmented label={t("settings.random")} value={weights.mode}
          onChange={(v) => patch({ random_day: { ...weights, mode: v } })}
          options={[
            { value: "weighted", label: t("settings.random.weighted") },
            { value: "uniform", label: t("settings.random.uniform") },
          ]} />
        {weights.mode === "weighted" && (
          <div style={{ marginTop: 16 }}>
            {(["photo", "voice", "video", "conversation"] as const).map((k) => (
              <label key={k} className="row between" style={{ minHeight: 44 }}>
                <span className="small">{t(`settings.random.${k}`)}</span>
                <input type="range" min={0} max={3} step={0.5} defaultValue={weights[k]} style={{ width: "55%" }}
                  aria-label={t(`settings.random.${k}`)}
                  onChange={(e) => patch({ random_day: { ...weights, [k]: Number(e.target.value) } })} />
              </label>
            ))}
          </div>
        )}
      </Section>

      <Section title={t("settings.privacy")}>
        <div className="row between" style={{ minHeight: 44 }}>
          <span>{t("settings.pin")}</span>
          <span className="badge-conf">{s.lock_enabled ? t("settings.pinOn") : t("settings.pinOff")}</span>
        </div>
        {s.lock_enabled && (
          <label className="field">
            <span>{t("settings.pinCurrent")}</span>
            <input className="input" type="password" autoComplete="current-password" value={pinCurrent}
              onChange={(e) => setPinCurrent(e.target.value)} />
          </label>
        )}
        <label className="field">
          <span>{t("settings.pinNew")}</span>
          <input className="input" type="password" autoComplete="new-password" value={pinNew} minLength={4}
            onChange={(e) => setPinNew(e.target.value)} />
        </label>
        {pinError && <p className="error-box" role="alert">{pinError}</p>}
        <div className="row wrap">
          <button className="btn primary small" disabled={pinNew.length < 4} onClick={() => savePin(false)}>
            {t("settings.pinSet")}
          </button>
          {s.lock_enabled && (
            <button className="btn line small" onClick={() => savePin(true)}>{t("settings.pinRemove")}</button>
          )}
        </div>
        <p className="tiny muted">{t("settings.pinNote")}</p>
        <label className="row between" style={{ minHeight: 48 }}>
          <span>{t("settings.autoLock")}</span>
          <select className="select" style={{ width: "auto" }} value={s.auto_lock_minutes}
            onChange={(e) => patch({ auto_lock_minutes: Number(e.target.value) })}>
            <option value={0}>{t("settings.autoLock.off")}</option>
            {[5, 15, 30, 60].map((m) => (
              <option key={m} value={m}>{t("common.minutes", { n: m })}</option>
            ))}
          </select>
        </label>
        {s.lock_enabled && (
          <button className="btn line small" onClick={() => api.lock().then(() => window.location.reload())}>
            {t("settings.lockNow")}
          </button>
        )}
      </Section>

      <Section title={t("settings.hidden")}>
        <div className="small muted" style={{ marginBottom: 8 }}>{t("settings.hiddenDays")}</div>
        {s.hidden_days.length === 0 && <p className="small">{t("settings.noneHidden")}</p>}
        {s.hidden_days.map((d) => (
          <div key={d} className="row between" style={{ minHeight: 44 }}>
            <Link to={`/day/${d}`}>{formatDay(d, lang, s.date_format)}</Link>
            <button className="btn small ghost" onClick={async () => { await api.hideDay(d, false); await reload(); }}>
              {t("common.unhide")}
            </button>
          </div>
        ))}
        <Link to="/review?filter=hidden" className="list-link">
          <span className="grow">{t("settings.hiddenMedia")}</span>
          <IconNext width={18} className="chev" />
        </Link>
        <Link to="/review" className="list-link">
          <span className="grow">{t("settings.review")}</span>
          <IconNext width={18} className="chev" />
        </Link>
      </Section>

      <Section title={t("settings.data")}>
        <p className="small muted" style={{ margin: 0 }}>{t("settings.dataNote")}</p>
      </Section>
      {toast.node}
    </div>
  );
}
