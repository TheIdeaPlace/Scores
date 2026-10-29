# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Scores** is a PyQt6 desktop application for Windows that displays live sports scores, standings, play-by-play, stats, and news. It is built with an accessibility-first philosophy — screen reader support, keyboard-only navigation, and multiple view modes are core features, not afterthoughts.

Current version: see `VERSION` file. Distributed as a standalone `Scores.exe` (~40MB) via GitHub releases.

A companion **iOS app** (SwiftUI, VoiceOver-first) lives in `iOS/SportsScoresApp/`. It shares no code with the Windows app — only the ESPN endpoints and the accessibility conventions — so the two evolve in parallel and features are ported by hand in both directions. See `### iOS App` below.

## Commands

**Run from source:**
```powershell
.venv\Scripts\activate
python scores.py
# Or straight to one screen (--<sport>, --<sport>-teams, --<sport>-standings, --live):
python main.py --mlb
```

**Build distributables:**
```powershell
python build.py
# Output: dist\Scores\ (one-dir, installer input) and dist\Scores.exe (portable)
```

**Build installer:**
```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=0.8.0 installer\scores.iss
# Output: installer\Output\Scores-0.8.0-Setup.exe
```

**Setup dev environment:**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Run tests:**
```powershell
pytest tests/
```

## Architecture

### Entry Points

- `main.py` — CLI argument parser; passes sport selection into the main window
- `scores.py` — The entire UI (9,700+ lines): `QApplication`, main window, all dialogs, all views, refresh logic, keyboard handling
- `version.py` — The version string, single source of truth. The app, the in-app updater and the release workflows all read it; bump it together with the `VERSION` file and the iOS `MARKETING_VERSION`.

### Data Layer

- `espn_api.py` (4,100+ lines) — All network calls. Fetches from ESPN's undocumented API (`site.api.espn.com/apis/site/v2/sports`), the official MLB Stats API (`statsapi.mlb.com`), and ESPN's fantasy feed (`lm-api-reads.fantasy.espn.com`, the only source for draft ranks/ADP/auction values). Contains per-sport logic for scores, standings, play-by-play, box scores, injuries, news, advanced stats, and the fantasy football cheatsheet.
- `services/api_service.py` — Thin wrapper around `espn_api.py` with unified error handling
- `services/venue_service.py` — Stadium/venue info
- `services/football_calendar.py` — NFL week/season calendar utilities
- `services/updater.py` — In-app update check against the GitHub release feed; downloads and launches the installer
- `models/` — `GameData`, `NewsData`, `StandingsData` dataclasses

### UI Components

- `accessible_table.py` (1,000+ lines) — Custom `QTableWidget` subclass powering every data table. Implements three view modes: **Table** (grid), **Quick List** (comma-separated), **Full List** (key: value pairs). Concrete subclasses: `StandingsTable`, `BoxscoreTable`, `InjuryTable`, `LeadersTable`.
- `pitch_exploration_dialog.py` — Interactive dialog for exploring MLB pitch coordinates with audio feedback
- `windows_notifications.py` — Windows UIA screen reader notifications

### Audio System

- `play_geometry.py` — Pure mapping from ESPN play coordinates to a note, a stereo balance and a spoken location, for basketball (NBA/WNBA/NCAAM/NCAAWB) and hockey (NHL/NCAAH/NCAAWH). No PyQt or winsound import, so it is unit-tested on any platform. **Its iOS twin is `Services/PlayAudioGeometry.swift`; the two are kept byte-identical in output and there is a grid diff in the test notes to prove it.** Football and soccer plays carry no coordinates, so they have no audio.
- `play_audio_mapper.py` — `PlayAudioMapper`, the playback layer for the above. Alt+P plays one play, Alt+S the whole period. **Nothing is spoken while a tone plays, on either platform.** The location is part of the play's own accessible text (`AccessibleTextRole` on Windows, the row's accessibility label on iOS) and the located count is part of the period header's, so it is heard on arrival; an announcement at playback time would repeat it and talk over the audio. The only thing said at playback time is that there is nothing to play.
- `simple_audio_mapper.py` — Maps pitch (x, y) coordinates to audio frequencies via `winsound` (MLB)
- `stereo_audio_mapper.py` — Stereo variant with left/right channel positioning for pitch location

