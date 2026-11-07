# iOS TestFlight / App Store Release via GitHub Actions

The [`ios-release.yml`](ios-release.yml) workflow builds and uploads a Sports Scores
build to App Store Connect (TestFlight) from a GitHub-hosted macOS runner.

**Why this exists:** archiving on a Mac that's on a **beta macOS** (or a beta
Xcode/SDK) stamps the binary as "compiled with a beta product," and Apple rejects
those for the public App Store. GitHub's runners are always on released macOS +
released Xcode, so builds from here pass review. The workflow also aborts if the
runner ever comes up on a beta macOS seed, so a bad binary can never ship.

The app talks only to public ESPN / MLB APIs, so **no app-side API-key secrets are
required** — just the Apple signing/upload credentials below.

## One-time setup: repo secrets

Add these under **Settings → Secrets and variables → Actions → New repository secret**
on the **Scores** repo. (Secrets are per-repository, so even though these are the
same Apple credentials used by FastWeather, they must be added here too.)

| Secret | What it is | How to get it |
|--------|-----------|---------------|
| `ASC_KEY_ID` | App Store Connect API key ID | e.g. `38ANZ53D9L` — the key you already use for TestFlight uploads |
| `ASC_ISSUER_ID` | ASC API issuer ID | The issuer UUID from App Store Connect → Users and Access → Integrations → App Store Connect API |
| `ASC_KEY_P8_BASE64` | The `.p8` API key, base64-encoded | `base64 -i ~/Downloads/AuthKey_38ANZ53D9L.p8 \| pbcopy` |
| `DIST_CERT_P12_BASE64` | "Apple Distribution" cert **+ its private key**, base64-encoded | Export a `.p12` (below), then `base64 -i dist.p12 \| pbcopy` |
| `DIST_CERT_PASSWORD` | The password you set on that `.p12` | Whatever you typed during export |

### Exporting the distribution `.p12`

Easiest via **Keychain Access** (the private key can't be reliably exported from the CLI):

1. Open **Keychain Access** → **login** keychain → **My Certificates**.
2. Find **"Apple Distribution: Kelly Ford (P887QF74N8)"**. Expand it — it must have a
   private key underneath (the disclosure triangle). If it doesn't, that Mac can't
   export a usable cert; create a new distribution cert in Xcode first.
3. Right-click it → **Export "Apple Distribution…"** → **Personal Information Exchange (.p12)**.
4. Save as `dist.p12`, set a password → that password is `DIST_CERT_PASSWORD`.
5. `base64 -i dist.p12 | pbcopy` → paste as `DIST_CERT_P12_BASE64`.

Then delete `dist.p12` when you're done.

## Where this runs

Both the workflow and the iOS app live on `main`, so the **Run workflow** button
appears in the Actions UI and dispatching it against `main` builds the current iOS
code. (This used to require a dance between `main` and a separate `iOS` branch —
that branch is gone, archived at the `ios-branch-archive` tag.) From the CLI:

```bash
gh workflow run ios-release.yml --ref main
```

## Running it

**Normally you don't.** Since 0.9.8 the Windows and iOS apps share one version.
Pushing a `v<x.y.z>` tag runs this workflow alongside the Windows release, so the
same tag that publishes `Scores.exe` uploads the iOS build. The marketing version
comes from the `VERSION` file, and the run fails if the tag doesn't match it.
The build number is one more than the highest build App Store Connect already
has for the app (across every marketing version), or the commit count
(`git rev-list --count HEAD`) if that is higher. The commit count alone isn't
enough: after a branch built to TestFlight is squash-merged, `main` can land on
a count Apple has already seen, and the upload is rejected as a duplicate
(issue #112). `iOS/SportsScoresApp/scripts/next_build_number.py` does the
lookup. If App Store Connect can't be asked, the run prints a warning and uses
the commit count rather than failing. Uploads run one at a time, but Apple can
take a few minutes to list a new upload, so a run started right after another
upload may still pick a taken number; rerun it with a **Build number** override.

**Windows-only patch releases** use a four-part version (`v0.9.9.1`). This
workflow still runs for that tag, but its `platforms` job skips every iOS step,
and the run shows green with only `platforms` run. App Store marketing versions
allow three parts, so the iOS project stays on the version it shipped at, and a
manual run while `VERSION` is four-part uses its first three parts. A manual run
started from a four-part tag skips too; start it from `main`.

To upload without a release:

1. **Actions** tab → **iOS TestFlight / App Store Release** → **Run workflow**.
2. Set the branch to **`main`**.
3. **Build number**: leave blank to have it chosen as above. A value here always
   wins; it has to be higher than the last build of that version, or Apple
   rejects the upload.
4. **Marketing version**: leave blank to use `VERSION` (its first three parts).
5. Run. On success the build appears in App Store Connect / TestFlight (Processing for
   ~5–15 min), after which you can add it to a TestFlight group or submit it for App
   Store review. The `.ipa` is also saved as a run artifact.

## External testers

On a release tag, a second job (`external-testflight`) sends the build to external
TestFlight testers through the App Store Connect API
(`iOS/SportsScoresApp/scripts/testflight_external.py`). It:

1. Waits for Apple to finish processing the upload, which usually takes 10–30 minutes.
2. Sets **What to Test** from the iPhone sections of `docs/release-notes-v<version>.md`.
3. Adds the build to every external group, or only those named in `EXTERNAL_GROUPS`.
4. Submits the build for Beta App Review.

Apple reviews the first build of each version, typically within a day; testers
get it once it's approved. A manual run does this only when **external** is ticked.
The API key needs the App Manager or Admin role to manage TestFlight groups.

## Notes

- **Signing is automatic:** the ASC API key lets `xcodebuild` create/download the App
  Store provisioning profile; the imported `.p12` provides the distribution identity.
- **App Store submission stays manual.** Release tags send the build to TestFlight
  testers (see *External testers*), but submitting a version for App Store review is
  done in App Store Connect.
- The workflow sets the build and marketing numbers for that run only; it does
  **not** commit them back. `MARKETING_VERSION` in `iOS/SportsScoresApp/project.yml`
  and `project.pbxproj` is kept equal to `VERSION` (its first three parts) by hand at release time, and
  `tests/unit/test_version_sync.py` fails if it drifts. `CURRENT_PROJECT_VERSION` in
  the repo is only used for local Xcode builds.
- **App:** "Sports Scores Fast", bundle id `com.sportsscores.app`, team `P887QF74N8`.
- **Cost:** free for public repos; a private repo bills macOS runner minutes at 10×
  (a build is a few minutes, so cents per run).
