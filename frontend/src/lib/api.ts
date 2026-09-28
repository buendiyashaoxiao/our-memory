import type {
  Copy,
  DayCardData,
  DayDetail,
  Favorite,
  FavoriteKind,
  LockStatus,
  Media,
  MediaDetail,
  Message,
  Moment,
  Overview,
  Page,
  ReviewSummary,
  Settings,
  SoundsPage,
  Stats,
  YearOverview,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export const LOCKED_EVENT = "mm-locked";

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && v !== false) u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  if (res.status === 401) {
    window.dispatchEvent(new Event(LOCKED_EVENT));
    throw new ApiError(401, "locked");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const get = <T>(p: string) => request<T>("GET", p);

export const api = {
  lockStatus: () => get<LockStatus>("/api/lock/status"),
  unlock: (pin: string) => request<{ unlocked: boolean }>("POST", "/api/lock/unlock", { pin }),
  lock: () => request<{ locked: boolean }>("POST", "/api/lock/lock"),
  changePin: (current: string | null, next: string | null) =>
    request<{ enabled: boolean }>("POST", "/api/lock/pin", { current, new: next }),

  copy: () => get<Copy>("/api/copy"),
  settings: () => get<Settings>("/api/settings"),
  patchSettings: (patch: Partial<Settings>) => request<Settings>("PATCH", "/api/settings", patch),
  uploadAvatar: (senderId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ avatar: string }>("POST", `/api/settings/avatar/${encodeURIComponent(senderId)}`, fd);
  },

  overview: () => get<Overview>("/api/overview"),
  years: () => get<YearOverview[]>("/api/timeline/years"),
  timeline: (p: { cursor?: string | null; limit?: number; order?: "asc" | "desc"; mode?: "curated" | "all"; year?: number; month?: number }) =>
    get<Page<DayCardData>>(`/api/timeline${qs(p)}`),
  day: (day: string) => get<DayDetail>(`/api/days/${day}`),
  dayMessages: (day: string, cursor?: string | null) =>
    get<Page<Message>>(`/api/days/${day}/messages${qs({ cursor, limit: 200 })}`),
  hideDay: (day: string, hidden: boolean) => request("PUT", `/api/days/${day}/hidden`, { hidden }),
  randomDay: (exclude?: string | null) => get<DayDetail | { day: null }>(`/api/random-day${qs({ exclude })}`),

  sounds: (p: { cursor?: string | null; favorites?: boolean; sender?: string | null; order?: "asc" | "desc" }) =>
    get<SoundsPage>(`/api/sounds${qs({ ...p, limit: 30 })}`),
  galleryMonths: () => get<{ month: string; photos: number; videos: number }[]>("/api/gallery/months"),
  gallery: (p: { cursor?: string | null; kind?: "all" | "image" | "video"; month?: string | null; favorites?: boolean; order?: "asc" | "desc"; limit?: number }) =>
    get<Page<Media>>(`/api/gallery${qs(p)}`),
  media: (id: number) => get<MediaDetail>(`/api/media/${id}`),
  patchMedia: (id: number, patch: { title?: string | null; note?: string | null; hidden?: boolean; ts?: string | null }) =>
    request<Media>("PATCH", `/api/media/${id}`, patch),
  linkMedia: (id: number, messageId: number | null) => request<MediaDetail>("PUT", `/api/media/${id}/link`, { message_id: messageId }),
  resetLink: (id: number) => request<MediaDetail>("DELETE", `/api/media/${id}/link`),
  mediaContext: (id: number) =>
    get<{ media: MediaDetail; anchor_ts: string | null; anchor_message_id: number | null; messages: Message[] }>(
      `/api/media/${id}/context`,
    ),
  mediaCandidates: (id: number) => get<Message[]>(`/api/media/${id}/candidates`),
  messageContext: (id: number) =>
    get<{ anchor_ts: string | null; anchor_message_id: number; messages: Message[] }>(`/api/messages/${id}/context`),
  hideMessage: (id: number, hidden: boolean) => request("PATCH", `/api/messages/${id}`, { hidden }),
  search: (q: string, cursor?: string | null) => get<Page<Message>>(`/api/search${qs({ q, cursor })}`),

  favorites: (kind?: FavoriteKind) => get<Favorite[]>(`/api/favorites${qs({ kind })}`),
  setFavorite: (kind: FavoriteKind, ref: string | number, on: boolean) =>
    request(on ? "PUT" : "DELETE", `/api/favorites/${kind}/${encodeURIComponent(String(ref))}`),

  moments: () => get<Moment[]>("/api/moments"),
  moment: (id: number) => get<Moment>(`/api/moments/${id}`),
  createMoment: (m: { title: string; description?: string | null; start_day?: string | null; end_day?: string | null; items?: { kind: "message" | "media"; ref: number }[] }) =>
    request<Moment>("POST", "/api/moments", m),
  patchMoment: (id: number, patch: Partial<Pick<Moment, "title" | "description" | "start_day" | "end_day">> & { cover_media_id?: number | null }) =>
    request<Moment>("PATCH", `/api/moments/${id}`, patch),
  deleteMoment: (id: number) => request("DELETE", `/api/moments/${id}`),
  addMomentItem: (id: number, kind: "message" | "media", ref: number) =>
    request<Moment>("POST", `/api/moments/${id}/items`, { kind, ref }),
  removeMomentItem: (id: number, kind: "message" | "media", ref: number) =>
    request<Moment>("DELETE", `/api/moments/${id}/items/${kind}/${ref}`),

  stats: () => get<Stats>("/api/stats"),
  reviewSummary: () => get<ReviewSummary>("/api/review/summary"),
  reviewMedia: (filter: string, cursor?: string | null) =>
    get<Page<MediaDetail>>(`/api/review/media${qs({ filter, cursor })}`),
};
