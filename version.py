"""Single source of truth for the application version.

`scores.py` re-exports this as its `__version__`, the in-app updater compares it
against the newest GitHub release, and the release workflow refuses to build a
`v*` tag whose version does not match this string and the VERSION file. Keeping
it in its own module means the updater can read the version without importing
the whole PyQt6 UI.

One version covers both apps: a v<x.y.z> tag releases Windows and uploads the
iOS app to TestFlight at the same version. When releasing: bump here, in the
VERSION file and in the iOS project's MARKETING_VERSION, and add
docs/release-notes-v<x.y.z>.md. tests/unit/test_version_sync.py checks they agree.

A fourth part (0.9.9.1) marks a Windows-only patch release: the iOS project
keeps the three-part version it shipped at (App Store marketing versions allow
only three parts) and ios-release.yml skips the build for that tag. The next
release of both apps goes to the next three-part version.

What each part means, from 1.0.0 on:

    1.0.0 -> 1.0.1   bug fixes
    1.0.0 -> 1.1.0   smaller features
    1.0.0 -> 2.0.0   a big feature, or anything that changes how the app is used

Each part is its own counter, not a decimal, so they do not run out: 1.9.0 is
followed by 1.10.0, which is higher. Write a bug fix as 1.0.1, never as "1.01" —
a leading zero is dropped when the version is compared, so "1.01" and 1.1 are
the same number to the updater and to Apple, and the bug-fix line would collide
with the feature line. test_version_sync.py requires three or four parts for
the same reason.
"""

__version__ = "1.0.0"
