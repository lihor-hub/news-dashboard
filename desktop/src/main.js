'use strict';

const { app, BrowserWindow, Menu, shell, ipcMain } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const fs = require('fs');

const APP_URL = 'https://news.lihor.ro';
const isDev = !app.isPackaged;

// ── Auto-updater configuration ────────────────────────────────────────────────
//
// electron-updater fetches latest-mac.yml / latest.yml from the GitHub Release
// assets to discover new versions, then downloads and installs the new build.
// autoDownload is disabled so the user controls when the download begins.

autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = true;

// In dev mode, skip auto-update entirely (no packaged binary to replace).
if (isDev) {
  autoUpdater.forceDevUpdateConfig = false;
}

// ── Window state persistence ──────────────────────────────────────────────────

const STATE_PATH = path.join(app.getPath('userData'), 'window-state.json');
const DEFAULT_STATE = { width: 1280, height: 860 };

function loadWindowState() {
  try {
    const raw = fs.readFileSync(STATE_PATH, 'utf8');
    const s = JSON.parse(raw);
    if (typeof s.width === 'number' && typeof s.height === 'number') return s;
  } catch {
    // first launch or corrupt state — use defaults
  }
  return { ...DEFAULT_STATE };
}

function saveWindowState(win) {
  if (win.isMaximized() || win.isMinimized() || win.isFullScreen()) return;
  try {
    fs.writeFileSync(STATE_PATH, JSON.stringify(win.getBounds()));
  } catch {
    // ignore write errors (e.g. read-only FS)
  }
}

// ── Window creation ───────────────────────────────────────────────────────────

function createWindow() {
  const state = loadWindowState();

  const win = new BrowserWindow({
    ...state,
    minWidth: 600,
    minHeight: 400,
    title: 'News Dashboard',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false, // must be false to allow preload to use require()
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  win.loadURL(APP_URL);

  // Open target=_blank and external links in the system browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(APP_URL)) return { action: 'allow' };
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Prevent in-window navigation away from the site.
  win.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(APP_URL)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  // Persist size/position on every move or resize (debounced).
  let saveTimer = null;
  const scheduleSave = () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveWindowState(win), 300);
  };
  win.on('resize', scheduleSave);
  win.on('move', scheduleSave);
  win.on('close', () => {
    clearTimeout(saveTimer);
    saveWindowState(win);
  });

  return win;
}

// ── Native notification IPC ───────────────────────────────────────────────────

ipcMain.on('notification:show', (_event, { title, body }) => {
  const { Notification } = require('electron');
  if (Notification.isSupported()) {
    new Notification({ title: String(title), body: String(body) }).show();
  }
});

// ── Auto-updater IPC bridge ───────────────────────────────────────────────────
//
// The renderer (web app at news.lihor.ro) calls window.electronAPI.*
// which the preload converts to these IPC messages.

function setupUpdater(win) {
  // Renderer → main: trigger actions.
  ipcMain.on('updater:check', () => {
    if (!isDev) autoUpdater.checkForUpdates().catch(() => {});
  });
  ipcMain.on('updater:download', () => {
    autoUpdater.downloadUpdate().catch(() => {});
  });
  ipcMain.on('updater:quit-and-install', () => {
    autoUpdater.quitAndInstall();
  });

  // Main → renderer: forward updater events.
  autoUpdater.on('update-available', (info) => {
    win.webContents.send('updater:available', info);
  });
  autoUpdater.on('update-not-available', (info) => {
    win.webContents.send('updater:not-available', info);
  });
  autoUpdater.on('update-downloaded', (info) => {
    win.webContents.send('updater:downloaded', info);
  });
  autoUpdater.on('download-progress', (progress) => {
    win.webContents.send('updater:progress', {
      percent: progress.percent,
      transferred: progress.transferred,
      total: progress.total,
    });
  });
  autoUpdater.on('error', (err) => {
    win.webContents.send('updater:error', err.message ?? String(err));
  });
}

// ── Application menu ──────────────────────────────────────────────────────────

function buildMenu(win) {
  const isMac = process.platform === 'darwin';

  const viewSubmenu = [
    {
      label: 'Reload',
      accelerator: 'CmdOrCtrl+R',
      click: (_, w) => (w || win).webContents.reload(),
    },
    {
      label: 'Force Reload',
      accelerator: 'CmdOrCtrl+Shift+R',
      click: (_, w) => (w || win).webContents.reloadIgnoringCache(),
    },
    ...(isDev ? [{ type: 'separator' }, { role: 'toggleDevTools' }] : []),
    { type: 'separator' },
    { role: 'resetZoom' },
    { role: 'zoomIn' },
    { role: 'zoomOut' },
    { type: 'separator' },
    { role: 'togglefullscreen' },
  ];

  const template = [
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' },
              { type: 'separator' },
              { role: 'services' },
              { type: 'separator' },
              { role: 'hide' },
              { role: 'hideOthers' },
              { role: 'unhide' },
              { type: 'separator' },
              { role: 'quit' },
            ],
          },
        ]
      : []),
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    { label: 'View', submenu: viewSubmenu },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        ...(isMac ? [{ type: 'separator' }, { role: 'front' }] : [{ role: 'close' }]),
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}

// ── App lifecycle ─────────────────────────────────────────────────────────────

// Synchronous reply for the preload's appVersion getter.
ipcMain.on('get-app-version', (event) => {
  event.returnValue = app.getVersion();
});

app.whenReady().then(() => {
  const win = createWindow();
  Menu.setApplicationMenu(buildMenu(win));
  setupUpdater(win);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      const w = createWindow();
      Menu.setApplicationMenu(buildMenu(w));
      setupUpdater(w);
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
