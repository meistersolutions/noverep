import { useEffect, useState } from 'react';
import { api, UserPreferences } from '@/lib/api';
import toast from 'react-hot-toast';
import { LanguageMultiSelect } from '@/components/LanguageMultiSelect';
import { effectiveLanguages, languageLabels } from '@/lib/languages';

const MEMORY_WINDOWS = [
  { value: '1d', label: '1 day' },
  { value: '7d', label: '7 days' },
  { value: '15d', label: '15 days' },
  { value: '30d', label: '30 days' },
  { value: '60d', label: '60 days' },
  { value: '90d', label: '90 days' },
  { value: '365d', label: '1 year' },
  { value: 'forever', label: 'Forever' },
];

const WEIGHT_LABELS: Record<string, string> = {
  artist_diversity: 'Artist Diversity',
  genre_diversity: 'Genre Diversity',
  album_diversity: 'Album Diversity',
  language_diversity: 'Language Diversity',
  year_diversity: 'Release Year Diversity',
  popularity: 'Popularity',
  freshness: 'Freshness',
  randomness: 'Randomness',
  time_of_day: 'Time of Day',
  history_penalty: 'History Penalty',
  session_length: 'Session Length',
};

export default function SettingsPage() {
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);
  const [blockedArtist, setBlockedArtist] = useState('');

  useEffect(() => {
    api.getPreferences().then(setPrefs);
  }, []);

  const save = async (updates: Partial<UserPreferences>) => {
    const updated = await api.updatePreferences(updates);
    setPrefs(updated);
    toast.success('Settings saved');
  };

  if (!prefs) return <div className="animate-pulse glass h-96" />;

  const weights = { ...prefs.recommendation_weights };

  return (
    <div className="space-y-8 max-w-2xl">
      <h2 className="text-2xl font-bold">Settings</h2>

      <section className="glass p-6 space-y-4">
        <h3 className="font-semibold text-lg">Discovery Mode</h3>
        <p className="text-sm text-white/50">
          Choose whether to hide songs you have already heard within your memory window.
        </p>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={!prefs.repeat_disabled}
            onChange={(e) => save({ repeat_disabled: !e.target.checked })}
            className="accent-accent w-5 h-5"
          />
          <div>
            <span className="font-medium">Discover new only</span>
            <p className="text-xs text-white/50">Hide songs heard within your memory window</p>
          </div>
        </label>
      </section>

      <section className="glass p-6 space-y-4">
        <h3 className="font-semibold text-lg">Memory Window</h3>
        <p className="text-sm text-white/50">How long before a song can play again in discover mode.</p>
        <p className="text-sm text-white/50">Songs won't repeat within this period unless you request them.</p>
        <select
          value={prefs.memory_window}
          onChange={(e) => save({ memory_window: e.target.value })}
          className="w-full bg-surface-raised border border-white/10 rounded-lg px-4 py-3 text-base"
        >
          {MEMORY_WINDOWS.map((w) => (
            <option key={w.value} value={w.value}>{w.label}</option>
          ))}
        </select>
      </section>

      <section className="glass p-6 space-y-4">
        <h3 className="font-semibold text-lg">Preferred Languages</h3>
        <p className="text-sm text-white/50">
          Pick one or more languages for search, home, and queue. Tamil + Ilaiyaraaja will not
          surface his Telugu songs.
        </p>
        <LanguageMultiSelect
          selected={effectiveLanguages(prefs.preferred_languages, prefs.language_preference)}
          onChange={(langs) => save({ preferred_languages: langs })}
        />
        <p className="text-xs text-white/40">
          Active: {languageLabels(prefs.preferred_languages, prefs.language_preference)}
        </p>
      </section>

      <section className="glass p-6 space-y-4">
        <h3 className="font-semibold text-lg">Discovery Year Range</h3>
        <p className="text-sm text-white/50">
          Limit discovery to songs from a specific year range. Leave blank for any year.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <label className="space-y-1">
            <span className="text-sm text-white/60">From year</span>
            <input
              type="number"
              min={1950}
              max={2100}
              placeholder="e.g. 2010"
              value={prefs.discovery_year_from ?? ''}
              onChange={(e) =>
                save({
                  discovery_year_from: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="w-full bg-surface-raised border border-white/10 rounded-lg px-4 py-2"
            />
          </label>
          <label className="space-y-1">
            <span className="text-sm text-white/60">To year</span>
            <input
              type="number"
              min={1950}
              max={2100}
              placeholder="e.g. 2020"
              value={prefs.discovery_year_to ?? ''}
              onChange={(e) =>
                save({
                  discovery_year_to: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="w-full bg-surface-raised border border-white/10 rounded-lg px-4 py-2"
            />
          </label>
        </div>
      </section>

      <section className="glass p-6 space-y-4">
        <h3 className="font-semibold text-lg">Playback</h3>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={prefs.autoplay}
            onChange={(e) => save({ autoplay: e.target.checked })}
            className="accent-accent"
          />
          <span>Autoplay next track</span>
        </label>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={prefs.shuffle}
            onChange={(e) => save({ shuffle: e.target.checked })}
            className="accent-accent"
          />
          <span>Shuffle</span>
        </label>
        <label className="flex items-center gap-3 cursor-pointer opacity-50">
          <input type="checkbox" checked={prefs.crossfade_enabled} disabled className="accent-accent" />
          <span>Crossfade (coming soon)</span>
        </label>
        <label className="flex items-center gap-3 cursor-pointer opacity-50">
          <input type="checkbox" checked={prefs.gapless_enabled} disabled className="accent-accent" />
          <span>Gapless playback (coming soon)</span>
        </label>
      </section>

      <section className="glass p-6 space-y-4">
        <h3 className="font-semibold text-lg">Recommendation Weights</h3>
        {Object.entries(WEIGHT_LABELS).map(([key, label]) => (
          <div key={key}>
            <div className="flex justify-between text-sm mb-1">
              <span>{label}</span>
              <span className="text-white/50">{(weights[key] ?? 0.5).toFixed(1)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={weights[key] ?? 0.5}
              onChange={(e) => {
                weights[key] = Number(e.target.value);
                save({ recommendation_weights: { ...weights } });
              }}
              className="w-full accent-accent"
            />
          </div>
        ))}
      </section>

      <section className="glass p-6 space-y-4">
        <h3 className="font-semibold text-lg">Blocked Artists</h3>
        <div className="flex gap-2">
          <input
            value={blockedArtist}
            onChange={(e) => setBlockedArtist(e.target.value)}
            placeholder="Artist name"
            className="flex-1 bg-surface-raised border border-white/10 rounded-lg px-4 py-2"
          />
          <button
            className="btn-primary"
            onClick={() => {
              if (!blockedArtist.trim()) return;
              save({ blocked_artists: [...prefs.blocked_artists, blockedArtist.trim()] });
              setBlockedArtist('');
            }}
          >
            Block
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {prefs.blocked_artists.map((a) => (
            <span
              key={a}
              className="px-3 py-1 rounded-full bg-red-500/20 text-red-300 text-sm cursor-pointer"
              onClick={() => save({ blocked_artists: prefs.blocked_artists.filter((x) => x !== a) })}
            >
              {a} ×
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
