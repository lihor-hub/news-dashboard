import type { i18n as I18nInstance } from 'i18next';

export interface SupportedLanguage {
  code: string;
  /** The language's own name for itself, as shown in the language picker. */
  nativeName: string;
  rtl?: boolean;
}

export const supportedLanguages: SupportedLanguage[] = [
  { code: 'en', nativeName: 'English' },
  { code: 'es', nativeName: 'Español' },
  { code: 'fr', nativeName: 'Français' },
  { code: 'de', nativeName: 'Deutsch' },
  { code: 'pt', nativeName: 'Português' },
  { code: 'it', nativeName: 'Italiano' },
  { code: 'nl', nativeName: 'Nederlands' },
  { code: 'pl', nativeName: 'Polski' },
  { code: 'ru', nativeName: 'Русский' },
  { code: 'zh-CN', nativeName: '简体中文' },
  { code: 'zh-TW', nativeName: '繁體中文' },
  { code: 'ja', nativeName: '日本語' },
  { code: 'ko', nativeName: '한국어' },
  { code: 'ar', nativeName: 'العربية', rtl: true },
  { code: 'hi', nativeName: 'हिन्दी' },
  { code: 'tr', nativeName: 'Türkçe' },
  { code: 'vi', nativeName: 'Tiếng Việt' },
  { code: 'th', nativeName: 'ไทย' },
  { code: 'id', nativeName: 'Bahasa Indonesia' },
  { code: 'sv', nativeName: 'Svenska' },
  { code: 'no', nativeName: 'Norsk' },
  { code: 'da', nativeName: 'Dansk' },
  { code: 'fi', nativeName: 'Suomi' },
  { code: 'ro', nativeName: 'Română' },
  { code: 'uk', nativeName: 'Українська' },
  { code: 'cs', nativeName: 'Čeština' },
  { code: 'hu', nativeName: 'Magyar' },
  { code: 'el', nativeName: 'Ελληνικά' },
  { code: 'he', nativeName: 'עברית', rtl: true },
];

const rtlLanguageCodes = new Set(supportedLanguages.filter((l) => l.rtl).map((l) => l.code));

export function isRtlLanguage(code: string): boolean {
  return rtlLanguageCodes.has(code);
}

/** Sets `dir`/`lang` on the document root to match the active language. */
export function applyDocumentDirection(code: string): void {
  document.documentElement.dir = isRtlLanguage(code) ? 'rtl' : 'ltr';
  document.documentElement.lang = code;
}

/**
 * Run once before React renders (mirrors `initTheme`): applies the resolved
 * language's direction immediately, then keeps it in sync as the user switches
 * languages.
 */
export function initLanguageDirection(i18n: I18nInstance): void {
  applyDocumentDirection(i18n.resolvedLanguage ?? i18n.language);
  i18n.on('languageChanged', (lng) => applyDocumentDirection(lng));
}
