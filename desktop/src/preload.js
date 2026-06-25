'use strict';

const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe, narrow API to the renderer (https://news.lihor.ro).
// Only IPC channels explicitly listed here are accessible from the web page.
contextBridge.exposeInMainWorld('electronAPI', {
  platform: 'electron',

  // Read-only version string — resolved in main and sent synchronously.
  get appVersion() {
    return ipcRenderer.sendSync('get-app-version');
  },

  // ── Auto-updater controls ─────────────────────────────────────────────────

  checkForUpdate: () => ipcRenderer.send('updater:check'),
  downloadUpdate: () => ipcRenderer.send('updater:download'),
  quitAndInstall: () => ipcRenderer.send('updater:quit-and-install'),

  // ── Auto-updater event subscriptions ─────────────────────────────────────
  // Each registers a one-way listener; the caller receives typed payloads.

  onUpdateAvailable: (cb) =>
    ipcRenderer.on('updater:available', (_e, info) => cb(info)),

  onUpdateNotAvailable: (cb) =>
    ipcRenderer.on('updater:not-available', (_e, info) => cb(info)),

  onUpdateDownloaded: (cb) =>
    ipcRenderer.on('updater:downloaded', (_e, info) => cb(info)),

  onUpdateError: (cb) =>
    ipcRenderer.on('updater:error', (_e, message) => cb(message)),

  onDownloadProgress: (cb) =>
    ipcRenderer.on('updater:progress', (_e, progress) => cb(progress)),

  // ── Cleanup ───────────────────────────────────────────────────────────────
  // Call when the Settings component unmounts to avoid listener leaks.

  removeUpdateListeners: () => {
    ipcRenderer.removeAllListeners('updater:available');
    ipcRenderer.removeAllListeners('updater:not-available');
    ipcRenderer.removeAllListeners('updater:downloaded');
    ipcRenderer.removeAllListeners('updater:error');
    ipcRenderer.removeAllListeners('updater:progress');
  },

  // ── Native notifications ──────────────────────────────────────────────────

  showNotification: (title, body) => ipcRenderer.send('notification:show', { title, body }),
});
