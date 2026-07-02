# Install the Android APK

News Dashboard publishes a native Android APK that wraps the web app using a
[Trusted Web Activity (TWA)](https://developer.chrome.com/docs/android/trusted-web-activity/).
It renders the PWA full-screen with no address bar, supports adaptive icons
and Material You theming, and behaves like a real installed app.

The APK always loads **news.lihor.ro** (or the domain your self-hosted instance
is configured with). It is **not** a standalone reader — it requires network
access to the server.

## What you need

- An Android device running Android 6.0+ (API 23+)
- A network connection to reach the server
- Permission to install apps from outside the Play Store (see below)

## Where to get the APK

The signed APK is published as part of every
[GitHub Release](https://github.com/lihor-hub/news-dashboard/releases).

1. Open the [Releases page](https://github.com/lihor-hub/news-dashboard/releases).
2. Find the latest release (highest version number).
3. Under **Assets**, download the file named `news-dashboard-<version>.apk`.

> **Note**: The APK is not distributed through Google Play or any app store.
> You must download it from GitHub and install it manually.

## How to install

### 1. Allow installation from unknown sources

Android blocks apps installed outside the Play Store by default. You need to
enable **Install from unknown sources** (sometimes called **Install unknown
apps**) for the app you will use to open the APK file (usually your file
manager or browser).

Depending on your Android version:

- **Android 8+**: When you open the APK, Android will prompt you to allow
  installation from that source. Tap **Settings** and enable **Allow from
  this source**.
- **Android 6–7**: Go to **Settings → Security → Unknown sources** and
  enable the toggle.

### 2. Open the APK file

Transfer the downloaded `.apk` file to your device (if you downloaded it
directly from the device browser, it will be in the Downloads folder).

Open the file. Android will show a confirmation screen with the app name and
permissions.

Tap **Install**.

### 3. Launch the app

Once installed, tap **Open** to launch News Dashboard. You will see a sign-in
screen — see [Create a web account](create-web-account.md) if you do not have
one yet.

## Verifying the installation

The app icon should appear in your app drawer under the name **News Dashboard**.
Tapping it opens the sign-in page in a full-screen Chrome view with no address
bar.

## Updates

To update, download the latest APK from the
[Releases page](https://github.com/lihor-hub/news-dashboard/releases) and
install it over the existing app. Android will preserve your app data and
session.

## Troubleshooting

| Problem | Likely cause | Solution |
|---------|-------------|----------|
| "App not installed" | APK is corrupted or incompatible | Re-download the APK and check that your Android version is 6.0+ |
| "Parse error" | Incomplete download | Delete the file and download again |
| "Blocked by Play Protect" | Google's safety check | Tap **Install anyway** (the APK is signed and safe) |
| White screen / doesn't load | No network or wrong server URL | Check your connection and ensure news.lihor.ro is reachable |

## Building the APK yourself

Developers and self-hosters can build the APK from source. See the
[Android build guide](https://github.com/lihor-hub/news-dashboard/blob/main/android/README.md)
for instructions.
