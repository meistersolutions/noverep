import { NavLink } from 'react-router-dom';
import {
  Home,
  Search,
  ListMusic,
  History,
  BarChart3,
  Settings,
  User,
  Music2,
  Disc3,
  MessageSquare,
  Shield,
} from 'lucide-react';
import clsx from 'clsx';
import { usePlayerStore } from '@/stores/playerStore';

const links = [
  { to: '/', icon: ListMusic, label: 'Queue' },
  { to: '/home', icon: Home, label: 'Home' },
  { to: '/search', icon: Search, label: 'Search' },
  { to: '/now-playing', icon: Disc3, label: 'Now Playing' },
  { to: '/history', icon: History, label: 'History' },
  { to: '/playlists', icon: Music2, label: 'Playlists' },
  { to: '/statistics', icon: BarChart3, label: 'Statistics' },
  { to: '/settings', icon: Settings, label: 'Settings' },
  { to: '/feedback', icon: MessageSquare, label: 'Feedback' },
  { to: '/profile', icon: User, label: 'Profile' },
];

export function Sidebar() {
  const isAdmin = usePlayerStore((s) => s.isAdmin);
  const navLinks = isAdmin
    ? [...links, { to: '/admin', icon: Shield, label: 'Admin' }]
    : links;

  return (
    <aside className="hidden md:flex flex-col w-64 glass m-4 mr-0 p-4 shrink-0">
      <div className="flex items-center gap-3 px-2 mb-8">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent to-purple-400 flex items-center justify-center">
          <Disc3 className="w-6 h-6" />
        </div>
        <div>
          <h1 className="font-bold text-lg tracking-tight">NoRepeat</h1>
          <p className="text-xs text-white/50">Never hear the same song twice</p>
        </div>
      </div>
      <nav className="flex flex-col gap-1 flex-1">
        {navLinks.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors',
                isActive
                  ? 'bg-accent/20 text-accent-hover font-medium'
                  : 'text-white/70 hover:text-white hover:bg-white/5',
              )
            }
          >
            <Icon className="w-5 h-5" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
