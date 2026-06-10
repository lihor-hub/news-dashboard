import type { LucideIcon } from "lucide-react";

interface Props {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
}

export function EmptyState({ icon: Icon, title, subtitle }: Props) {
  return (
    <div className="flex flex-col items-center justify-center text-center px-6 py-20 text-muted-foreground">
      <Icon className="size-10 text-subtle mb-3" strokeWidth={1.25} />
      <div className="text-sm font-medium text-foreground">{title}</div>
      {subtitle && <div className="text-xs mt-1 max-w-xs">{subtitle}</div>}
    </div>
  );
}
