import { ThemeSection } from '@/components/settings/ThemeSection';
import { PersonalizationSection } from '@/components/settings/PersonalizationSection';
import { WatchlistsSection } from '@/components/settings/WatchlistsSection';
import { AiMemorySection } from '@/components/settings/AiMemorySection';
import { McpTokensSection } from '@/components/settings/McpTokensSection';
import { DataExportSection } from '@/components/settings/DataExportSection';
import { DailyBriefSection } from '@/components/settings/DailyBriefSection';
import { WeeklyRecapSection } from '@/components/settings/WeeklyRecapSection';
import { PrivacySection } from '@/components/settings/PrivacySection';
import { UpdatesSection } from '@/components/settings/UpdatesSection';
import { DeleteAccountSection } from '@/components/settings/DeleteAccountSection';

export function SettingsPage() {
  return (
    <div className="p-4 md:p-5 max-w-2xl space-y-6">
      <div>
        <h2 className="text-[22px] font-semibold tracking-tight">Settings</h2>
      </div>

      <ThemeSection />
      <PersonalizationSection />
      <WatchlistsSection />
      <AiMemorySection />
      <McpTokensSection />
      <DataExportSection />
      <DailyBriefSection />
      <WeeklyRecapSection />
      <PrivacySection />
      <UpdatesSection />
      <DeleteAccountSection />

      <section className="text-xs text-muted-foreground space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">About</div>
        <p>Radar is a private technical news triage tool. State is stored on the server.</p>
        <p>
          Press{' '}
          <kbd className="font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
            ?
          </kbd>{' '}
          anywhere for keyboard shortcuts.
        </p>
      </section>
    </div>
  );
}
