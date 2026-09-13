# Install the desktop app

News Dashboard's Electron desktop app opens **news.lihor.ro** in a native
window. It loads the live website and needs network access to the server;
it is not a standalone offline reader. The published app connects to the public
instance and does not offer a server-address setting.

## What you need

- A Mac with an Intel or Apple Silicon processor for the published universal build
- Network access to [news.lihor.ro](https://news.lihor.ro)
- A News Dashboard account; see [Create a web account](create-web-account.md)

Linux and Windows packaging targets are available for local builds, as described
below. The current published desktop release provides a macOS installer only.

## Where to get the build

1. Open the [GitHub Releases page](https://github.com/lihor-hub/news-dashboard/releases).
2. Find the newest **Desktop App** release, tagged `desktop-v{version}`.
   Android and server releases are separate.
3. Under **Assets**, download the universal `.dmg` installer.

For example, [Desktop App v1.171.0](https://github.com/lihor-hub/news-dashboard/releases/tag/desktop-v1.171.0)
provides `News.Dashboard-1.171.0-universal.dmg`. Its other asset,
`latest-mac.yml`, is update metadata, not an installer. That release has no
Linux AppImage or Windows installer.

## How to install

### macOS

1. Open the downloaded `.dmg` file.
2. Drag **News Dashboard.app** to **Applications**, then eject the disk image.
3. Open **News Dashboard** from Applications.

The macOS build is **unsigned**, so Gatekeeper may block its first launch.
After downloading it from the project's release page, Control-click the app
in Finder and choose **Open**, then confirm **Open** if offered. If macOS still
blocks it, open **System Settings → Privacy & Security** and use **Open Anyway**
for News Dashboard after attempting to launch it. See
[Apple’s instructions for opening an app from an unknown developer](https://support.apple.com/guide/mac-help/mh40616/mac).

If necessary, remove the downloaded app's quarantine attribute in Terminal:

```bash
xattr -dr com.apple.quarantine "/Applications/News Dashboard.app"
```

This command applies only to that installed app. Open it again afterward.

### Linux

There is currently no published Linux installer. Build the x64 AppImage using
the [desktop build instructions](https://github.com/lihor-hub/news-dashboard/blob/main/desktop/README.md).
Make the resulting `.AppImage` executable using its file properties or
`chmod +x`, then run it. The local build uses the name
`News Dashboard-<version>.AppImage` in `desktop/dist/`.

### Windows

There is currently no published Windows installer. Use the
[desktop build instructions](https://github.com/lihor-hub/news-dashboard/blob/main/desktop/README.md)
to produce the x64 NSIS installer, `News Dashboard Setup <version>.exe`, in
`desktop/dist/`. Open it and follow the installation wizard, choosing an
installation directory when prompted.

## Verifying the installation

Launch **News Dashboard**. It should open the public instance's sign-in page,
or your news dashboard if you already have a session. External article links
open in your system browser. In **Settings → Updates**, check **Current version**
to confirm which desktop build is installed.

## Updates

The window loads the live website, so web features update with the server.
The desktop wrapper has its own version: opening **Settings → Updates** checks
for a newer build automatically. If one is available, choose **Download update**,
then **Restart and install** when the download finishes.

If the updater fails, quit the app and install the newest desktop release over
the existing installation. On macOS, download its `.dmg` and replace the copy in
Applications. Local Linux and Windows builds can be updated by rebuilding and
installing the resulting package.

## Troubleshooting

| Problem | What to do |
|---------|------------|
| macOS blocks the app | Follow the unsigned-build steps above for the copy downloaded from the project release. |
| Blank window or site does not load | Check your network and open news.lihor.ro in a browser to confirm the server is reachable. |
| Update check or download fails | Choose **Try again** in Updates, or download and install the latest desktop release manually. |
| No installer for your operating system | Current published builds are macOS only; use the local build instructions for Linux or Windows. |
| You want to connect to a self-hosted server | Use that server in your browser. The published desktop app connects to news.lihor.ro. |

## Building the app yourself

See the [desktop development and build guide](https://github.com/lihor-hub/news-dashboard/blob/main/desktop/README.md)
for local commands and packaging configuration.
