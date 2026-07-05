import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import translationEn from '@/locales/en/translation.json';
import translationEs from '@/locales/es/translation.json';
import translationFr from '@/locales/fr/translation.json';
import translationDe from '@/locales/de/translation.json';
import translationPt from '@/locales/pt/translation.json';
import translationIt from '@/locales/it/translation.json';
import translationNl from '@/locales/nl/translation.json';
import translationPl from '@/locales/pl/translation.json';
import translationRu from '@/locales/ru/translation.json';
import translationZhCN from '@/locales/zh-CN/translation.json';
import translationZhTW from '@/locales/zh-TW/translation.json';
import translationJa from '@/locales/ja/translation.json';
import translationKo from '@/locales/ko/translation.json';
import translationAr from '@/locales/ar/translation.json';
import translationHi from '@/locales/hi/translation.json';
import translationTr from '@/locales/tr/translation.json';
import translationVi from '@/locales/vi/translation.json';
import translationTh from '@/locales/th/translation.json';
import translationId from '@/locales/id/translation.json';
import translationSv from '@/locales/sv/translation.json';
import translationNo from '@/locales/no/translation.json';
import translationDa from '@/locales/da/translation.json';
import translationFi from '@/locales/fi/translation.json';
import translationRo from '@/locales/ro/translation.json';
import translationUk from '@/locales/uk/translation.json';
import translationCs from '@/locales/cs/translation.json';
import translationHu from '@/locales/hu/translation.json';
import translationEl from '@/locales/el/translation.json';
import translationHe from '@/locales/he/translation.json';

import { supportedLanguages } from '@/lib/languages';

// Default namespace
const DEFAULT_NS = 'translation';

// Language resources
const resources = {
  en: { translation: translationEn },
  es: { translation: translationEs },
  fr: { translation: translationFr },
  de: { translation: translationDe },
  pt: { translation: translationPt },
  it: { translation: translationIt },
  nl: { translation: translationNl },
  pl: { translation: translationPl },
  ru: { translation: translationRu },
  'zh-CN': { translation: translationZhCN },
  'zh-TW': { translation: translationZhTW },
  ja: { translation: translationJa },
  ko: { translation: translationKo },
  ar: { translation: translationAr },
  hi: { translation: translationHi },
  tr: { translation: translationTr },
  vi: { translation: translationVi },
  th: { translation: translationTh },
  id: { translation: translationId },
  sv: { translation: translationSv },
  no: { translation: translationNo },
  da: { translation: translationDa },
  fi: { translation: translationFi },
  ro: { translation: translationRo },
  uk: { translation: translationUk },
  cs: { translation: translationCs },
  hu: { translation: translationHu },
  el: { translation: translationEl },
  he: { translation: translationHe },
};

void i18n
  // Detect user language
  .use(LanguageDetector)
  // Pass the i18n instance to react-i18next.
  .use(initReactI18next)
  // Initialize i18next
  .init({
    resources,
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
