"""Choose the build number for the next iOS upload.

ios-release.yml used to take the build number straight from the commit count.
That grows on any one branch but not across a squash merge: a branch built to
TestFlight and then squashed leaves main at a count Apple has already seen, and
the upload is rejected as a duplicate (issue #112).

So the number is now the larger of:

- one more than the highest build number App Store Connect already has for the
  app, across every marketing version, and
- the commit count, so the number still tracks the history when nothing is
  ahead of it.

Apple only asks for a number higher than the last one in the same version
train, but floor-ing on the whole app is never wrong and needs no knowledge of
which train an older build belonged to.

If App Store Connect can't be asked (no key, network trouble, an API change),
the commit count is used and a GitHub Actions warning is printed, so the build
still runs; Apple will reject it at upload if the number really is taken.

Prints only the chosen number on stdout; everything else goes to stderr.

Usage:
  python next_build_number.py <commit count>

Environment:
  ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_P8   App Store Connect API key (PEM text)
  BUNDLE_ID                               e.g. com.sportsscores.app
"""

import os
import re
import sys
import time

API = "https://api.appstoreconnect.apple.com/v1"
PAGE_LIMIT = 200
MAX_PAGES = 50  # 10,000 builds; a guard against a pagination loop, not a real limit


def parse_build_number(version):
    """The whole-number part of a build string, or None if it has none.

    Builds are normally plain integers ("395"). Apple also allows dotted build
    strings ("395.1"); only the first part matters here, because the next
    number is always one more than it.
    """
    if version is None:
        return None
    match = re.match(r"\s*(\d+)(?:\.\d+)*\s*$", str(version))
    return int(match.group(1)) if match else None


def highest_build(versions):
    """The highest build number among build strings, or None if none parse."""
    numbers = [n for n in (parse_build_number(v) for v in versions) if n is not None]
    return max(numbers) if numbers else None


def build_versions(page):
    """The build strings in one page of GET /builds."""
    return [b.get("attributes", {}).get("version") for b in page.get("data", [])]


def choose_build_number(commit_count, highest_existing):
    """max(highest existing + 1, commit count); the commit count if nothing exists."""
    if highest_existing is None:
        return commit_count
    return max(highest_existing + 1, commit_count)


def warn(message):
    """A GitHub Actions warning. It carries one line, so whitespace is collapsed."""
    print(f"::warning::{' '.join(str(message).split())}", file=sys.stderr, flush=True)


def fetch_highest_build(bundle_id):
    """Ask App Store Connect for the app's highest build number. Raises on failure."""
    import jwt  # imported here so a missing package falls back like any other failure
    import requests

    def token():
        now = int(time.time())
        return jwt.encode(
            {"iss": os.environ["ASC_ISSUER_ID"], "iat": now, "exp": now + 1200,
             "aud": "appstoreconnect-v1"},
            os.environ["ASC_KEY_P8"], algorithm="ES256",
            headers={"kid": os.environ["ASC_KEY_ID"], "typ": "JWT"})

    def get(url, params=None):
        resp = requests.get(url, params=params, timeout=60,
                            headers={"Authorization": f"Bearer {token()}"})
        if resp.status_code >= 400:
            raise RuntimeError(f"GET {url} failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    apps = get(API + "/apps", {"filter[bundleId]": bundle_id}).get("data", [])
    apps = [a for a in apps if a.get("attributes", {}).get("bundleId") == bundle_id]
    if not apps:
        raise RuntimeError(f"no app with bundle id {bundle_id}")
    app_id = apps[0]["id"]

    # Every build of the app, expired and still-processing ones included: each
    # holds its number.
    versions = []
    page = get(API + "/builds", {"filter[app]": app_id, "fields[builds]": "version",
                                 "limit": PAGE_LIMIT})
    for _ in range(MAX_PAGES):
        versions += build_versions(page)
        next_url = page.get("links", {}).get("next")
        if not next_url:
            break
        page = get(next_url)
    else:
        raise RuntimeError(f"more than {MAX_PAGES} pages of builds")
    print(f"App Store Connect has {len(versions)} builds of {bundle_id}.", file=sys.stderr)
    return highest_build(versions)


def main(argv):
    if len(argv) != 2 or parse_build_number(argv[1]) is None or "." in argv[1]:
        sys.exit("usage: next_build_number.py <commit count>")
    commit_count = int(argv[1])
    try:
        highest = fetch_highest_build(os.environ["BUNDLE_ID"])
    except Exception as e:  # noqa: BLE001 - any failure falls back to the commit count
        warn(f"Couldn't ask App Store Connect for the highest build number ({e}); "
             f"using the commit count, {commit_count}. If Apple already has that "
             "number, rerun with a build_number override.")
        print(commit_count)
        return
    number = choose_build_number(commit_count, highest)
    shown = "none" if highest is None else highest
    print(f"Highest existing build: {shown}; commit count: {commit_count}; "
          f"using build {number}.", file=sys.stderr)
    print(number)


if __name__ == "__main__":
    main(sys.argv)
