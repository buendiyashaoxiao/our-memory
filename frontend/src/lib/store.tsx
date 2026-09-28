import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Lang } from "./format";
import { translate, type I18nKey } from "./i18n";
import type { Copy, Settings } from "./types";

interface AppState {
  settings: Settings | null;
  copy: Copy | null;
  lang: Lang;
  t: (key: I18nKey, vars?: Record<string, string | number>) => string;
  nameOf: (senderId: string | null | undefined) => string;
  avatarOf: (senderId: string | null | undefined) => string | null;
  isSelf: (senderId: string | null | undefined) => boolean;
  reload: () => Promise<void>;
  setSettings: (s: Settings) => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children, initialLang = "zh" }: { children: ReactNode; initialLang?: Lang }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [copy, setCopy] = useState<Copy | null>(null);

  const reload = useCallback(async () => {
    const [s, c] = await Promise.all([api.settings(), api.copy()]);
    setSettings(s);
    setCopy(c);
  }, []);

  useEffect(() => {
    reload().catch(() => undefined);
  }, [reload]);

  // copy depends on language; refresh when it changes
  const language = settings?.language;
  useEffect(() => {
    if (language) api.copy().then(setCopy).catch(() => undefined);
  }, [language]);

  const theme = settings?.theme ?? "auto";
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);

  const lang: Lang = settings?.language ?? initialLang;
  useEffect(() => {
    document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
    if (copy?.museumTitle) document.title = copy.museumTitle;
  }, [lang, copy?.museumTitle]);

  const value = useMemo<AppState>(() => {
    const detected = settings?.participants_detected ?? [];
    const configured = settings?.participants ?? {};
    const selfId = settings?.self_id ?? detected[0]?.id ?? null;
    return {
      settings,
      copy,
      lang,
      t: (key, vars) => translate(lang, key, vars),
      nameOf: (id) => {
        if (!id) return translate(lang, "common.unknownSender");
        return configured[id]?.name || detected.find((d) => d.id === id)?.display_name || id;
      },
      avatarOf: (id) => (id ? configured[id]?.avatar ?? null : null),
      isSelf: (id) => !!id && id === selfId,
      reload,
      setSettings,
    };
  }, [settings, copy, lang, reload]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
