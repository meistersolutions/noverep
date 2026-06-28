import { useState } from 'react';
import { ChevronDown, ChevronUp, Settings2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { api, UserPreferences } from '@/lib/api';
import { LanguageMultiSelect } from '@/components/LanguageMultiSelect';
import { DiscoveryYearRangeInput } from '@/components/DiscoveryYearRangeInput';
import { effectiveLanguages, languageLabels } from '@/lib/languages';
import { MEMORY_WINDOWS } from '@/lib/preferenceOptions';
import { usePlayerStore } from '@/stores/playerStore';

interface SearchPreferencesPanelProps {
  onPreferencesSaved?: () => void;
}

export function SearchPreferencesPanel({ onPreferencesSaved }: SearchPreferencesPanelProps) {
  const preferences = usePlayerStore((s) => s.preferences);
  const loadPreferences = usePlayerStore((s) => s.loadPreferences);
  const [open, setOpen] = useState(true);

  if (!preferences) {
    return <div className="glass h-24 animate-pulse rounded-xl" />;
  }

  const save = async (updates: Partial<UserPreferences>) => {
    try {
      await api.updatePreferences(updates);
      await loadPreferences();
      toast.success('Preferences updated');
      onPreferencesSaved?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save preferences');
      throw err;
    }
  };

  const langs = effectiveLanguages(preferences.preferred_languages, preferences.language_preference);
  const yearLabel =
    preferences.discovery_year_from || preferences.discovery_year_to
      ? `${preferences.discovery_year_from ?? '…'} – ${preferences.discovery_year_to ?? '…'}`
      : 'Any year';

  return (
    <section className="glass overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-white/5 transition-colors"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Settings2 className="w-5 h-5 text-accent shrink-0" />
          <div className="min-w-0">
            <p className="font-semibold text-sm">Your discovery preferences</p>
            <p className="text-xs text-white/50 truncate">
              {languageLabels(preferences.preferred_languages, preferences.language_preference)}
              {' · '}
              {yearLabel}
              {' · '}
              {MEMORY_WINDOWS.find((w) => w.value === preferences.memory_window)?.label ?? preferences.memory_window}
            </p>
          </div>
        </div>
        {open ? (
          <ChevronUp className="w-5 h-5 text-white/40 shrink-0" />
        ) : (
          <ChevronDown className="w-5 h-5 text-white/40 shrink-0" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-5 border-t border-white/10 pt-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">Preferred languages</p>
            <p className="text-xs text-white/50">
              Search, home, and queue use these languages.
            </p>
            <LanguageMultiSelect
              compact
              selected={langs}
              onChange={(preferred_languages) => save({ preferred_languages })}
            />
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">Discovery year range</p>
            <DiscoveryYearRangeInput
              compact
              yearFrom={preferences.discovery_year_from}
              yearTo={preferences.discovery_year_to}
              onSave={(discovery_year_from, discovery_year_to) =>
                save({ discovery_year_from, discovery_year_to })
              }
            />
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">Memory window</p>
            <p className="text-xs text-white/50">
              How long before a heard song can appear again in discover mode.
            </p>
            <select
              value={preferences.memory_window}
              onChange={(e) => save({ memory_window: e.target.value })}
              className="w-full bg-surface-raised border border-white/10 rounded-lg px-3 py-2 text-sm"
            >
              {MEMORY_WINDOWS.map((w) => (
                <option key={w.value} value={w.value}>
                  {w.label}
                </option>
              ))}
            </select>
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={!preferences.repeat_disabled}
              onChange={(e) => save({ repeat_disabled: !e.target.checked })}
              className="accent-accent w-4 h-4"
            />
            <div>
              <span className="text-sm font-medium">Discover new only</span>
              <p className="text-xs text-white/50">Hide songs heard within your memory window</p>
            </div>
          </label>

          <Link to="/settings" className="text-xs text-accent hover:underline inline-block">
            More settings (weights, blocked artists) →
          </Link>
        </div>
      )}
    </section>
  );
}
