export const DISCOVERY_YEAR_MIN = 1950;
export const DISCOVERY_YEAR_MAX = 2100;

export function yearToInput(value: number | null | undefined): string {
  if (value == null) return '';
  return String(value);
}

/** Parse and validate a single year text field. Empty = no limit. */
export function validateYearField(raw: string): { value: number | null; error: string | null } {
  const trimmed = raw.trim();
  if (!trimmed) return { value: null, error: null };
  if (!/^\d{4}$/.test(trimmed)) {
    return { value: null, error: 'Enter a 4-digit year (e.g. 2015)' };
  }
  const year = Number(trimmed);
  if (year < DISCOVERY_YEAR_MIN || year > DISCOVERY_YEAR_MAX) {
    return { value: null, error: `Year must be ${DISCOVERY_YEAR_MIN}–${DISCOVERY_YEAR_MAX}` };
  }
  return { value: year, error: null };
}

export function validateYearRange(
  from: number | null,
  to: number | null,
): string | null {
  if (from !== null && to !== null && from > to) {
    return '"From" year must be on or before "To" year';
  }
  return null;
}
