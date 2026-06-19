'use strict';

const { app, BrowserWindow, Menu, shell } = require('electron');
const path = require('path');
const fs = require('fs');

const APP_URL = 'https://news.lihor.ro';
const isDev = !app.isPackaged;

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
      sandbox: true,
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
    ...(isDev
      ? [{ type: 'separator' }, { role: 'toggleDevTools' }]
      : []),
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
        ...(isMac
          ? [{ type: 'separator' }, { role: 'front' }]
          : [{ role: 'close' }]),
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  const win = createWindow();
  Menu.setApplicationMenu(buildMenu(win));

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      const w = createWindow();
      Menu.setApplicationMenu(buildMenu(w));
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
