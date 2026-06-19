# News Dashboard — Android TWA

This directory contains the configuration for building a native Android APK
that wraps the News Dashboard PWA (`https://news.lihor.ro`) using a
[Trusted Web Activity](https://developer.chrome.com/docs/android/trusted-web-activity/).

## What is a TWA?

A Trusted Web Activity renders a PWA full-screen inside Chrome on Android with
no address bar. It produces a real `.apk` that can be sideloaded or distributed
through an app store. Unlike Chrome's WebAPK install path (which has known bugs
around themed icons, update latency, and adaptive icon fidelity), a TWA APK is
fully under your control.

## How to build

The GitHub Actions workflow `.github/workflows/android.yml` builds and signs the
APK on every push to `android/` or on a manual `workflow_dispatch` trigger.

To trigger manually:

```
gh workflow run android.yml
```

The signed APK is uploaded as a workflow artifact. Download it with:

```
gh run download <run-id> --name news-dashboard-apk
```

## Project structure

| File | Purpose |
|---|---|
| `twa-manifest.json` | Bubblewrap config — source of truth for package ID, icons, colours, signing key ref |
| `app/` | Gradle Android application module (generated via `@bubblewrap/core`, committed) |
| `build.gradle` / `settings.gradle` | Root Gradle build files |
| `gradlew` | Gradle wrapper — CI uses this directly |
| `android.keystore` | **NOT in git** — signing keystore lives only in GitHub secrets |

The Gradle project under `android/` was generated once via `@bubblewrap/core`
and is committed to the repo. CI builds directly with `./gradlew assembleRelease`
— no Bubblewrap CLI is needed at build time.

## Signing key

**Whoever holds this keystore controls all future APK updates.** Android
enforces that every update of a package must be signed with the same key.

The keystore is stored as a base64-encoded GitHub Actions secret:
`ANDROID_KEYSTORE_BASE64`. It is _never_ committed to git (enforced by
`.gitignore`). The four required secrets are:

| Secret | Meaning |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | `base64 -i android.keystore` output |
| `ANDROID_KEYSTORE_PASSWORD` | keystore password |
| `ANDROID_KEY_ALIAS` | key alias inside the keystore (`android`) |
| `ANDROID_KEY_PASSWORD` | key entry password |

### Key rotation / disaster recovery

If the keystore is ever lost, new APK installs can use a new key, but **existing
installs cannot be updated**. Back up the keystore securely outside of git
(e.g. a password manager or encrypted off-site storage).

To rotate or regenerate (only safe for a fresh install — breaks OTA updates to
existing installs):

```bash
export PATH="$(brew --prefix openjdk@17)/bin:$PATH"

keytool -genkeypair \
  -alias android \
  -keyalg RSA -keysize 2048 -validity 9125 \
  -keystore android/android.keystore \
  -dname "CN=News Dashboard, OU=App, O=Lihor, L=Iasi, S=Iasi, C=RO"

# Get fingerprint for assetlinks.json
keytool -list -v -keystore android/android.keystore -alias android \
  | grep "SHA256:"

# Re-upload to GitHub
gh secret set ANDROID_KEYSTORE_BASE64 --body "$(base64 -i android/android.keystore)"
```

## Digital Asset Links

For the TWA to render without a URL bar, `news.lihor.ro` must serve
`/.well-known/assetlinks.json` containing the signing certificate fingerprint.

The file is at `public/.well-known/assetlinks.json` in the repo. If you
regenerate the keystore, update the `sha256_cert_fingerprints` field there.

Current fingerprint (matches the keystore in GitHub secrets):
```
C6:AC:CD:86:57:77:00:3D:26:6A:DD:23:C7:38:29:0C:49:C2:D6:E9:31:1C:44:E2:43:97:2A:81:9E:1A:35:EE
```

## Adaptive icon and themed icons

`twa-manifest.json` references `monochromeIconUrl`, which points to the
`icon-monochrome-512.png` already served by the PWA. Bubblewrap embeds this as
the `<monochrome>` layer of the Android adaptive icon in the generated APK.
This is why a TWA gets proper Material You themed icon support while Chrome's
WebAPK path does not.
