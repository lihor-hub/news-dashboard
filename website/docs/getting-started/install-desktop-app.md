# Install the desktop app

News Dashboard's Electron desktop app opens **news.lihor.ro** in a native
window. It loads the live website and needs network access to the server;
it is not a standalone offline reader. The published app connects to the public
instance and does not offer a server-address setting.

## What you need

- macOS on Intel or Apple Silicon, Linux x64, or Windows x64
- Network access to [news.lihor.ro](https://news.lihor.ro)
- A News Dashboard account; see [Create a web account](create-web-account.md)

New desktop releases include installers for all three operating systems. Older releases may contain only the macOS installer;
check the selected release’s assets.

## Where to get the build

1. Open the [GitHub Releases page](https://github.com/lihor-hub/news-dashboard/releases).
2. Find the newest **Desktop App** release, tagged `desktop-v{version}`.
   Android and server releases are separate.
3. Under **Assets**, download the installer for your operating system:

| Operating system | Installer |
|------------------|-----------|
| macOS (Intel and Apple Silicon) | `news-dashboard-<version>-universal.dmg` |
| Linux x64 | `news-dashboard-<version>-x64.AppImage` |
| Windows x64 | `news-dashboard-<version>-x64.exe` |

The accompanying ZIP, YAML manifests (`latest-mac.yml`, `latest-linux.yml`,
and `latest.yml`), and blockmaps support updates; they are not separate installers.

For an older example, [Desktop App v1.171.0](https://github.com/lihor-hub/news-dashboard/releases/tag/desktop-v1.171.0)
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

1. Download the `.AppImage` for Linux x64.
2. Make it executable in the file’s properties, or run `chmod +x` followed by
   the downloaded filename in a terminal.
3. Open the AppImage to launch News Dashboard.

### Windows

Download the x64 `.exe` installer, open it, and follow the installation wizard.
You can choose the installation directory when prompted. The installer is
unsigned, so Windows may display an unknown-publisher warning; confirm that
it came from the project’s GitHub release before continuing.

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
Applications. On Linux, replace the old AppImage with the new one and make it
executable. On Windows, run the new installer.

## Troubleshooting

| Problem | What to do |
|---------|------------|
| macOS blocks the app | Follow the unsigned-build steps above for the copy downloaded from the project release. |
| Blank window or site does not load | Check your network and open news.lihor.ro in a browser to confirm the server is reachable. |
| Update check or download fails | Choose **Try again** in Updates, or download and install the latest desktop release manually. |
| No installer for your operating system | Older releases may be macOS-only. Check a newer Desktop App release for Linux x64 or Windows x64 assets, or use the local build instructions. |
| You want to connect to a self-hosted server | Use that server in your browser. The published desktop app connects to news.lihor.ro. |

## Building the app yourself

See the [desktop development and build guide](https://github.com/lihor-hub/news-dashboard/blob/main/desktop/README.md)
for local commands and packaging configuration.
