# Building Scores

How to run Scores from source, run its tests, and build the Windows distributables.
The installer, the in-app updater, code signing and the release checklist are in
[docs/INSTALLER.md](docs/INSTALLER.md).

## Set up

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements-minimal.txt` lists just what the app needs to run and build
(PyQt6, requests, pytz, PyInstaller), without the test tools.

## Run from source

```powershell
python scores.py
# Or straight to one screen:
python main.py --mlb
python main.py --live
```

`python main.py --help` lists every screen you can open directly. The built exe
starts from `main.py`.

## Run the tests

```powershell
pytest
```

A bare `pytest` run from the repo root collects `tests/` only (`testpaths` in
`pyproject.toml`). `TheBench/` is an archive of old scripts and isn't part
of the suite.

## Test coverage

Two checks, for two things:

- **The data layer's floor**, on every push (`scores.yml`): `coverage report`
  fails below `fail_under` in `pyproject.toml`, which covers a few pure modules.
- **The whole app, weekly** (#254): the **Coverage** workflow runs every Monday
  at 13:00 UTC, or by hand (Actions, Coverage, Run workflow). It runs the same
  tests on Windows as `scores.yml`, measures lines and branches of everything at
  the root plus `models` and `services` (the settings are in
  `tests/coverage/coveragerc`), and `tools/coverage_check.py` compares the result
  with `tests/coverage/baseline.json`. It flags:
  - the whole app falling more than 1 point;
  - a file of 50 statements or more falling more than 5 points;
  - any file, a new one included, with 25 or more statements more that no test
    runs.

  A drop files an issue labelled `coverage-regression`, or comments on the one
  already open. Each run's summary page shows the report, and its
  `coverage-report` download has the per-line HTML.

The baseline changes only when it's accepted, so a slow slide is still caught.
When a drop is expected (code moved, tests removed on purpose), or coverage rose
and the bar should rise with it, download `coverage.json` from a run's
`coverage-report` and accept it in a pull request:

```powershell
gh run download RUN_ID -n coverage-report -D cov
python tools/coverage_check.py cov\coverage.json --accept --measured "main at SHA, DATE, run RUN_ID"
```

To measure locally: `pip install pytest-cov`, then
`python -m pytest tests/unit --cov --cov-config=tests/coverage/coveragerc --cov-report=term-missing`.
The settings file is named on the command line because a `.coveragerc` at the
root would replace `pyproject.toml`'s settings, the floor's included.

## Build the exe

```powershell
python build.py
```

This is what CI runs, so it is the definition of a Scores build. It produces both
distributables:

- `dist\Scores\` - one-dir build; the input to the installer
- `dist\Scores.exe` - one-file portable build

Pass `--onedir` or `--onefile` to build just one of them. The data files the app
reads at run time (`user_guide.html`, `radio_links.json`) are listed in `DATAS` at
the top of `build.py`; add any new one there.

## Build the installer

```powershell
python build.py
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=0.8.0 installer\scores.iss
# -> installer\Output\Scores-0.8.0-Setup.exe
```

The installer packages the **one-dir** output, never the one-file exe; the comment
at the top of `build.py` says why.

## Build output

- `dist\Scores\` - installer input
- `dist\Scores.exe` - portable executable
- `installer\Output\Scores-<version>-Setup.exe` - installer
- `build\onedir\` and `build\onefile\` - PyInstaller work directories

Both builds are standalone: they carry the Python runtime, PyQt6 and everything
else the app needs, so they run on a Windows machine without Python. Releases are
code-signed by CI; local builds are not, so Windows SmartScreen will warn on them.

## Releasing

Bump `version.py` **and** `VERSION`, write `docs/release-notes-v<version>.md`,
update `CHANGELOG.md`, then push a `v<version>` tag. The workflow checks the tag
against `version.py` and `VERSION` and that the release notes exist, then builds,
signs, packages the installer and publishes the release.

A three-part version also moves the iOS `MARKETING_VERSION` (in
`iOS/SportsScoresApp/project.yml` and `project.pbxproj`), which
`tests/unit/test_version_sync.py` checks. A four-part version is a Windows-only
patch and leaves `MARKETING_VERSION` alone, since the App Store allows only three
parts. See
[docs/INSTALLER.md](docs/INSTALLER.md#cutting-a-release).
