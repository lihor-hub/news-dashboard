import { describe, expect, it } from 'vitest';
import { supportedLanguages, isRtlLanguage } from '@/lib/languages';

const translationModules = import.meta.glob('../locales/*/translation.json', { eager: true });

function keySet(obj: Record<string, unknown>, prefix = ''): Set<string> {
  const keys = new Set<string>();
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const nested of keySet(v as Record<string, unknown>, path)) keys.add(nested);
    } else {
      keys.add(path);
    }
  }
  return keys;
}

describe('locale files', () => {
  it('ship a translation.json for every supported language', () => {
    for (const lang of supportedLanguages) {
      expect(translationModules[`../locales/${lang.code}/translation.json`]).toBeDefined();
    }
  });

  it('keep the same set of keys across every language, matching English', () => {
    const enModule = translationModules['../locales/en/translation.json'] as {
      default: Record<string, unknown>;
    };
    const englishKeys = keySet(enModule.default);

    for (const lang of supportedLanguages) {
      const mod = translationModules[`../locales/${lang.code}/translation.json`] as {
        default: Record<string, unknown>;
      };
      const keys = keySet(mod.default);
      expect(new Set(keys)).toEqual(englishKeys);
    }
  });

  it('flags only Arabic and Hebrew as right-to-left', () => {
    const rtl = supportedLanguages.filter((l) => isRtlLanguage(l.code)).map((l) => l.code);
    expect(rtl.sort()).toEqual(['ar', 'he']);
  });
});
