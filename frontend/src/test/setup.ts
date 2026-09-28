import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
Object.defineProperty(HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: vi.fn(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  }),
});
Object.defineProperty(HTMLMediaElement.prototype, "pause", {
  configurable: true,
  value: vi.fn(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("pause"));
  }),
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
