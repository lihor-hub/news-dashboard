import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getReaderList, setReaderList } from '../lib/readerList';

describe('readerList sessionStorage helpers', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('returns null when nothing is stored', () => {
    expect(getReaderList()).toBeNull();
  });

  it('round-trips a list of ids', () => {
    setReaderList(['1', '2', '3']);
    expect(getReaderList()).toEqual({ ids: ['1', '2', '3'] });
  });

  it('returns null for corrupt JSON', () => {
    sessionStorage.setItem('reader_list', '{not json');
    expect(getReaderList()).toBeNull();
  });

  it('swallows write errors when sessionStorage throws', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    expect(() => setReaderList(['1'])).not.toThrow();
  });
});
