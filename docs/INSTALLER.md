# Installer, automatic updates, and code signing

Scores ships three things per release:

| Asset | What it is |
| --- | --- |
| `Scores-<version>-Setup.exe` | Per-user installer (Inno Setup). The recommended download. |
| `Scores.exe` | Portable one-file build, kept for people who already use it. |

Both are Authenticode-signed with Azure Artifact Signing, and both can update
themselves in place.

This mirrors what WeatherFast does, which in turn follows QuickMail's model
(QuickMail uses Velopack because it is a .NET app; a PyInstaller app gets the
same behaviour from Inno Setup plus a small updater module).

## Installer

`installer/scores.iss` builds the installer over the **one-dir** PyInstaller
output in `dist/Scores/`.

- **Per-user, no elevation.** Installs to `%LocalAppData%\Programs\Scores` with
  `PrivilegesRequired=lowest`, which is what lets the in-app updater run a new
  installer without a UAC prompt.
- **Upgrades in place.** `AppId` is a fixed GUID — never change it, or an upgrade
  becomes a second parallel install.
- **Waits for a running copy.** `AppMutex=ScoresRunning` matches the mutex the app
  holds (`hold_app_mutex` in `services/updater.py`), so Setup can detect a running
  Scores and prompt instead of failing to overwrite a locked `Scores.exe`. A
  `PrepareToInstall` handler force-closes a leftover process as a backstop, which
  matters most when upgrading from a pre-installer one-file release.
- **Shortcuts.** Start Menu always; desktop shortcut is an unchecked option.

The installer deliberately does **not** package the one-file build — see the
comment at the top of `build.py` for the failure that causes (a one-file
bootloader can sit alive holding `Scores.exe` open, which no installer can
replace).

### Build it locally

```powershell
.venv\Scripts\activate
python build.py                 # dist\Scores\ (installer input) + dist\Scores.exe (portable)
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=0.8.0 installer\scores.iss
# -> installer\Output\Scores-0.8.0-Setup.exe
```

A local build is unsigned, so SmartScreen will warn on it. Only CI signs.

## Automatic updates

`services/updater.py` reads
`https://api.github.com/repos/TheIdeaPlace/Scores/releases`, ignores drafts and
prereleases, takes the highest `v<semver>` tag, and compares it to `version.py`.
When a release is newer it downloads that release's `*Setup.exe` asset to the temp
directory, launches it, and quits the app so Setup can replace the files.

- **Automatic check** runs about two seconds after launch, only in a frozen build,
  and only when the *Automatically check for updates at startup* setting is on
  (home page → Settings). It is silent unless an update exists, so a failed
  network call never interrupts launch.
- **Manual check** is the *Check for Updates* entry at the bottom of the home
  list. It reports every outcome, including "you're up to date" and "couldn't
  check".
- **Portable copies** update too; the installer relocates them to
  `%LocalAppData%\Programs\Scores`, and the prompt says so.
- If a release has no installer asset, the app offers to open the releases page
  instead of pretending it can update itself.

Version comparison is numeric per segment (`0.10.0` > `0.9.0`) and zero-pads, so
`0.8` and `0.8.0` are the same release. `tests/unit/test_updater.py` covers this.

## Code signing (Azure Artifact Signing)

`.github/workflows/scores.yml` signs on `v*` tags and manual runs. Authentication
is GitHub OIDC — no certificate or long-lived secret is stored in the repo.
`azure/login` exchanges the workflow's OIDC token for a short-lived Azure
credential, then `azure/artifact-signing-action` signs:

1. every `.exe` in `dist\Scores\` (so the copy inside the installer is signed),
2. the portable `dist\Scores.exe`,
3. the finished `installer\Output\Scores-*-Setup.exe`.

Signing identity, shared with QuickMail and WeatherFast:

| Setting | Value |
| --- | --- |
| Endpoint | `https://eus.codesigning.azure.net/` |
| Signing account | `kellylford` |
| Certificate profile | `kellyford-public` |
| Timestamp | `http://timestamp.acs.microsoft.com` |

### One-time setup for this repository

The signing account already exists; only the trust between this repo and Azure is
new. Three things are needed:

1. **A GitHub environment named `azure-signing`** (the job declares it so the OIDC
   token subject is predictable). Leave it unprotected — protection rules would
   make every build, including pull requests, wait for approval:

   ```bash
   gh api -X PUT repos/TheIdeaPlace/Scores/environments/azure-signing
   ```

2. **Repository secrets** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID` — the same values QuickMail and WeatherFast use:

   ```bash
   gh secret set AZURE_CLIENT_ID --repo TheIdeaPlace/Scores
   gh secret set AZURE_TENANT_ID --repo TheIdeaPlace/Scores
   gh secret set AZURE_SUBSCRIPTION_ID --repo TheIdeaPlace/Scores
   ```

3. **A federated credential on that Azure app registration** for this repo, with
   subject `repo:TheIdeaPlace/Scores:environment:azure-signing`
   (issuer `https://token.actions.githubusercontent.com`, audience
   `api://AzureADTokenExchange`). Add it in the Azure portal under the app
   registration's *Certificates & secrets → Federated credentials*, choosing
   GitHub Actions → Environment. The app registration also needs the *Trusted
   Signing Certificate Profile Signer* role on the `kellylford` signing account.

Until all three exist, tagged builds fail at the *Azure login* step. Pushes to
main and pull requests are unaffected — they never sign.

## Cutting a release

1. Bump the version in **`version.py`**, **`VERSION`**, and the iOS project's
   `MARKETING_VERSION` (in `iOS/SportsScoresApp/project.yml` and
   `SportsScores.xcodeproj/project.pbxproj`). Both release workflows refuse a tag
   that disagrees with `VERSION`, and `tests/unit/test_version_sync.py` fails if
   any of the four drift.
2. Write `docs/release-notes-v<version>.md` — it becomes the release body, and a
   missing file fails the build early.
3. Update `CHANGELOG.md`.
4. Commit, then tag and push:

   ```bash
   git tag -a v0.9.0 -m "Release v0.9.0" && git push origin main v0.9.0
   ```

The tag releases both apps. `scores.yml` tests, builds both Windows targets,
signs, packages the installer, signs it, and publishes the release with both
assets attached. `ios-release.yml` archives the iOS app at the same version and
uploads it to TestFlight, with a build number one past the highest Apple
already has, or the commit count if that is higher (see
`.github/workflows/README-ios-release.md`). The installer asset must stay
on every release: the in-app updater looks for a name ending in `Setup.exe`.

To rehearse without releasing, run the workflow manually
(*Actions → Scores → Run workflow*). A manual run signs and uploads the installer
as a build artifact but creates no release.
