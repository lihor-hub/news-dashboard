import i18n from 'i18next';
import type { BackendModule } from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import { supportedLanguages } from '@/lib/languages';

// Default namespace
const DEFAULT_NS = 'translation';

// One dynamic-import loader per language, so Vite code-splits each
// translation.json into its own chunk instead of bundling all 29 upfront.
const localeLoaders = import.meta.glob<{ default: Record<string, unknown> }>(
  '../locales/*/translation.json'
);

function findLoader(language: string) {
  const suffix = `/locales/${language}/translation.json`;
  const entry = Object.entries(localeLoaders).find(([path]) => path.endsWith(suffix));
  return entry?.[1];
}

/** i18next backend that lazy-loads each language's bundle on first use. */
const lazyBackend: BackendModule = {
  type: 'backend',
  init: () => undefined,
  read: (language, _namespace, callback) => {
    const loader = findLoader(language);
    if (!loader) {
      callback(new Error(`No translation bundle for language: ${language}`), false);
      return;
    }
    loader()
      .then((mod) => callback(null, mod.default))
      .catch((err: Error) => callback(err, false));
  },
};

void i18n
  // Lazy-load translation bundles per language instead of bundling all of them.
  .use(lazyBackend)
  // Detect user language
  .use(LanguageDetector)
  // Pass the i18n instance to react-i18next.
  .use(initReactI18next)
  // Initialize i18next
  .init({
    fallbackLng: 'en',
    supportedLngs: supportedLanguages.map((l) => l.code),
    defaultNS: DEFAULT_NS,
    ns: [DEFAULT_NS],
    interpolation: {
      escapeValue: false, // React already escapes
    },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'i18nextLng',
      caches: ['localStorage'],
    },
  });

export default i18n;
export { DEFAULT_NS };
