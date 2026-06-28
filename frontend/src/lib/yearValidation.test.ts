import { describe, expect, it } from 'vitest';
import { validateYearField, validateYearRange } from '@/lib/yearValidation';

describe('validateYearField', () => {
  it('accepts empty as no limit', () => {
    expect(validateYearField('')).toEqual({ value: null, error: null });
    expect(validateYearField('   ')).toEqual({ value: null, error: null });
  });

  it('accepts valid 4-digit years', () => {
    expect(validateYearField('2015')).toEqual({ value: 2015, error: null });
    expect(validateYearField('1950')).toEqual({ value: 1950, error: null });
  });

  it('rejects non-4-digit input', () => {
    expect(validateYearField('15').error).toBeTruthy();
    expect(validateYearField('20155').error).toBeTruthy();
    expect(validateYearField('abcd').error).toBeTruthy();
  });

  it('rejects out of range years', () => {
    expect(validateYearField('1949').error).toBeTruthy();
    expect(validateYearField('2101').error).toBeTruthy();
  });
});

describe('validateYearRange', () => {
  it('allows valid ranges', () => {
    expect(validateYearRange(2010, 2020)).toBeNull();
    expect(validateYearRange(null, 2020)).toBeNull();
    expect(validateYearRange(2010, null)).toBeNull();
  });

  it('rejects inverted range', () => {
    expect(validateYearRange(2020, 2010)).toBeTruthy();
  });
});
