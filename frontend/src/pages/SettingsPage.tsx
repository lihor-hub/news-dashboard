import { useTranslation } from 'react-i18next';
import { ThemeSection } from '@/components/settings/ThemeSection';
import { LanguageSection } from '@/components/settings/LanguageSection';
import { PersonalizationSection } from '@/components/settings/PersonalizationSection';
import { WatchlistsSection } from '@/components/settings/WatchlistsSection';
import { AiMemorySection } from '@/components/settings/AiMemorySection';
import { AutomaticAiEnrichmentSection } from '@/components/settings/AutomaticAiEnrichmentSection';
import { McpTokensSection } from '@/components/settings/McpTokensSection';
import { GreaderTokensSection } from '@/components/settings/GreaderTokensSection';
import { DataExportSection } from '@/components/settings/DataExportSection';
import { DailyBriefSection } from '@/components/settings/DailyBriefSection';
import { WeeklyRecapSection } from '@/components/settings/WeeklyRecapSection';
import { PrivacySection } from '@/components/settings/PrivacySection';
import { UpdatesSection } from '@/components/settings/UpdatesSection';
import { DeleteAccountSection } from '@/components/settings/DeleteAccountSection';

export function SettingsPage() {
  const { t } = useTranslation();

  return (
    <div className="p-4 md:p-5 max-w-2xl space-y-6">
      <div>
        <h2 className="text-[22px] font-semibold tracking-tight">{t('settings.title')}</h2>
      </div>

      <ThemeSection />
      <LanguageSection />
      <PersonalizationSection />
      <WatchlistsSection />
      <AiMemorySection />
      <AutomaticAiEnrichmentSection />
      <McpTokensSection />
      <GreaderTokensSection />
      <DataExportSection />
      <DailyBriefSection />
      <WeeklyRecapSection />
      <PrivacySection />
      <UpdatesSection />
      <DeleteAccountSection />

      <section className="text-xs text-muted-foreground space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">
          {t('settings.about_heading')}
        </div>
        <p>{t('settings.about_body')}</p>
        <p>
          {t('settings.shortcuts_hint_prefix')}{' '}
          <kbd className="font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
            ?
          </kbd>{' '}
          {t('settings.shortcuts_hint_suffix')}
        </p>
      </section>
    </div>
  );
}
