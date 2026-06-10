import { createFileRoute } from "@tanstack/react-router";
import { useApp, type Theme } from "@/lib/store";
import { Sun, Moon, Monitor, Download, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings — Radar" }] }),
  component: SettingsPage,
});

// Bundle every source file as a raw string at build time
const SOURCE_FILES = import.meta.glob("/src/**/*", {
  query: "?raw",
  import: "default",
}) as Record<string, () => Promise<string>>;
const ROOT_FILES = import.meta.glob(
  [
    "/package.json",
    "/tsconfig.json",
    "/vite.config.ts",
    "/components.json",
    "/eslint.config.js",
    "/bunfig.toml",
    "/index.html",
  ],
  { query: "?raw", import: "default" },
) as Record<string, () => Promise<string>>;

async function downloadSource() {
  const JSZip = (await import("jszip")).default;
  const zip = new JSZip();
  const entries = { ...SOURCE_FILES, ...ROOT_FILES };
  await Promise.all(
    Object.entries(entries).map(async ([path, loader]) => {
      try {
        const content = await loader();
        zip.file(path.replace(/^\//, ""), content);
      } catch {
        /* skip unreadable files */
      }
    }),
  );
  const blob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `radar-source-${new Date().toISOString().slice(0, 10)}.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function SettingsPage() {
  const theme = useApp((s) => s.theme);
  const setTheme = useApp((s) => s.setTheme);

  const opts: { v: Theme; label: string; icon: any }[] = [
    { v: "light", label: "Light", icon: Sun },
    { v: "dark", label: "Dark", icon: Moon },
    { v: "system", label: "System", icon: Monitor },
  ];

  return (
    <div className="p-4 md:p-5 max-w-2xl space-y-6">
      <div>
        <h2 className="text-[22px] font-semibold tracking-tight">Settings</h2>
      </div>
      <section>
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">Theme</div>
        <div className="grid grid-cols-3 gap-2">
          {opts.map((o) => {
            const Icon = o.icon;
            const active = theme === o.v;
            return (
              <button
                key={o.v}
                onClick={() => setTheme(o.v)}
                className={cn(
                  "flex flex-col items-center gap-1.5 rounded-md border p-3 text-xs font-medium transition-colors",
                  active ? "border-foreground bg-surface-2" : "border-border bg-card hover:bg-surface",
                )}
              >
                <Icon className="size-5" />
                {o.label}
              </button>
            );
          })}
        </div>
      </section>

      <section>
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">Source code</div>
        <DownloadButton />
        <p className="text-xs text-muted-foreground mt-2">
          Bundles every file under <code className="font-mono text-[10px]">src/</code> plus root configs into a single <code className="font-mono text-[10px]">.zip</code>.
        </p>
      </section>

      <section className="text-xs text-muted-foreground space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">About</div>
        <p>Radar is a private technical news triage tool. State is stored locally in your browser.</p>
        <p>Press <kbd className="font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">?</kbd> anywhere for keyboard shortcuts.</p>
      </section>
    </div>
  );
}

function DownloadButton() {
  const [loading, setLoading] = useState(false);
  return (
    <button
      onClick={async () => {
        setLoading(true);
        try {
          await downloadSource();
        } finally {
          setLoading(false);
        }
      }}
      disabled={loading}
      className="inline-flex items-center gap-2 rounded-md border border-border bg-card hover:bg-surface px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50"
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
      {loading ? "Packaging…" : "Download source as .zip"}
    </button>
  );
}
