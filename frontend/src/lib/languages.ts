export type LanguageCode =
  | 'tamil'
  | 'english'
  | 'hindi'
  | 'telugu'
  | 'malayalam'
  | 'kannada'
  | 'punjabi';

export const SELECTABLE_LANGUAGES: {
  value: LanguageCode;
  label: string;
  desc: string;
}[] = [
  { value: 'tamil', label: 'Tamil', desc: 'Tamil film & indie music' },
  { value: 'english', label: 'English', desc: 'Global English hits' },
  { value: 'hindi', label: 'Hindi', desc: 'Bollywood & Hindi pop' },
  { value: 'telugu', label: 'Telugu', desc: 'Tollywood & Telugu hits' },
  { value: 'malayalam', label: 'Malayalam', desc: 'Mollywood & Malayalam songs' },
  { value: 'kannada', label: 'Kannada', desc: 'Sandalwood & Kannada music' },
  { value: 'punjabi', label: 'Punjabi', desc: 'Punjabi pop & bhangra' },
];

export function effectiveLanguages(
  preferred: string[] | null | undefined,
  legacy: string | null | undefined,
): LanguageCode[] {
  if (preferred && preferred.length > 0) {
    return preferred.filter((c): c is LanguageCode =>
      SELECTABLE_LANGUAGES.some((o) => o.value === c),
    );
  }
  if (!legacy || legacy === 'all' || legacy === 'both' || legacy === 'multi') {
    return SELECTABLE_LANGUAGES.map((o) => o.value);
  }
  const match = SELECTABLE_LANGUAGES.find((o) => o.value === legacy);
  return match ? [match.value] : SELECTABLE_LANGUAGES.map((o) => o.value);
}

export function languageLabels(
  preferred: string[] | null | undefined,
  legacy: string | null | undefined,
): string {
  const langs = effectiveLanguages(preferred, legacy);
  if (langs.length === SELECTABLE_LANGUAGES.length) return 'All languages';
  return langs
    .map((c) => SELECTABLE_LANGUAGES.find((o) => o.value === c)?.label ?? c)
    .join(', ');
}
