/** Shape injected by the Electron preload via contextBridge. */
interface ElectronUpdateInfo {
  version: string;
  releaseDate?: string;
  releaseName?: string;
}

interface ElectronDownloadProgress {
  percent: number;
  transferred: number;
  total: number;
}

interface Window {
  electronAPI?: {
    readonly platform: 'electron';
    readonly appVersion: string;
    checkForUpdate(): void;
    downloadUpdate(): void;
    quitAndInstall(): void;
    onUpdateAvailable(cb: (info: ElectronUpdateInfo) => void): void;
    onUpdateNotAvailable(cb: (info: ElectronUpdateInfo) => void): void;
    onUpdateDownloaded(cb: (info: ElectronUpdateInfo) => void): void;
    onUpdateError(cb: (message: string) => void): void;
    onDownloadProgress(cb: (progress: ElectronDownloadProgress) => void): void;
    removeUpdateListeners(): void;
    /** Show a native OS notification (Electron only). */
    showNotification(title: string, body: string): void;
  };
}
