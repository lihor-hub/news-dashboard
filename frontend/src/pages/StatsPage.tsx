import LegacyApp from '../App';

// Stats are embedded inside the Scheduler tab until slice #83 migrates them.
export function StatsPage() {
  return <LegacyApp initialTab="scheduler" hideLegacyNav />;
}
