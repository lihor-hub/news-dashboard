import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const REPO_ROOT = path.resolve(__dirname, '..');

export default defineConfig({
  testDir: '.',
  testMatch: 'capture-screenshots.spec.ts',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL: 'http://localhost:5173',
  },
  projects: [
    {
      name: 'chromium-desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    {
      // Resolves (and creates, if missing) the scratch Postgres database used
      // for demo-mode screenshot capture, then seeds the schema and starts the
      // backend. Runs only when Playwright starts this server, not at config
      // load time — so static analysis tools that import this file don't
      // shell out or require a reachable Postgres server.
      command:
        'export DATABASE_URL="$(python3 scripts/ensure_demo_database.py | tail -1)" && ' +
        'news-dashboard init && uvicorn news_dashboard.main:app --app-dir backend --port 8000',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
      timeout: 30_000,
      cwd: REPO_ROOT,
      env: {
        DEMO_MODE: '1',
        DATABASE_URL: process.env.DATABASE_URL ?? '',
        DEMO_DATABASE_URL: process.env.DEMO_DATABASE_URL ?? '',
        SESSION_SECRET: process.env.SESSION_SECRET ?? 'demo-screenshot-session-secret',
      },
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 30_000,
      cwd: REPO_ROOT,
    },
  ],
});
