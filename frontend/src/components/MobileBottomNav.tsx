import { Home, Search, ListMusic, Disc3, Menu } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import clsx from 'clsx';

const tabs = [
  { to: '/', icon: Home, label: 'Home' },
  { to: '/search', icon: Search, label: 'Search' },
  { to: '/queue', icon: ListMusic, label: 'Queue' },
  { to: '/now-playing', icon: Disc3, label: 'Playing' },
  { to: '/profile', icon: Menu, label: 'More' },
];

export function MobileBottomNav() {
  return (
    <nav className="md:hidden fixed bottom-[6.5rem] left-0 right-0 z-40 glass border-t border-white/10 safe-bottom-nav">
      <div className="flex justify-around items-center px-1 py-1">
        {tabs.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                'flex flex-col items-center gap-0.5 py-2 px-3 min-w-[3.5rem] rounded-lg text-[10px] transition-colors',
                isActive ? 'text-accent' : 'text-white/50',
              )
            }
          >
            <Icon className="w-5 h-5" />
            <span>{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
