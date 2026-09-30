// Renders promo.html frame-by-frame and encodes a 1080x1920 MP4.
// Usage: node render.mjs [--stills 2,6,14,...]  (needs playwright + ffmpeg; FFMPEG env overrides path)
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const dir = path.dirname(fileURLToPath(import.meta.url));
const FPS = 30;
const ffmpeg = process.env.FFMPEG || 'ffmpeg';
const stillsArg = process.argv.indexOf('--stills');
const frameDir = path.join(dir, 'frames');

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
await page.goto('file://' + path.join(dir, 'promo.html') + '?capture');
await page.evaluate(() => window.ready);
await page.waitForTimeout(500);

if (stillsArg > 0) {
  for (const t of process.argv[stillsArg + 1].split(',').map(Number)) {
    await page.evaluate(t => window.render(t), t);
    await page.screenshot({ path: path.join(dir, `still_${t}.png`) });
  }
} else {
  rmSync(frameDir, { recursive: true, force: true });
  mkdirSync(frameDir);
  const dur = await page.evaluate(() => window.DURATION);
  const n = Math.round(dur * FPS);
  for (let i = 0; i < n; i++) {
    await page.evaluate(t => window.render(t), i / FPS);
    await page.screenshot({ path: path.join(frameDir, `f${String(i).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 95 });
  }
  execFileSync(ffmpeg, ['-y', '-framerate', String(FPS), '-i', path.join(frameDir, 'f%05d.jpg'),
    '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-shortest',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'slow', '-movflags', '+faststart',
    '-c:a', 'aac', path.join(dir, 'promo.mp4')], { stdio: 'inherit' });
  rmSync(frameDir, { recursive: true, force: true });
}
await browser.close();
