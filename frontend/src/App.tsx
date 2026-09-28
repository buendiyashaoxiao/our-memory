import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { MiniPlayer, TabBar } from "./components/Nav";
import { api, LOCKED_EVENT } from "./lib/api";
import { useIdle } from "./lib/hooks";
import { PlayerProvider } from "./lib/player";
import { AppProvider, useApp } from "./lib/store";
import type { LockStatus } from "./lib/types";
import DayView from "./pages/DayView";
import Favorites from "./pages/Favorites";
import Gallery from "./pages/Gallery";
import Home from "./pages/Home";
import Landing from "./pages/Landing";
import Lock from "./pages/Lock";
import MomentView from "./pages/MomentView";
import Moments from "./pages/Moments";
import RandomDay from "./pages/RandomDay";
import Review from "./pages/Review";
import Search from "./pages/Search";
import SettingsPage from "./pages/Settings";
import Sounds from "./pages/Sounds";
import StatsPage from "./pages/Stats";
import Timeline from "./pages/Timeline";

function Shell({ onLock }: { onLock: () => void }) {
  const location = useLocation();
  const { settings } = useApp();
  useIdle(settings?.auto_lock_minutes ?? 0, onLock);
  const bare = location.pathname === "/";
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);
  return (
    <div className={bare ? "" : "app"}>
      <main>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/home" element={<Home />} />
          <Route path="/timeline" element={<Timeline />} />
          <Route path="/day/:day" element={<DayView />} />
          <Route path="/random" element={<RandomDay />} />
          <Route path="/sounds" element={<Sounds />} />
          <Route path="/gallery" element={<Gallery />} />
          <Route path="/favorites" element={<Favorites />} />
          <Route path="/moments" element={<Moments />} />
          <Route path="/moments/:id" element={<MomentView />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/review" element={<Review />} />
          <Route path="/search" element={<Search />} />
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
      </main>
      {!bare && (
        <>
          <MiniPlayer />
          <TabBar />
        </>
      )}
    </div>
  );
}

export default function App() {
  const [status, setStatus] = useState<LockStatus | null>(null);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(() => {
    api
      .lockStatus()
      .then((s) => {
        setStatus(s);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);

  useEffect(() => {
    refresh();
    const onLocked = () => setStatus((s) => (s ? { ...s, unlocked: false } : s));
    window.addEventListener(LOCKED_EVENT, onLocked);
    return () => window.removeEventListener(LOCKED_EVENT, onLocked);
  }, [refresh]);

  const lockNow = useCallback(() => {
    api.lock().finally(() => setStatus((s) => (s ? { ...s, unlocked: !s.enabled } : s)));
  }, []);

  if (offline) {
    return (
      <div className="lock">
        <div className="error-box" role="alert" style={{ maxWidth: 360 }}>
          无法连接本地服务器。请确认 <code>python -m memory_museum serve</code> 正在运行，然后刷新页面。
          <br />
          Cannot reach the local server. Is it running?
          <div>
            <button className="btn small ghost" style={{ marginTop: 12 }} onClick={refresh}>
              重试 / Retry
            </button>
          </div>
        </div>
      </div>
    );
  }
  if (!status) return null;
  if (status.enabled && !status.unlocked) {
    return <Lock lang={status.language} onUnlocked={refresh} />;
  }
  return (
    <AppProvider initialLang={status.language}>
      <PlayerProvider>
        <Shell onLock={lockNow} />
      </PlayerProvider>
    </AppProvider>
  );
}
