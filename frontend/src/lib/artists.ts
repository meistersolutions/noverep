export interface ArtistOption {
  id: string;
  name: string;
  color: string;
  language: string;
}

export const TAMIL_ARTISTS: ArtistOption[] = [
  { id: 'ar-rahman', name: 'AR Rahman', color: '#8b5cf6', language: 'tamil' },
  { id: 'anirudh', name: 'Anirudh', color: '#ec4899', language: 'tamil' },
  { id: 'ilaiyaraaja', name: 'Ilaiyaraaja', color: '#f59e0b', language: 'tamil' },
  { id: 'sid-sriram', name: 'Sid Sriram', color: '#10b981', language: 'tamil' },
  { id: 'dhanush', name: 'Dhanush', color: '#3b82f6', language: 'tamil' },
  { id: 'hip-hop-tamizha', name: 'HHT', color: '#ef4444', language: 'tamil' },
  { id: 'yuvan', name: 'Yuvan', color: '#06b6d4', language: 'tamil' },
  { id: 'gv-prakash', name: 'GV Prakash', color: '#a855f7', language: 'tamil' },
];

export const ENGLISH_ARTISTS: ArtistOption[] = [
  { id: 'taylor-swift', name: 'Taylor Swift', color: '#f472b6', language: 'english' },
  { id: 'drake', name: 'Drake', color: '#fbbf24', language: 'english' },
  { id: 'weeknd', name: 'The Weeknd', color: '#ef4444', language: 'english' },
  { id: 'ed-sheeran', name: 'Ed Sheeran', color: '#3b82f6', language: 'english' },
  { id: 'billie', name: 'Billie Eilish', color: '#6b7280', language: 'english' },
  { id: 'coldplay', name: 'Coldplay', color: '#06b6d4', language: 'english' },
];

export const HINDI_ARTISTS: ArtistOption[] = [
  { id: 'arijit', name: 'Arijit Singh', color: '#f43f5e', language: 'hindi' },
  { id: 'pritam', name: 'Pritam', color: '#8b5cf6', language: 'hindi' },
  { id: 'shreya', name: 'Shreya Ghoshal', color: '#ec4899', language: 'hindi' },
  { id: 'atif', name: 'Atif Aslam', color: '#3b82f6', language: 'hindi' },
];

export const TELUGU_ARTISTS: ArtistOption[] = [
  { id: 'dsp', name: 'Devi Sri Prasad', color: '#f59e0b', language: 'telugu' },
  { id: 'thaman', name: 'Thaman S', color: '#10b981', language: 'telugu' },
  { id: 'mani', name: 'Mani Sharma', color: '#6366f1', language: 'telugu' },
];

export const MALAYALAM_ARTISTS: ArtistOption[] = [
  { id: 'gopi', name: 'Gopi Sundar', color: '#14b8a6', language: 'malayalam' },
  { id: 'shaan', name: 'Shaan Rahman', color: '#a855f7', language: 'malayalam' },
];

export const KANNADA_ARTISTS: ArtistOption[] = [
  { id: 'arjun', name: 'Arjun Janya', color: '#f97316', language: 'kannada' },
  { id: 'harikrishna', name: 'V Harikrishna', color: '#22c55e', language: 'kannada' },
];

export const PUNJABI_ARTISTS: ArtistOption[] = [
  { id: 'diljit', name: 'Diljit Dosanjh', color: '#eab308', language: 'punjabi' },
  { id: 'ap-dhillon', name: 'AP Dhillon', color: '#ef4444', language: 'punjabi' },
  { id: 'karan', name: 'Karan Aujla', color: '#3b82f6', language: 'punjabi' },
];

const BY_LANGUAGE: Record<string, ArtistOption[]> = {
  tamil: TAMIL_ARTISTS,
  english: ENGLISH_ARTISTS,
  hindi: HINDI_ARTISTS,
  telugu: TELUGU_ARTISTS,
  malayalam: MALAYALAM_ARTISTS,
  kannada: KANNADA_ARTISTS,
  punjabi: PUNJABI_ARTISTS,
};

export function artistsForLanguage(lang: string | string[]): ArtistOption[] {
  const langs = Array.isArray(lang) ? lang : [lang];
  if (langs.includes('all') || langs.includes('both') || langs.length >= 7) {
    return [
      ...TAMIL_ARTISTS.slice(0, 3),
      ...ENGLISH_ARTISTS.slice(0, 2),
      ...HINDI_ARTISTS.slice(0, 2),
      ...TELUGU_ARTISTS.slice(0, 2),
      ...PUNJABI_ARTISTS.slice(0, 1),
    ];
  }
  const seen = new Set<string>();
  const merged: ArtistOption[] = [];
  for (const code of langs) {
    for (const artist of BY_LANGUAGE[code] ?? []) {
      if (!seen.has(artist.id)) {
        seen.add(artist.id);
        merged.push(artist);
      }
    }
  }
  return merged.length > 0 ? merged : TAMIL_ARTISTS;
}

export function artistInitials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}
