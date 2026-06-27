import { Link } from 'react-router-dom';
import {
  History,
  BarChart3,
  Settings,
  MessageSquare,
  ListMusic,
  LogOut,
  ChevronRight,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';
import { MobileHeader } from '@/components/MobileHeader';
import { DiscoverModeToggle } from '@/components/DiscoverModeToggle';
import { languageLabels } from '@/lib/languages';
import toast from 'react-hot-toast';

const menuLinks = [
  { to: '/history', icon: History, label: 'History' },
  { to: '/statistics', icon: BarChart3, label: 'Statistics' },
  { to: '/playlists', icon: ListMusic, label: 'Playlists' },
  { to: '/settings', icon: Settings, label: 'Settings' },
  { to: '/feedback', icon: MessageSquare, label: 'Feedback' },
];

export default function ProfilePage() {
  const navigate = useNavigate();
  const logout = usePlayerStore((s) => s.logout);
  const preferences = usePlayerStore((s) => s.preferences);
  const [user, setUser] = useState<{
    id: string;
    username: string;
    display_name: string;
    email: string | null;
    is_guest: boolean;
  } | null>(null);

  useEffect(() => {
    api.getMe().then(setUser).catch(() => {});
  }, []);

  const handleLogout = () => {
    logout();
    toast.success('Signed out');
    navigate('/auth');
  };

  return (
    <div className="space-y-6 max-w-md">
      <MobileHeader title="More" />

      {user && (
        <div className="glass p-5 space-y-2">
          <p className="text-2xl font-bold">{user.display_name}</p>
          <p className="text-sm text-white/50">@{user.username}</p>
          {user.is_guest && (
            <p className="text-xs text-yellow-400 pt-1">
              Guest account — register to save your profile
            </p>
          )}
        </div>
      )}

      <DiscoverModeToggle />

      <nav className="glass divide-y divide-white/10 overflow-hidden">
        {menuLinks.map(({ to, icon: Icon, label }) => (
          <Link
            key={to}
            to={to}
            className="flex items-center justify-between px-4 py-3.5 hover:bg-white/5 active:bg-white/10"
          >
            <span className="flex items-center gap-3">
              <Icon className="w-5 h-5 text-white/60" />
              {label}
            </span>
            <ChevronRight className="w-4 h-4 text-white/30" />
          </Link>
        ))}
      </nav>

      {preferences && (
        <div className="glass p-4 text-sm space-y-1">
          <p>
            <span className="text-white/50">Language: </span>
            {languageLabels(preferences.preferred_languages, preferences.language_preference)}
          </p>
          <p>
            <span className="text-white/50">Artists: </span>
            {preferences.favorite_artists?.join(', ') || 'None'}
          </p>
        </div>
      )}

      <button
        onClick={handleLogout}
        className="w-full glass-hover py-3.5 flex items-center justify-center gap-2 text-red-400"
      >
        <LogOut className="w-4 h-4" />
        Sign out
      </button>
    </div>
  );
}
