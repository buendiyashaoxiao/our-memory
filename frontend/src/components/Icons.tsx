import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;
const base = (p: P) => ({
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  ...p,
});

export const IconHome = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z" />
  </svg>
);
export const IconTimeline = (p: P) => (
  <svg {...base(p)}>
    <path d="M7 4v16M7 7h9M7 12h11M7 17h7" />
    <circle cx="7" cy="7" r="1.2" fill="currentColor" />
  </svg>
);
export const IconShuffle = (p: P) => (
  <svg {...base(p)}>
    <path d="M16 4h4v4M4 18l16-14M20 16v4h-4M14 14l6 6M4 6l5 5" />
  </svg>
);
export const IconWave = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2" />
  </svg>
);
export const IconImage = (p: P) => (
  <svg {...base(p)}>
    <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
    <circle cx="9" cy="10" r="1.6" />
    <path d="m20 16-4.5-4.5L7 19.5" />
  </svg>
);
export const IconStar = ({ filled, ...p }: P & { filled?: boolean }) => (
  <svg {...base(p)} fill={filled ? "currentColor" : "none"}>
    <path d="m12 4 2.4 5 5.3.6-4 3.6 1.1 5.3L12 15.8 7.2 18.5l1.1-5.3-4-3.6 5.3-.6z" />
  </svg>
);
export const IconPlay = (p: P) => (
  <svg {...base(p)} fill="currentColor" stroke="none">
    <path d="M8 5.5v13a.8.8 0 0 0 1.2.7l10.3-6.5a.8.8 0 0 0 0-1.4L9.2 4.8A.8.8 0 0 0 8 5.5z" />
  </svg>
);
export const IconPause = (p: P) => (
  <svg {...base(p)} fill="currentColor" stroke="none">
    <rect x="6.5" y="5" width="4" height="14" rx="1.2" />
    <rect x="13.5" y="5" width="4" height="14" rx="1.2" />
  </svg>
);
export const IconPrev = (p: P) => (
  <svg {...base(p)}>
    <path d="M15 6l-6 6 6 6" />
  </svg>
);
export const IconNext = (p: P) => (
  <svg {...base(p)}>
    <path d="M9 6l6 6-6 6" />
  </svg>
);
export const IconSkipNext = (p: P) => (
  <svg {...base(p)} fill="currentColor" stroke="none">
    <path d="M6 6.5v11a.7.7 0 0 0 1.1.6l8-5.5a.7.7 0 0 0 0-1.2l-8-5.5A.7.7 0 0 0 6 6.5z" />
    <rect x="16.5" y="6" width="2" height="12" rx="1" />
  </svg>
);
export const IconSkipPrev = (p: P) => (
  <svg {...base(p)} fill="currentColor" stroke="none">
    <path d="M18 6.5v11a.7.7 0 0 1-1.1.6l-8-5.5a.7.7 0 0 1 0-1.2l8-5.5a.7.7 0 0 1 1.1.6z" />
    <rect x="5.5" y="6" width="2" height="12" rx="1" />
  </svg>
);
export const IconClose = (p: P) => (
  <svg {...base(p)}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);
export const IconChat = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 18.5V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H8.5z" />
  </svg>
);
export const IconCamera = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.5-2h6l1.5 2h2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z" />
    <circle cx="12" cy="13" r="3.2" />
  </svg>
);
export const IconVideo = (p: P) => (
  <svg {...base(p)}>
    <rect x="3.5" y="6" width="12" height="12" rx="2" />
    <path d="m15.5 10.5 5-3v9l-5-3" />
  </svg>
);
export const IconMic = (p: P) => (
  <svg {...base(p)}>
    <rect x="9" y="3.5" width="6" height="11" rx="3" />
    <path d="M6 11a6 6 0 0 0 12 0M12 17v3.5" />
  </svg>
);
export const IconClock = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="8" />
    <path d="M12 8v4.5l3 1.8" />
  </svg>
);
export const IconBook = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 5.5A1.5 1.5 0 0 1 6.5 4H19v14H6.5A1.5 1.5 0 0 0 5 19.5z" />
    <path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19" />
  </svg>
);
export const IconChart = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 19V11M10 19V6M15 19v-5M20 19V9" />
  </svg>
);
export const IconSettings = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4M16.6 16.6 18 18M6 18l1.4-1.4M16.6 7.4 18 6" />
  </svg>
);
export const IconSearch = (p: P) => (
  <svg {...base(p)}>
    <circle cx="11" cy="11" r="6" />
    <path d="m20 20-4.5-4.5" />
  </svg>
);
export const IconCheck = (p: P) => (
  <svg {...base(p)}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </svg>
);
export const IconLock = (p: P) => (
  <svg {...base(p)}>
    <rect x="5" y="10.5" width="14" height="9.5" rx="2" />
    <path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" />
  </svg>
);
export const IconMore = (p: P) => (
  <svg {...base(p)}>
    <circle cx="6" cy="12" r="1.2" fill="currentColor" />
    <circle cx="12" cy="12" r="1.2" fill="currentColor" />
    <circle cx="18" cy="12" r="1.2" fill="currentColor" />
  </svg>
);
export const IconPlus = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);
export const IconEye = ({ off, ...p }: P & { off?: boolean }) => (
  <svg {...base(p)}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="2.8" />
    {off && <path d="M4 4l16 16" />}
  </svg>
);
export const IconLink = (p: P) => (
  <svg {...base(p)}>
    <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
  </svg>
);
export const IconSparkle = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 4v4M12 16v4M4 12h4M16 12h4M7 7l2 2M15 15l2 2M7 17l2-2M15 9l2-2" />
  </svg>
);
