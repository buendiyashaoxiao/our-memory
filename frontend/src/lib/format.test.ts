import { describe, expect, it } from "vitest";
import { addDays, agoText, daysBetween, formatDay, formatDuration, formatDurationLong, formatMonthDay } from "./format";
import { translate } from "./i18n";

describe("format", () => {
  const today = new Date(2026, 8, 28);

  it("formats days in both languages", () => {
    expect(formatDay("2025-05-01", "zh")).toBe("2025年5月1日");
    expect(formatDay("2025-05-01", "en")).toBe("May 1, 2025");
    expect(formatDay("2025-05-01", "zh", "numeric")).toBe("2025.05.01");
    expect(formatMonthDay("2025-12-09", "zh")).toBe("12月9日");
  });

  it("describes how long ago a day was", () => {
    expect(agoText("2026-09-28", "zh", today)).toBe("今天");
    expect(agoText("2026-09-27", "zh", today)).toBe("昨天");
    expect(agoText("2026-09-10", "zh", today)).toBe("18 天前");
    expect(agoText("2025-05-01", "zh", today)).toBe("1 年 4 个月前");
    expect(agoText("2025-09-28", "zh", today)).toBe("1 年前");
    expect(agoText("2025-05-01", "en", today)).toBe("1 year, 4 months ago");
    expect(agoText("2026-06-29", "zh", today)).toBe("2 个月前");
  });

  it("does date arithmetic across month boundaries", () => {
    expect(addDays("2025-02-28", 1)).toBe("2025-03-01");
    expect(daysBetween("2025-03-01", "2025-05-01")).toBe(61);
  });

  it("formats durations", () => {
    expect(formatDuration(6.08)).toBe("0:06");
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(null)).toBe("--:--");
    expect(formatDurationLong(416, "zh")).toBe("6 分 56 秒");
  });

  it("interpolates translations", () => {
    expect(translate("zh", "common.messages", { n: 3 })).toBe("3 条消息");
    expect(translate("en", "random.ago", { ago: "today" })).toBe("That was today");
  });
});
