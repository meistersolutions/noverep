import { useEffect, useState, lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { PlayerBar } from '@/components/PlayerBar';
import { OnboardingModal } from '@/components/OnboardingModal';
import { usePlayerStore } from '@/stores/playerStore';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import AuthPage from '@/pages/AuthPage';
import QueuePage from '@/pages/QueuePage';
import { api } from '@/lib/api';
import { Loader2 } from 'lucide-react';

const HomePage = lazy(() => import('@/pages/HomePage'));
const SearchPage = lazy(() => import('@/pages/SearchPage'));
const NowPlayingPage = lazy(() => import('@/pages/NowPlayingPage'));
const HistoryPage = lazy(() => import('@/pages/HistoryPage'));
const PlaylistsPage = lazy(() => import('@/pages/PlaylistsPage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));
const StatisticsPage = lazy(() => import('@/pages/StatisticsPage'));
const FeedbackPage = lazy(() => import('@/pages/FeedbackPage'));
const ProfilePage = lazy(() => import('@/pages/ProfilePage'));
const AdminPage = lazy(() => import('@/pages/AdminPage'));
const YouTubePlayer = lazy(() =>
  import('@/components/YouTubePlayer').then((m) => ({ default: m.YouTubePlayer })),
);

function RouteFallback() {
  return (
    <div className="flex items-center justify-center py-16">
      <Loader2 className="w-6 h-6 animate-spin text-accent" />
    </div>
  );
}

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
    if (token) init();
  }, [token, init]);

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
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<QueuePage />} />
            <Route path="/home" element={<HomePage />} />
            <Route path="/queue" element={<QueuePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/now-playing" element={<NowPlayingPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/playlists" element={<PlaylistsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/feedback" element={<FeedbackPage />} />
            <Route path="/statistics" element={<StatisticsPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </Suspense>
      </main>
      <MobileBottomNav />
      <Suspense fallback={null}>
        <YouTubePlayer />
      </Suspense>
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
