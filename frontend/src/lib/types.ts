export type Confidence = "exact" | "high" | "medium" | "low";

export interface Association {
  message_id: number | null;
  suggested_message_id: number | null;
  method: string | null;
  confidence: Confidence | null;
  locked: boolean;
}

export type MediaType = "image" | "video" | "voice" | "audio";

export interface Media {
  id: number;
  type: MediaType;
  filename: string;
  ts: string | null;
  day: string | null;
  ts_source: string | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  status: "ok" | "corrupt" | "missing" | "unsupported";
  error: string | null;
  thumb: string | null;
  url: string;
  playable: boolean;
  waveform: number[] | null;
  title: string | null;
  note: string | null;
  hidden: boolean;
  duplicate_of: number | null;
  favorite: boolean;
  association: Association | null;
  sender_id: string | null;
  context?: Message[];
}

export interface MediaDetail extends Media {
  rel_path: string | null;
  codec: string | null;
  original_ts: string | null;
  original_ts_source: string | null;
  message?: Message | null;
  suggested_message?: Message | null;
}

export type MessageType =
  | "text"
  | "image"
  | "voice"
  | "audio"
  | "video"
  | "sticker"
  | "file"
  | "link"
  | "system"
  | "unknown";

export interface Message {
  id: number;
  ts: string | null;
  day: string | null;
  sender_id: string | null;
  sender_name: string | null;
  type: MessageType;
  text: string | null;
  media_ref: string | null;
  media: Media | null;
  reply_to: { id: number; sender_id: string | null; type: string; text: string } | null;
  duration: number | null;
  favorite: boolean;
}

export interface DayStats {
  messages: number;
  photos: number;
  videos: number;
  voices: number;
  audio_seconds: number;
  longest_session_minutes: number;
  first_ts: string | null;
  last_ts: string | null;
  score: number;
}

export interface MomentRef {
  id: number;
  title: string;
}

export interface DayCardData {
  day: string;
  stats: DayStats;
  excerpts: Message[];
  media: Media[];
  voices: Media[];
  favorite: boolean;
  moments: MomentRef[];
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface DayDetail {
  day: string;
  hidden: boolean;
  stats: DayStats;
  favorite: boolean;
  moments: MomentRef[];
  prev_day: string | null;
  next_day: string | null;
  media: Media[];
  voices: Media[];
  excerpts: Message[];
  messages: Page<Message>;
}

export interface MonthOverview {
  year: number;
  month: number;
  days: number;
  messages: number;
  photos: number;
  videos: number;
  voices: number;
  memory_days: number;
  cover: string | null;
}

export interface YearOverview {
  year: number;
  days: number;
  messages: number;
  photos: number;
  videos: number;
  voices: number;
  months: MonthOverview[];
}

export interface Participant {
  id: string;
  name: string;
  messages: number;
}

export interface Overview {
  totals: {
    days: number;
    messages: number;
    photos: number;
    videos: number;
    voices: number;
    first_day: string | null;
    last_day: string | null;
  };
  participants: Participant[];
  on_this_day: { day: string; msg_count: number; photo_count: number; voice_count: number; video_count: number }[];
  cover: string | null;
  has_data: boolean;
}

export interface SoundsPage extends Page<Media> {
  total: number;
  total_seconds: number;
}

export interface Moment {
  id: number;
  title: string;
  description: string | null;
  start_day: string | null;
  end_day: string | null;
  cover: Media | null;
  counts: { message: number; media: number };
  favorite: boolean;
  created_at: string;
  updated_at: string;
  messages?: Message[];
  media?: Media[];
}

export type FavoriteKind = "message" | "media" | "day" | "moment";

export interface Favorite {
  kind: FavoriteKind;
  ref: string;
  created_at: string;
  item: Message | Media | DayCardData | Moment;
}

export interface Stats {
  totals: {
    days: number;
    messages: number;
    photos: number;
    videos: number;
    voices: number;
    voice_seconds: number;
    first_day: string | null;
    last_day: string | null;
    span_days?: number;
  };
  busiest_day: { day: string; value: number } | null;
  longest_conversation_day: { day: string; value: number } | null;
  most_photos_day: { day: string; value: number } | null;
  months: { month: string; messages: number; photos: number; voices: number; videos: number }[];
  busiest_month: { month: string; messages: number } | null;
  hours: number[];
  peak_hour: number | null;
  weekdays: number[];
  by_sender: { sender_id: string; messages: number; voices: number; photos: number }[];
  longest_voice: { id: number; day: string; duration: number } | null;
  first_message: { id: number; ts: string; day: string; sender_id: string; text: string } | null;
  words: { method: "jieba" | "bigram"; words: [string, number][]; emojis: [string, number][]; laugh_messages: number };
  names: Record<string, string>;
}

export interface RandomDayWeights {
  mode: "weighted" | "uniform";
  photo: number;
  voice: number;
  video: number;
  conversation: number;
  min_messages: number;
}

export interface Settings {
  participants: Record<string, { name?: string; avatar?: string }>;
  self_id: string | null;
  relationship_start: string | null;
  title: string | null;
  intro_lines: string[] | null;
  language: "zh" | "en";
  date_format: "long" | "numeric";
  theme: "auto" | "light" | "dark";
  timezone: string;
  random_day: RandomDayWeights;
  autoplay: boolean;
  auto_lock_minutes: number;
  participants_detected: { id: string; display_name: string | null; message_count: number }[];
  hidden_days: string[];
  lock_enabled: boolean;
}

export interface Copy {
  museumTitle: string;
  museumSubtitleEn: string;
  introLines: string[];
  enterButton: string;
  randomDayTitle: string;
  soundMuseumTitle: string;
  soundMuseumIntro: string;
  galleryTitle: string;
  timelineTitle: string;
  favoritesTitle: string;
  momentsTitle: string;
  statsTitle: string;
  statsIntro: string;
  emptyMuseum: string;
  footer: string;
}

export interface LockStatus {
  enabled: boolean;
  unlocked: boolean;
  auto_lock_minutes: number;
  language: "zh" | "en";
  theme: "auto" | "light" | "dark";
}

export interface ReviewSummary {
  low: number;
  medium: number;
  unlinked: number;
  problems: number;
  hidden: number;
  manual: number;
  duplicates: number;
}
