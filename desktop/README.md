# News Dashboard — Desktop App

A thin Electron wrapper that opens `https://news.lihor.ro` in a native desktop
window. Like the Android TWA, this is not a bundled copy of the frontend — the
window always loads the live deployed site, so it stays up-to-date automatically.

For downloads, installation, unsigned macOS first-launch steps, and updates,
see the [desktop installation guide](https://docs.lihor.ro/docs/getting-started/install-desktop-app).

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
npm run build:mac    # produces a universal .dmg in dist/
npm run build:linux  # produces an x64 .AppImage in dist/
npm run build:win    # produces an x64 NSIS .exe in dist/
```

## CI

The release workflow `.github/workflows/release.yml` builds the universal
macOS DMG and publishes it with update metadata as a GitHub Release tagged
`desktop-v{version}`. Linux and Windows targets are available for local builds;
the release workflow currently publishes macOS only.

`.github/workflows/desktop.yml` provides manual `workflow_dispatch` builds.
It uploads the DMG and update metadata as workflow artifacts without creating
a release.

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
