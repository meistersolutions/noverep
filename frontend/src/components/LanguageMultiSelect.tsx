import { Check } from 'lucide-react';
import { LanguageCode, SELECTABLE_LANGUAGES } from '@/lib/languages';

interface LanguageMultiSelectProps {
  selected: LanguageCode[];
  onChange: (langs: LanguageCode[]) => void;
  compact?: boolean;
}

export function LanguageMultiSelect({ selected, onChange, compact = false }: LanguageMultiSelectProps) {
  const toggle = (code: LanguageCode) => {
    if (selected.includes(code)) {
      if (selected.length === 1) return;
      onChange(selected.filter((c) => c !== code));
    } else {
      onChange([...selected, code]);
    }
  };

  const selectAll = () => onChange(SELECTABLE_LANGUAGES.map((o) => o.value));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {SELECTABLE_LANGUAGES.map((opt) => {
          const active = selected.includes(opt.value);
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => toggle(opt.value)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-full text-sm transition-all border ${
                active
                  ? 'bg-accent/20 border-accent text-white'
                  : 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10'
              }`}
            >
              {active && <Check className="w-3.5 h-3.5" />}
              {opt.label}
            </button>
          );
        })}
      </div>
      {!compact && (
        <div className="flex items-center justify-between text-xs text-white/40">
          <span>Select one or more languages for search and discovery.</span>
          <button type="button" className="text-accent hover:underline" onClick={selectAll}>
            Select all
          </button>
        </div>
      )}
    </div>
  );
}
