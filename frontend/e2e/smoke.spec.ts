import { expect, test } from "@playwright/test";

/**
 * Smoke test: launch → museum → timeline → a day → open/play media → Random Day → Sound Museum.
 * Runs against the real backend serving the built frontend and the fictional demo data.
 */
test("walk through the museum", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  // Launch + intro
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "我们的回忆馆" })).toBeVisible();
  await page.getByRole("button", { name: "进入" }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole("heading", { name: "林夏 和 周屿" })).toBeVisible();

  // Timeline
  await page.getByRole("navigation", { name: "main" }).getByRole("link", { name: "时间线" }).click();
  await expect(page.getByRole("heading", { name: "时间线" })).toBeVisible();
  const firstCard = page.locator("article.day-card").first();
  await expect(firstCard).toBeVisible();

  // Select a day
  await firstCard.getByRole("link", { name: "查看这一天", exact: true }).click();
  await expect(page).toHaveURL(/\/day\/2025-03-01$/);
  await expect(page.getByRole("heading", { name: "这一天的聊天" })).toBeVisible();
  await expect(page.locator(".msg").first()).toBeVisible();

  // Open a photo full screen, and its surrounding chat
  await page.locator(".strip button.thumb").first().click();
  const lightbox = page.getByRole("dialog").first();
  await expect(lightbox).toBeVisible();
  const img = lightbox.locator(".stage img");
  await expect(img).toBeVisible();
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
  await page.getByRole("button", { name: "那一天我们还说了什么" }).click();
  await expect(page.getByRole("heading", { name: "那一天我们还说了什么" })).toBeVisible();
  await expect(page.locator(".sheet .bubble.highlight")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await expect(page.locator(".lightbox")).toHaveCount(0);

  // A video opens in a real <video> element served with range support
  await page.goto("/gallery");
  await page.getByRole("button", { name: "视频", exact: true }).click();
  await page.locator(".grid button.thumb").first().click();
  // Test Chromium has no H.264 decoder; real browsers play it. Either way the UI must say something truthful.
  const video = page.locator(".lightbox video");
  const fallback = page.getByRole("link", { name: "打开原文件" });
  await expect(video.or(fallback)).toBeVisible();
  const src = (await video.count()) ? await video.getAttribute("src") : await fallback.getAttribute("href");
  expect(src).toMatch(/^\/api\/media\/\d+\/file$/);
  const head = await page.request.get(src!, { headers: { Range: "bytes=0-99" } });
  expect(head.status()).toBe(206);
  await page.keyboard.press("Escape");

  // Random Day
  await page.getByRole("navigation", { name: "main" }).getByRole("link", { name: "随机回到一天" }).click();
  await expect(page).toHaveURL(/\/random\?day=\d{4}-\d{2}-\d{2}$/);
  const firstDay = new URL(page.url()).searchParams.get("day");
  await expect(page.locator(".ago")).toContainText("那是");
  await page.getByRole("button", { name: /再随机一天/ }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("day")).not.toBe(firstDay);
  await expect(page.getByRole("link", { name: "查看完整当天记录" })).toBeVisible();
  await page.getByRole("button", { name: /前一天/ }).click();
  await expect(page.locator(".random-stage")).toBeVisible();

  // Sound Museum: play the first voice (MP3) and check playback really advances
  await page.getByRole("navigation", { name: "main" }).getByRole("link", { name: "声音" }).click();
  await expect(page.getByRole("heading", { name: "声音博物馆" })).toBeVisible();
  const card = page.locator("article.sound-card").first();
  await card.getByRole("button", { name: /播放 语音/ }).click();
  await expect(page.getByRole("region", { name: "正在播放" })).toBeVisible();
  await expect(card.getByRole("button", { name: /暂停 语音/ })).toBeVisible();
  await expect.poll(async () => card.locator(".wave i.on").count(), { timeout: 10_000 }).toBeGreaterThan(0);

  expect(errors).toEqual([]);
});

test("broken and missing media fail gracefully", async ({ page }) => {
  const res = await page.request.get("/api/review/summary");
  expect((await res.json()).problems).toBe(3);
  // An image message whose file was lost renders a placeholder instead of breaking the day
  await page.goto("/day/2025-03-15");
  await expect(page.getByText("文件未找到").first()).toBeVisible();
  expect((await page.request.get("/api/media/999999/file")).status()).toBe(404);
});
