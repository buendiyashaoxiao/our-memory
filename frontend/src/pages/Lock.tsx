import { useState, type FormEvent } from "react";
import { IconLock } from "../components/Icons";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/format";
import { translate } from "../lib/i18n";

export default function Lock({ lang, onUnlocked }: { lang: Lang; onUnlocked: () => void }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const t = (k: Parameters<typeof translate>[1]) => translate(lang, k);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!pin) return;
    setBusy(true);
    setError(null);
    try {
      await api.unlock(pin);
      onUnlocked();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? err.message : t("lock.wrong"));
      setPin("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lock">
      <form onSubmit={submit} aria-labelledby="lock-title">
        <IconLock width={32} height={32} style={{ color: "var(--muted)" }} />
        <h1 id="lock-title" style={{ fontSize: 24, marginTop: 14 }}>
          {t("lock.title")}
        </h1>
        <p className="muted small">{t("lock.hint")}</p>
        <label className="sr-only" htmlFor="pin">
          PIN
        </label>
        <input
          id="pin"
          className="input"
          type="password"
          inputMode="numeric"
          autoComplete="current-password"
          autoFocus
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? "pin-error" : undefined}
        />
        {error && (
          <p id="pin-error" role="alert" style={{ color: "var(--accent)", fontSize: 14, margin: "0 0 12px" }}>
            {error}
          </p>
        )}
        <button className="btn primary block" disabled={busy || !pin}>
          {t("lock.unlock")}
        </button>
      </form>
    </div>
  );
}
