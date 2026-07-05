import { useTranslation } from 'react-i18next';
import { supportedLanguages } from '@/lib/languages';

export function LanguageSection() {
  const { t, i18n } = useTranslation();

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        {t('settings.language.heading')}
      </div>
      <p className="text-xs text-muted-foreground mb-2">{t('settings.language.description')}</p>
      <select
        value={i18n.resolvedLanguage ?? i18n.language}
        onChange={(e) => void i18n.changeLanguage(e.target.value)}
        aria-label={t('settings.language.heading')}
        className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm"
      >
        {supportedLanguages.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.nativeName}
          </option>
        ))}
      </select>
    </section>
  );
}
