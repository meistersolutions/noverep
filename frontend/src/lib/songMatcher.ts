const TITLE_NOISE =
  /\b(official\s*(music\s*)?video|official\s*audio|lyrics?\s*video|lyric\s*video|full\s*video|hd\s*video|4k|8k|remaster(?:ed)?|audio\s*only|music\s*video|mv\b|ft\.?|feat\.?|featuring)\b/gi;

const PAREN_CONTENT = /\([^)]*\)|\[[^\]]*\]|\{[^}]*\}/g;

const STOP_WORDS = new Set([
  'the',
  'a',
  'an',
  'and',
  'or',
  'of',
  'from',
  'ft',
  'feat',
  'featuring',
  'vs',
  'song',
  'songs',
  'audio',
  'video',
  'official',
  'lyrics',
  'lyric',
]);

function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\w\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function stripTitleNoise(title: string): string {
  return title.replace(PAREN_CONTENT, ' ').replace(TITLE_NOISE, ' ');
}

function extractCoreTitle(title: string, artist = ''): string {
  const cleaned = stripTitleNoise(title);
  const parts = cleaned
    .split(/[|\-–—:•]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.length) return title.trim();

  const normArtist = normalizeText(artist);
  const meaningful = parts.filter((part) => {
    const normPart = normalizeText(part);
    if (normPart.length < 3) return false;
    if (
      normArtist &&
      (normPart === normArtist || normArtist.includes(normPart) || normPart.includes(normArtist))
    ) {
      return false;
    }
    return true;
  });

  const candidates = meaningful.length ? meaningful : parts;
  return candidates[0];
}

function tokenSet(text: string): Set<string> {
  return new Set(
    normalizeText(text)
      .split(' ')
      .filter((token) => token.length >= 2 && !STOP_WORDS.has(token)),
  );
}

function jaccard(left: Set<string>, right: Set<string>): number {
  if (!left.size || !right.size) return 0;
  let intersection = 0;
  for (const token of left) {
    if (right.has(token)) intersection += 1;
  }
  const union = left.size + right.size - intersection;
  return union ? intersection / union : 0;
}

function titleSimilarity(titleA: string, titleB: string, artistA = '', artistB = ''): number {
  const coreA = extractCoreTitle(titleA, artistA);
  const coreB = extractCoreTitle(titleB, artistB);
  const normA = normalizeText(coreA);
  const normB = normalizeText(coreB);
  if (!normA || !normB) return 0;
  if (normA === normB) return 1;
  if (normA.includes(normB) || normB.includes(normA)) return 0.92;
  return jaccard(tokenSet(coreA), tokenSet(coreB));
}

function artistSimilarity(artistA: string, artistB: string): number {
  const normA = normalizeText(artistA);
  const normB = normalizeText(artistB);
  if (!normA || !normB) return 0;
  if (normA === normB) return 1;
  if (normA.includes(normB) || normB.includes(normA)) return 0.9;
  return jaccard(tokenSet(artistA), tokenSet(artistB));
}

function durationCompatible(
  durationA: number | null | undefined,
  durationB: number | null | undefined,
): boolean {
  if (durationA == null || durationB == null) return true;
  const diff = Math.abs(durationA - durationB);
  const average = (durationA + durationB) / 2;
  return diff <= 25 || (average > 0 && diff / average <= 0.08);
}

export function isSameSong(
  titleA: string,
  artistA: string,
  durationA: number | null | undefined,
  titleB: string,
  artistB: string,
  durationB: number | null | undefined,
): boolean {
  if (!durationCompatible(durationA, durationB)) return false;
  const titleScore = titleSimilarity(titleA, titleB, artistA, artistB);
  const artistScore = artistSimilarity(artistA, artistB);
  if (titleScore >= 0.88) return true;
  if (titleScore >= 0.78 && artistScore >= 0.4) return true;
  const score = titleScore * 0.65 + artistScore * 0.35;
  return score >= 0.82;
}
