import { describe, it, expect } from 'vitest';
import { formatDuration } from './lib/api';

describe('formatDuration', () => {
  it('formats seconds correctly', () => {
    expect(formatDuration(125)).toBe('2:05');
    expect(formatDuration(null)).toBe('--:--');
  });
});
