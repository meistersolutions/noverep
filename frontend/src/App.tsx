import { useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { PlayerBar } from '@/components/PlayerBar';
import { YouTubePlayer } from '@/components/YouTubePlayer';
import { OnboardingModal } from '@/components/OnboardingModal';
import { usePlayerStore } from '@/stores/playerStore';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import AuthPage from '@/pages/AuthPage';
import HomePage from '@/pages/HomePage';
import SearchPage from '@/pages/SearchPage';
import QueuePage from '@/pages/QueuePage';
import NowPlayingPage from '@/pages/NowPlayingPage';
import HistoryPage from '@/pages/HistoryPage';
import PlaylistsPage from '@/pages/PlaylistsPage';
import SettingsPage from '@/pages/SettingsPage';
import StatisticsPage from '@/pages/StatisticsPage';
import FeedbackPage from '@/pages/FeedbackPage';
import ProfilePage from '@/pages/ProfilePage';
import AdminPage from '@/pages/AdminPage';
import { api } from '@/lib/api';
import { Loader2 } from 'lucide-react';

function MainApp() {
  const init = usePlayerStore((s) => s.init);
  const initialized = usePlayerStore((s) => s.initialized);
  const queueBuilding = usePlayerStore((s) => s.queueBuilding);
  const token = usePlayerStore((s) => s.token);
  const preferences = usePlayerStore((s) => s.preferences);
  const loadPreferences = usePlayerStore((s) => s.loadPreferences);
  const [showOnboarding, setShowOnboarding] = useState(false);

  useKeyboardShortcuts();

  useEffect(() => {
    if (token && !initialized) init();
  }, [token, initialized, init]);

  useEffect(() => {
    if (initialized && preferences && !preferences.onboarding_completed) {
      setShowOnboarding(true);
    }
  }, [initialized, preferences]);

  const handleOnboardingComplete = async () => {
    setShowOnboarding(false);
    await loadPreferences();
    const me = await api.getMe();
    localStorage.setItem('noverep_display_name', me.display_name);
  };

  if (!token) return <Navigate to="/auth" replace />;
  if (!initialized) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="glass p-8 flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <p className="text-white/60">Loading NoRepeat...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen pb-40 md:pb-24">
      {showOnboarding && <OnboardingModal onComplete={handleOnboardingComplete} />}
      {queueBuilding && (
        <div className="fixed top-0 left-0 right-0 z-[60] bg-accent/15 border-b border-accent/30 px-4 py-2 text-center text-xs text-accent flex items-center justify-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Building your discovery queue in the background…
        </div>
      )}
      <Sidebar />
      <main className="flex-1 p-4 md:p-6 overflow-auto w-full max-w-full">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/now-playing" element={<NowPlayingPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/playlists" element={<PlaylistsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/feedback" element={<FeedbackPage />} />
          <Route path="/statistics" element={<StatisticsPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </main>
      <MobileBottomNav />
      <YouTubePlayer />
      <PlayerBar />
    </div>
  );
}

export default function App() {
  const token = usePlayerStore((s) => s.token);

  return (
    <Routes>
      <Route
        path="/auth"
        element={token ? <Navigate to="/" replace /> : <AuthPage />}
      />
      <Route path="/*" element={<MainApp />} />
    </Routes>
  );
}
