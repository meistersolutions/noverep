import { useState } from 'react';
import { User, Globe, Music2, ChevronRight, Check } from 'lucide-react';
import { api } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';
import { artistsForLanguage, artistInitials } from '@/lib/artists';
import { LanguageCode, SELECTABLE_LANGUAGES } from '@/lib/languages';
import { LanguageMultiSelect } from '@/components/LanguageMultiSelect';
import toast from 'react-hot-toast';

interface OnboardingModalProps {
  onComplete: () => void;
}

export function OnboardingModal({ onComplete }: OnboardingModalProps) {
  const [step, setStep] = useState(0);
  const [displayName, setDisplayName] = useState('');
  const [selectedLanguages, setSelectedLanguages] = useState<LanguageCode[]>([
    'tamil',
    'english',
  ]);
  const [selectedArtists, setSelectedArtists] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const steps = [
    { icon: User, title: 'Your profile', subtitle: 'What should we call you?' },
    { icon: Globe, title: 'Language preferences', subtitle: 'Pick one or more music languages' },
    { icon: Music2, title: 'Favorite artists', subtitle: 'Tap to select (pick at least 1)' },
  ];

  const StepIcon = steps[step].icon;
  const artistOptions = artistsForLanguage(selectedLanguages);

  const toggleArtist = (name: string) => {
    setSelectedArtists((prev) =>
      prev.includes(name) ? prev.filter((a) => a !== name) : [...prev, name].slice(0, 5),
    );
  };

  const handleFinish = async () => {
    if (!displayName.trim() || selectedArtists.length === 0) {
      toast.error('Please enter your name and select at least one artist');
      return;
    }
    setSaving(true);
    try {
      await api.completeOnboarding({
        display_name: displayName.trim(),
        favorite_artists: selectedArtists,
        preferred_languages: selectedLanguages,
      });
      localStorage.setItem('noverep_display_name', displayName.trim());
      await usePlayerStore.getState().loadPreferences();
      await usePlayerStore.getState().fillQueue();
      toast.success(`Welcome, ${displayName}!`);
      onComplete();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Setup failed');
    } finally {
      setSaving(false);
    }
  };

  const canProceed =
    (step === 0 && displayName.trim().length >= 2) ||
    (step === 1 && selectedLanguages.length > 0) ||
    step === 2;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="glass w-full max-w-lg p-8 space-y-6 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-accent/20 flex items-center justify-center shrink-0">
            <StepIcon className="w-6 h-6 text-accent" />
          </div>
          <div>
            <h2 className="text-xl font-bold">{steps[step].title}</h2>
            <p className="text-sm text-white/50">{steps[step].subtitle}</p>
          </div>
        </div>

        <div className="flex gap-2">
          {steps.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full ${i <= step ? 'bg-accent' : 'bg-white/10'}`}
            />
          ))}
        </div>

        {step === 0 && (
          <input
            autoFocus
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Your display name"
            className="w-full glass px-4 py-3 text-lg focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
        )}

        {step === 1 && (
          <LanguageMultiSelect
            selected={selectedLanguages}
            onChange={(langs) => {
              setSelectedLanguages(langs);
              setSelectedArtists([]);
            }}
            compact
          />
        )}

        {step === 2 && (
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
            {artistOptions.map((artist) => {
              const selected = selectedArtists.includes(artist.name);
              return (
                <button
                  key={artist.id}
                  type="button"
                  onClick={() => toggleArtist(artist.name)}
                  className={`flex flex-col items-center gap-2 p-3 rounded-xl transition-all ${
                    selected ? 'ring-2 ring-accent bg-accent/10' : 'glass-hover'
                  }`}
                >
                  <div
                    className="w-14 h-14 rounded-full flex items-center justify-center text-sm font-bold relative"
                    style={{ backgroundColor: `${artist.color}33`, color: artist.color }}
                  >
                    {artistInitials(artist.name)}
                    {selected && (
                      <span className="absolute -top-1 -right-1 w-5 h-5 bg-accent rounded-full flex items-center justify-center">
                        <Check className="w-3 h-3" />
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-center leading-tight">{artist.name}</span>
                </button>
              );
            })}
          </div>
        )}

        <div className="flex justify-between pt-2">
          {step > 0 ? (
            <button type="button" className="btn-ghost" onClick={() => setStep(step - 1)}>
              Back
            </button>
          ) : (
            <div />
          )}
          {step < steps.length - 1 ? (
            <button
              type="button"
              className="btn-primary flex items-center gap-2"
              onClick={() => setStep(step + 1)}
              disabled={!canProceed}
            >
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary"
              onClick={handleFinish}
              disabled={saving || selectedArtists.length === 0}
            >
              {saving ? 'Saving...' : 'Start discovering'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