### Utilities

- `text_utils.py` — ESPN text cleaning (strips HTML/placeholders from news content)
- `timezone_utils.py` — Converts ESPN UTC times to local timezone
- `exceptions.py` — `ApiError`, `DataModelError`

### Packaging and Release

- `build.py` — Builds both distributables. The installer packages the **one-dir** build, never the one-file exe; the reason is documented at the top of the file.
- `installer/scores.iss` — Inno Setup script. Per-user install into `%LocalAppData%\Programs\Scores`, no elevation, so the in-app updater can install without a UAC prompt.
- `.github/workflows/scores.yml` — Tests, builds, signs (Azure Artifact Signing over GitHub OIDC), packages the installer and publishes the release on a `v*` tag.
- `docs/INSTALLER.md` — How the installer, updater and signing fit together, plus the release checklist.

### iOS App

Lives entirely in `iOS/SportsScoresApp/` (Xcode project, SwiftUI). Nothing in the Python app reads from it and nothing in it reads from the Python app — `pytest` and `build.py` ignore the directory completely.

- `SportsScores/Services/ESPNAPIService.swift` — the iOS equivalent of `espn_api.py`. When you fix an ESPN data quirk on one platform, check whether the other needs the same fix; this has been the main source of drift.
- `.github/workflows/ios-build-check.yml` — simulator-only compile, runs on `main` for changes under `iOS/**`. No signing, no secrets.
- `.github/workflows/ios-release.yml` — runs on the same `v*` tags as the Windows release (and by manual dispatch); archives on a macOS runner and uploads to TestFlight. Needs the five App Store Connect secrets listed in `.github/workflows/README-ios-release.md`.

Both apps share one version: `VERSION` drives the Windows build and the iOS marketing version, and one `v*` tag releases both. The iOS build number is the commit count. Keep `MARKETING_VERSION` in `iOS/SportsScoresApp/project.yml` and `project.pbxproj` equal to `VERSION`; `tests/unit/test_version_sync.py` enforces it.

A four-part version (e.g. `0.9.9.1`) is a Windows-only patch release: the iOS project keeps the three-part version it shipped at (App Store marketing versions allow only three parts), and `ios-release.yml` skips the build for that tag. The next release of both apps moves to the next three-part version.

The iOS app previously lived on a separate `iOS` branch that also carried a stale copy of the Windows app. That branch is retired; its history is preserved at the `ios-branch-archive` tag.

## Key Patterns

**Sports supported:** MLB, NFL, NBA, NHL, WNBA, NCAAF, NCAAM, NCAAWB, NCAAH, NCAAWH, Soccer. ESPN sport/league slugs are used as identifiers throughout (e.g., `"baseball/mlb"`, `"football/nfl"`).

**Accessibility view modes:** `accessible_table.py` controls three view modes toggled via Alt+V / Alt+T / Alt+Q / Alt+F. When modifying any table/standings/stats display, verify all three modes render correctly.

**Window titles** are set dynamically throughout `scores.py` to give screen readers hierarchical context (e.g., `"Yankees vs Red Sox - MLB - Sports Scores"`). Maintain this pattern when adding new views or dialogs.

**Play-by-play parsing** is sport-specific and lives entirely in `espn_api.py`. MLB play-by-play uses ESPN's `summaryType` field (`S`=scoring, `I`=inning marker, `N`=substitution) and has several workarounds for ESPN data quirks documented in recent commits.

**No test framework for UI** — UI correctness is verified manually. `tests/` covers data parsing and utility functions.

## Reference

- `TheBench/ESPN_API_GUIDE.md` — Comprehensive documentation of the ESPN API endpoints used
- `TheBench/TECHNICAL_GUIDE.md` — Architecture reference with more detail
- `CHANGELOG.md` — Version history
