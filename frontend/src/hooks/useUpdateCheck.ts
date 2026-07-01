import { useState, useCallback } from 'react';
import { compareVersions, tagToVersion } from '../lib/version';
import { detectPlatform, type AppPlatform } from '../lib/platform';

const GH_REPO = 'lihor-hub/news-dashboard';
const GH_RELEASES = `https://api.github.com/repos/${GH_REPO}/releases`;

/** Tag prefix per platform. */
const TAG_PREFIX: Record<AppPlatform, string> = {
  electron: 'desktop-v',
  twa: 'android-v',
  web: 'desktop-v',
};

export interface GithubRelease {
  tag_name: string;
  html_url: string;
  assets: { name: string; browser_download_url: string }[];
}

export interface UpdateInfo {
  currentVersion: string | null;
  latestVersion: string;
  updateAvailable: boolean;
  releaseUrl: string;
  /** Direct APK download URL — only populated for the twa platform. */
  apkUrl: string | null;
  platform: AppPlatform;
  /** Whether the currentVersion represents a known installed version (as opposed to TWA unknown). */
  installedVersionKnown: boolean;
}

/** Fetch all releases and return the latest one matching the prefix. */
async function fetchLatestRelease(prefix: string): Promise<GithubRelease | null> {
  const res = await fetch(`${GH_RELEASES}?per_page=30`);
  if (!res.ok) throw new Error(`GitHub API ${res.status}`);
  const releases: GithubRelease[] = (await res.json()) as GithubRelease[];
  return releases.find((r) => r.tag_name.startsWith(prefix)) ?? null;
}

/** Fetch the running version from the backend. */
async function fetchCurrentVersion(): Promise<string> {
  const res = await fetch('/api/version');
  if (!res.ok) throw new Error(`version API ${res.status}`);
  const data = (await res.json()) as { version: string };
  return data.version;
}

export type ElectronUpdateStage =
  'idle' | 'checking' | 'up-to-date' | 'available' | 'downloading' | 'ready' | 'error';

export function useUpdateCheck() {
  const platform = detectPlatform();
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Electron-specific state (driven by IPC events from main process).
  const [electronStage, setElectronStage] = useState<ElectronUpdateStage>('idle');
  const [downloadPercent, setDownloadPercent] = useState(0);
  const [electronLatestVersion, setElectronLatestVersion] = useState<string | null>(null);

  /** Check for updates (GitHub API + optionally /api/version). */
  const check = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const prefix = TAG_PREFIX[platform];
      const isTwa = platform === 'twa';

      // For TWA, skip /api/version: it returns the deployed server version,
      // not the installed APK version on the device.
      const release = await fetchLatestRelease(prefix);
      const serverVersion: string | null = isTwa ? null : await fetchCurrentVersion();

      if (!release) {
        setInfo({
          currentVersion: isTwa ? null : serverVersion,
          latestVersion: isTwa ? '0.0.0' : serverVersion!,
          updateAvailable: false,
          releaseUrl: `https://github.com/${GH_REPO}/releases`,
          apkUrl: null,
          platform,
          installedVersionKnown: !isTwa,
        });
        return;
      }

      const latestVersion = tagToVersion(release.tag_name);
      const apkAsset = release.assets.find((a) => a.name.endsWith('.apk')) ?? null;

      // For TWA, since we cannot determine the installed APK version, treat any
      // Android release with an APK asset as an available update.
      const updateAvailable = isTwa
        ? apkAsset !== null
        : compareVersions(latestVersion, serverVersion!) > 0;

      setInfo({
        currentVersion: isTwa ? null : serverVersion,
        latestVersion,
        updateAvailable,
        releaseUrl: release.html_url,
        apkUrl: apkAsset?.browser_download_url ?? null,
        platform,
        installedVersionKnown: !isTwa,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update check failed');
    } finally {
      setLoading(false);
    }
  }, [platform]);

  /**
   * Wire Electron IPC listeners and trigger autoUpdater.checkForUpdates().
   * Call once when the Settings page mounts on Electron.
   */
  const checkElectron = useCallback(() => {
    const api = window.electronAPI;
    if (!api) return;

    api.removeUpdateListeners();
    setElectronStage('checking');
    setError(null);

    api.onUpdateAvailable((updateInfo) => {
      setElectronStage('available');
      setElectronLatestVersion(updateInfo.version);
    });
    api.onUpdateNotAvailable(() => {
      setElectronStage('up-to-date');
    });
    api.onDownloadProgress((p) => {
      setElectronStage('downloading');
      setDownloadPercent(Math.round(p.percent));
    });
    api.onUpdateDownloaded(() => {
      setElectronStage('ready');
    });
    api.onUpdateError((msg) => {
      setElectronStage('error');
      setError(msg);
    });

    api.checkForUpdate();
  }, []);

  const downloadElectronUpdate = useCallback(() => {
    window.electronAPI?.downloadUpdate();
    setElectronStage('downloading');
  }, []);

  const installElectronUpdate = useCallback(() => {
    window.electronAPI?.quitAndInstall();
  }, []);

  return {
    platform,
    info,
    loading,
    error,
    check,
    // Electron-specific
    electronStage,
    downloadPercent,
    electronLatestVersion,
    checkElectron,
    downloadElectronUpdate,
    installElectronUpdate,
  };
}
