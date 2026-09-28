import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { VoicePlayer } from "../components/VoicePlayer";
import { dayCard, dayDetail, media, mockApi, renderPage } from "../test/utils";
import DayView from "./DayView";
import Landing from "./Landing";
import Lock from "./Lock";
import RandomDay from "./RandomDay";
import Sounds from "./Sounds";
import Timeline from "./Timeline";

describe("Landing", () => {
  it("shows the configurable intro and enters the museum", async () => {
    mockApi({});
    renderPage(<Landing />);
    expect(await screen.findByRole("heading", { name: "我们的回忆馆" })).toBeInTheDocument();
    expect(screen.getByText("后来回头看才知道很重要。")).toBeInTheDocument();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fireEvent.click(screen.getByRole("button", { name: "进入" }));
    await act(() => vi.advanceTimersByTimeAsync(700));
    expect(screen.getByTestId("elsewhere")).toBeInTheDocument();
    vi.useRealTimers();
  });
});

describe("Timeline", () => {
  it("renders day cards and switches to every day", async () => {
    const { calls } = mockApi({
      "/api/timeline/years": [{ year: 2025, days: 2, messages: 20, photos: 2, videos: 0, voices: 0, months: [] }],
      "/api/timeline": (url: URL) => ({
        items: url.searchParams.get("mode") === "all" ? [dayCard("2025-05-01"), dayCard("2025-05-02")] : [dayCard("2025-05-01")],
        next_cursor: null,
      }),
    });
    renderPage(<Timeline />);
    expect(await screen.findByText("那天的话 2025-05-01")).toBeInTheDocument();
    expect(screen.queryByText("那天的话 2025-05-02")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "全部日子" }));
    expect(await screen.findByText("那天的话 2025-05-02")).toBeInTheDocument();
    expect(calls.some((c) => c.url.pathname === "/api/timeline" && c.url.searchParams.get("mode") === "all")).toBe(true);
  });

  it("opens a photo in the lightbox", async () => {
    mockApi({ "/api/timeline/years": [], "/api/timeline": { items: [dayCard("2025-05-01")], next_cursor: null } });
    renderPage(<Timeline />);
    const thumb = await screen.findByRole("button", { name: /照片 2025-05-01 11:23/ });
    await userEvent.click(thumb);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /那一天我们还说了什么/ })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("Random Day", () => {
  it("shows a day and asks for another one, excluding the current day", async () => {
    let n = 0;
    const { calls } = mockApi({
      "/api/random-day": () => dayDetail(n++ === 0 ? "2025-05-01" : "2025-06-18"),
    });
    renderPage(<RandomDay />, { path: "/random", route: "/random" });
    expect(await screen.findByText("excerpt of 2025-05-01")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /前一天/ })).toBeEnabled();
    expect(screen.getByRole("link", { name: "查看完整当天记录" })).toHaveAttribute("href", "/day/2025-05-01");
    await userEvent.click(screen.getByRole("button", { name: /再随机一天/ }));
    expect(await screen.findByText("excerpt of 2025-06-18")).toBeInTheDocument();
    const second = calls.filter((c) => c.url.pathname === "/api/random-day")[1];
    expect(second.url.searchParams.get("exclude")).toBe("2025-05-01");
  });

  it("navigates to the previous day", async () => {
    const { calls } = mockApi({
      "/api/random-day": dayDetail("2025-05-01"),
      "/api/days/2025-04-30": dayDetail("2025-04-30", { excerpts: [] }),
    });
    renderPage(<RandomDay />, { path: "/random", route: "/random" });
    await screen.findByText("excerpt of 2025-05-01");
    await userEvent.click(screen.getByRole("button", { name: /前一天/ }));
    await waitFor(() => expect(calls.some((c) => c.url.pathname === "/api/days/2025-04-30")).toBe(true));
  });

  it("shows an empty state when there is nothing yet", async () => {
    mockApi({ "/api/random-day": { day: null } });
    renderPage(<RandomDay />, { path: "/random", route: "/random" });
    expect(await screen.findByText("还没有可以回去的日子。")).toBeInTheDocument();
  });
});

describe("Sound Museum", () => {
  const voice = media(5, { type: "voice", duration: 12, waveform: [0.1, 0.9, 0.4], title: "一个普通的晚安",
    context: [] });

  it("lists voices and plays one without autoplaying", async () => {
    mockApi({ "/api/sounds": { items: [voice, media(6, { type: "voice", duration: 3 })], next_cursor: null, total: 2, total_seconds: 15 } });
    renderPage(<Sounds />);
    expect(await screen.findByText("一个普通的晚安")).toBeInTheDocument();
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    await userEvent.click(screen.getAllByRole("button", { name: /播放 语音/ })[0]);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: /暂停 语音/ })).toBeInTheDocument();
  });

  it("saves a private title", async () => {
    const { calls } = mockApi({
      "/api/sounds": { items: [{ ...voice, title: null }], next_cursor: null, total: 1, total_seconds: 12 },
      "/api/media/5": (_u: URL, init?: RequestInit) => ({ ...voice, ...JSON.parse(String(init?.body ?? "{}")) }),
    });
    renderPage(<Sounds />);
    await userEvent.click(await screen.findByRole("button", { name: "写一个标题" }));
    await userEvent.type(screen.getByPlaceholderText("比如：一个普通的晚安"), "那天你在路上");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByText("那天你在路上")).toBeInTheDocument();
    const patch = calls.find((c) => c.init?.method === "PATCH");
    expect(JSON.parse(String(patch?.init?.body))).toMatchObject({ title: "那天你在路上" });
  });

  it("disables playback for formats the browser cannot play", async () => {
    mockApi({});
    renderPage(<VoicePlayer media={media(7, { type: "voice", playable: false })} />);
    expect(await screen.findByRole("button", { name: /播放/ })).toBeDisabled();
  });
});

describe("Day view", () => {
  it("shows chat, stats and neighbours, and favorites the day", async () => {
    const { calls } = mockApi({ "/api/days/2025-05-01": dayDetail("2025-05-01"), "/api/favorites": {} });
    renderPage(<DayView />, { path: "/day/:day", route: "/day/2025-05-01" });
    expect(await screen.findByText("早呀")).toBeInTheDocument();
    expect(screen.getByText("从 06:40 聊到 22:16")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /2025年4月30日/ })).toHaveAttribute("href", "/day/2025-04-30");
    await userEvent.click(screen.getAllByRole("button", { name: "收藏" })[0]);
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PUT" && c.url.pathname === "/api/favorites/day/2025-05-01")).toBe(true));
  });
});

describe("Lock", () => {
  it("rejects a wrong PIN and accepts the right one", async () => {
    mockApi({
      "/api/lock/unlock": (_u: URL, init?: RequestInit) =>
        JSON.parse(String(init?.body)).pin === "2468"
          ? { unlocked: true }
          : new Response(JSON.stringify({ detail: "wrong PIN" }), { status: 403 }),
    });
    const onUnlocked = vi.fn();
    renderPage(<Lock lang="zh" onUnlocked={onUnlocked} />);
    const input = screen.getByLabelText("PIN");
    await userEvent.type(input, "0000{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("PIN 不对");
    await userEvent.type(input, "2468{Enter}");
    await waitFor(() => expect(onUnlocked).toHaveBeenCalled());
  });
});
