export type Lang = "zh" | "en";

const WEEK_ZH = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];
const WEEK_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTH_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function parseDay(day: string): Date {
  const [y, m, d] = day.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function toDayString(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function addDays(day: string, n: number): string {
  const d = parseDay(day);
  d.setDate(d.getDate() + n);
  return toDayString(d);
}

export function formatDay(day: string, lang: Lang, style: "long" | "numeric" = "long"): string {
  const d = parseDay(day);
  if (style === "numeric") return day.replace(/-/g, ".");
  if (lang === "en") return `${MONTH_EN[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

export function formatMonthDay(day: string, lang: Lang): string {
  const d = parseDay(day);
  return lang === "en" ? `${MONTH_EN[d.getMonth()]} ${d.getDate()}` : `${d.getMonth() + 1}月${d.getDate()}日`;
}

export function formatMonth(ym: string, lang: Lang): string {
  const [y, m] = ym.split("-").map(Number);
  return lang === "en" ? `${MONTH_EN[m - 1]} ${y}` : `${y}年${m}月`;
}

export function monthName(m: number, lang: Lang): string {
  return lang === "en" ? MONTH_EN[m - 1] : `${m}月`;
}

export function weekday(day: string, lang: Lang): string {
  const w = parseDay(day).getDay();
  return lang === "en" ? WEEK_EN[w] : WEEK_ZH[w];
}

export function formatTime(ts: string | null | undefined): string {
  return ts ? ts.slice(11, 16) : "";
}

export function daysBetween(a: string, b: string): number {
  return Math.round((parseDay(b).getTime() - parseDay(a).getTime()) / 86_400_000);
}

/** "1 年 4 个月前" — calendar difference between a past day and today. */
export function agoText(day: string, lang: Lang, today: Date = new Date()): string {
  const then = parseDay(day);
  const now = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const totalDays = Math.round((now.getTime() - then.getTime()) / 86_400_000);
  if (totalDays === 0) return lang === "en" ? "today" : "今天";
  if (totalDays === 1) return lang === "en" ? "yesterday" : "昨天";
  if (totalDays < 0) return lang === "en" ? `in ${-totalDays} days` : `${-totalDays} 天后`;
  let months = (now.getFullYear() - then.getFullYear()) * 12 + (now.getMonth() - then.getMonth());
  if (now.getDate() < then.getDate()) months -= 1;
  if (months < 1) return lang === "en" ? `${totalDays} days ago` : `${totalDays} 天前`;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  if (lang === "en") {
    const parts = [];
    if (years) parts.push(`${years} year${years > 1 ? "s" : ""}`);
    if (rest) parts.push(`${rest} month${rest > 1 ? "s" : ""}`);
    return `${parts.join(", ")} ago`;
  }
  if (years && rest) return `${years} 年 ${rest} 个月前`;
  if (years) return `${years} 年前`;
  return `${rest} 个月前`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return "--:--";
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const p = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(sec)}` : `${m}:${p(sec)}`;
}

export function formatDurationLong(seconds: number, lang: Lang): string {
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (lang === "en") {
    if (h) return `${h} h ${m} min`;
    if (m) return `${m} min ${sec} s`;
    return `${sec} s`;
  }
  if (h) return `${h} 小时 ${m} 分钟`;
  if (m) return `${m} 分 ${sec} 秒`;
  return `${sec} 秒`;
}

export function num(n: number | null | undefined, lang: Lang = "zh"): string {
  return (n ?? 0).toLocaleString(lang === "en" ? "en-US" : "zh-CN");
}

export function hourLabel(h: number, lang: Lang): string {
  if (lang === "en") return `${h}:00`;
  return `${h} 点`;
}
