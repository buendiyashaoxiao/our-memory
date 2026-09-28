import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { PlayerProvider } from "../lib/player";
import { AppProvider } from "../lib/store";
import type { DayCardData, DayDetail, Media, Message, Settings } from "../lib/types";

export const settings: Settings = {
  participants: {},
  self_id: "a",
  relationship_start: null,
  title: null,
  intro_lines: null,
  language: "zh",
  date_format: "long",
  theme: "auto",
  timezone: "local",
  random_day: { mode: "weighted", photo: 1, voice: 1, video: 1, conversation: 1, min_messages: 5 },
  autoplay: false,
  auto_lock_minutes: 0,
  participants_detected: [
    { id: "a", display_name: "阿林", message_count: 10 },
    { id: "b", display_name: "小周", message_count: 9 },
  ],
  hidden_days: [],
  lock_enabled: false,
};

export const copy = {
  museumTitle: "我们的回忆馆",
  museumSubtitleEn: "Our Memory Museum",
  introLines: ["有些普通的一天，", "后来回头看才知道很重要。"],
  enterButton: "进入",
  randomDayTitle: "随机回到一天",
  soundMuseumTitle: "声音博物馆",
  soundMuseumIntro: "那些被保存下来的声音。",
  galleryTitle: "相册",
  timelineTitle: "时间线",
  favoritesTitle: "收藏",
  momentsTitle: "回忆片段",
  statsTitle: "我们的数字",
  statsIntro: "",
  emptyMuseum: "这里还是空的。",
  footer: "只存在于这台电脑上。",
};

export function media(id: number, over: Partial<Media> = {}): Media {
  return {
    id, type: "image", filename: `IMG_${id}.jpg`, ts: "2025-05-01T11:23:00", day: "2025-05-01", ts_source: "exif",
    duration: null, width: 720, height: 960, status: "ok", error: null, thumb: `/api/media/${id}/thumb`,
    url: `/api/media/${id}/file`, playable: true, waveform: null, title: null, note: null, hidden: false,
    duplicate_of: null, favorite: false, association: null, sender_id: "a", ...over,
  };
}

export function message(id: number, text: string, sender = "a", over: Partial<Message> = {}): Message {
  return {
    id, ts: `2025-05-01T10:${String(id).padStart(2, "0")}:00`, day: "2025-05-01", sender_id: sender, sender_name: null,
    type: "text", text, media_ref: null, media: null, reply_to: null, duration: null, favorite: false, ...over,
  };
}

const stats = { messages: 12, photos: 2, videos: 0, voices: 1, audio_seconds: 6, longest_session_minutes: 3,
  first_ts: "2025-05-01T06:40:00", last_ts: "2025-05-01T22:16:00", score: 5 };

export function dayCard(day: string): DayCardData {
  return { day, stats, excerpts: [message(1, `那天的话 ${day}`)], media: [media(1)], voices: [], favorite: false, moments: [] };
}

export function dayDetail(day: string, over: Partial<DayDetail> = {}): DayDetail {
  return {
    day, hidden: false, stats, favorite: false, moments: [], prev_day: "2025-04-30", next_day: "2025-05-02",
    media: [media(1)], voices: [media(9, { type: "voice", duration: 6, waveform: [0.2, 1, 0.5] })],
    excerpts: [message(1, `excerpt of ${day}`)], messages: { items: [message(1, "早安"), message(2, "早呀", "b")], next_cursor: null },
    ...over,
  };
}

type Handler = (url: URL, init?: RequestInit) => unknown;

/** Replace fetch with a tiny router: longest matching path prefix wins. */
export function mockApi(routes: Record<string, unknown | Handler>) {
  const calls: { url: URL; init?: RequestInit }[] = [];
  const base: Record<string, unknown | Handler> = { "/api/settings": settings, "/api/copy": copy, ...routes };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    calls.push({ url, init });
    const key = Object.keys(base).filter((k) => url.pathname.startsWith(k)).sort((a, b) => b.length - a.length)[0];
    if (!key) return new Response(JSON.stringify({ detail: "not mocked" }), { status: 404 });
    const v = base[key];
    const body = typeof v === "function" ? (v as Handler)(url, init) : v;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function renderPage(ui: ReactNode, { path = "/", route = "/" }: { path?: string; route?: string } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AppProvider>
        <PlayerProvider>
          <Routes>
            <Route path={path} element={ui} />
            <Route path="*" element={<div data-testid="elsewhere" />} />
          </Routes>
        </PlayerProvider>
      </AppProvider>
    </MemoryRouter>,
  );
}
