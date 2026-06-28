import { useEffect, useState } from 'react';
import { api, Statistics } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';

export default function StatisticsPage() {
  const [stats, setStats] = useState<Statistics | null>(null);
  const historyVersion = usePlayerStore((s) => s.historyVersion);

  const load = () => api.getStatistics().then(setStats);

  useEffect(() => {
    load();
  }, [historyVersion]);

  if (!stats) return <div className="animate-pulse glass h-96" />;

  const maxHour = Math.max(...stats.listening_by_hour, 1);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Statistics</h2>
        <button className="btn-ghost text-sm" onClick={load}>
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Songs Played', value: stats.songs_played },
          { label: 'Artists Explored', value: stats.artists_explored },
          { label: 'Genres Explored', value: stats.genres_explored },
          { label: 'Discovery Score', value: stats.discovery_score },
          { label: 'Listening Streak', value: `${stats.listening_streak_days} days` },
          { label: 'Repeat Avoided', value: stats.repeat_avoidance_count },
          { label: 'Albums Explored', value: stats.albums_explored },
        ].map(({ label, value }) => (
          <div key={label} className="glass p-5">
            <p className="text-sm text-white/50">{label}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
          </div>
        ))}
      </div>

      <section className="glass p-6">
        <h3 className="font-semibold mb-4">Listening by Hour</h3>
        <div className="flex items-end gap-1 h-32">
          {stats.listening_by_hour.map((count, hour) => (
            <div key={hour} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full bg-accent/80 rounded-t"
                style={{ height: `${(count / maxHour) * 100}%`, minHeight: count ? 4 : 0 }}
              />
              <span className="text-[10px] text-white/30">{hour}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="grid md:grid-cols-2 gap-6">
        <section className="glass p-6">
          <h3 className="font-semibold mb-4">Top Genres</h3>
          <ul className="space-y-2">
            {stats.most_explored_genres.map((g) => (
              <li key={g.name} className="flex justify-between text-sm">
                <span>{g.name}</span>
                <span className="text-white/50">{g.count}</span>
              </li>
            ))}
            {stats.most_explored_genres.length === 0 && (
              <li className="text-white/50 text-sm">Play songs to see stats</li>
            )}
          </ul>
        </section>
        <section className="glass p-6">
          <h3 className="font-semibold mb-4">Top Artists</h3>
          <ul className="space-y-2">
            {stats.top_artists.map((a) => (
              <li key={a.name} className="flex justify-between text-sm">
                <span>{a.name}</span>
                <span className="text-white/50">{a.count}</span>
              </li>
            ))}
            {stats.top_artists.length === 0 && (
              <li className="text-white/50 text-sm">Play songs to see stats</li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
