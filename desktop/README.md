# News Dashboard — Desktop App

A thin Electron wrapper that opens `https://news.lihor.ro` in a native desktop
window. Like the Android TWA, this is not a bundled copy of the frontend — the
window always loads the live deployed site, so it stays up-to-date automatically.

## Features

- Native window with persistent size/position across launches
- Standard OS-native menus (File, Edit, View, Window) with keyboard shortcuts
- Reload (`⌘R`) and Force Reload (`⌘⇧R`)
- External links open in the system browser, not inside the app window
- Navigation is locked to `news.lihor.ro` — no accidental browsing
- Universal macOS binary (Intel + Apple Silicon)

## Download

Go to the [Releases page](https://github.com/ioachim-hub/news-dashboard/releases)
and download the latest `News Dashboard-*.dmg` (macOS) or `News Dashboard-*.AppImage`
(Linux).

## First launch on macOS (Gatekeeper)

The app is **unsigned** (no Apple Developer certificate). macOS will refuse to
open it directly. Two options:

**Option A — right-click → Open** (easiest):
1. In Finder, right-click `News Dashboard.app`
2. Click **Open**
3. Click **Open** again in the warning dialog

**Option B — strip quarantine attribute** (once, via Terminal):
```bash
xattr -cr "/Applications/News Dashboard.app"
```

After the first launch, the exception is saved and the app opens normally.

## Running locally (development)

```bash
cd desktop
npm install
npm start
```

The DevTools menu item (`View → Toggle Developer Tools`) is only available when
running via `npm start` (i.e., when the app is not packaged).

## Building locally

```bash
cd desktop
npm install
npm run build:mac    # produces dist/News Dashboard-1.0.0.dmg (universal)
npm run build:linux  # produces dist/News Dashboard-1.0.0.AppImage
npm run build:win    # produces dist/News Dashboard Setup 1.0.0.exe
```

## CI

The GitHub Actions workflow `.github/workflows/desktop.yml` builds the macOS DMG
on every push to `main` that touches `desktop/**` and on manual
`workflow_dispatch` triggers. Built installers are published as GitHub Release
assets tagged `desktop-v{version}-{run_number}`.

## Architecture

| File | Purpose |
|---|---|
| `src/main.js` | Electron main process: window creation, menu, navigation guards |
| `electron-builder.yml` | Build/packaging config (targets, signing, artifact names) |
| `assets/icon.icns` | macOS app icon (multi-resolution ICNS, generated from PWA icon-512.png) |
| `assets/icon.ico` | Windows app icon (multi-size ICO) |
| `assets/icon.png` | Linux app icon (512×512 PNG) |

Window state (size, position) is persisted to:
- macOS: `~/Library/Application Support/News Dashboard/window-state.json`
- Linux: `~/.config/News Dashboard/window-state.json`
- Windows: `%APPDATA%\News Dashboard\window-state.json`
