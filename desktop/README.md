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
npm run build:mac    # produces a universal DMG and ZIP update payload in dist/
npm run build:linux  # produces dist/news-dashboard-{version}-x64.AppImage
npm run build:win    # produces dist/news-dashboard-{version}-x64.exe
```

## CI

`.github/workflows/release.yml` builds macOS, Linux, and Windows after a new
application release tag is created. A single publishing job waits for all three
builds, then creates `desktop-v{version}` with the installers, update manifests
(`latest-mac.yml`, `latest-linux.yml`, and `latest.yml`), and update payloads.
Missing required artifacts fail the build before publication.

`.github/workflows/desktop.yml` runs the same platform matrix on manual
`workflow_dispatch`. It uploads versioned workflow artifacts for seven days
and does not publish a GitHub Release. Both workflows inject the tag-derived
version and run desktop unit tests before packaging.

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
