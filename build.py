#!/usr/bin/env python3
"""Build the Windows distributables for Scores.

Produces two things from one source tree:

  dist/Scores/       one-dir build - the input to installer/scores.iss
  dist/Scores.exe    one-file build - the portable download

The installer deliberately packages the ONE-DIR build. A one-file build unpacks
itself to a _MEIxxxx temp directory at startup and deletes it on exit; when that
delete fails (antivirus still scanning, a handle still open) the bootloader
leaves a modal warning up and the process stays alive holding Scores.exe open,
which is exactly the state an in-app update cannot recover from - Setup cannot
replace a locked file. One-file also runs as a bootloader parent plus a child,
and only the child holds the ScoresRunning mutex, so the installer's running-app
check misses the parent that owns the lock. One-dir has neither problem and
starts faster.

The one-file exe is still built because that is what earlier releases shipped and
what the README points at; it updates itself by downloading Setup.exe like any
other copy.

Usage:
    python build.py              # both targets
    python build.py --onedir     # installer input only
    python build.py --onefile    # portable exe only
"""

import argparse
import os
import shutil
import subprocess
import sys

APP_NAME = "Scores"
ENTRY = "main.py"
DATAS = ["user_guide.html", "radio_links.json"]

# Separate work directories: the two builds share a name, so a shared build/
# cache lets one leg's analysis leak into the other's.
ONEDIR_WORK = os.path.join("build", "onedir")
ONEFILE_WORK = os.path.join("build", "onefile")


def _common_args(workpath):
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        f"--name={APP_NAME}",
        "--windowed",
        "--distpath=dist",
        f"--workpath={workpath}",
        f"--specpath={workpath}",
    ]
    for data in DATAS:
        # Absolute: --specpath moves the generated spec into the work directory,
        # and PyInstaller resolves relative data paths against the spec's folder.
        args += ["--add-data", f"{os.path.abspath(data)}{os.pathsep}."]
    return args


def build_onedir():
    print("=" * 60)
    print("Building one-dir build (installer input) -> dist/Scores/")
    print("=" * 60)
    target = os.path.join("dist", APP_NAME)
    if os.path.isdir(target):
        shutil.rmtree(target)
    subprocess.check_call(_common_args(ONEDIR_WORK) + ["--onedir", ENTRY])
    exe = os.path.join(target, f"{APP_NAME}.exe")
    if not os.path.exists(exe):
        raise SystemExit(f"Build produced no {exe}")
    size = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(target)
        for f in files
    )
    print(f"\n{target}  ({size / (1024 * 1024):.1f} MB)")


def build_onefile():
    print("=" * 60)
    print("Building one-file build (portable) -> dist/Scores.exe")
    print("=" * 60)
    exe = os.path.join("dist", f"{APP_NAME}.exe")
    if os.path.exists(exe):
        os.remove(exe)
    subprocess.check_call(_common_args(ONEFILE_WORK) + ["--onefile", ENTRY])
    if not os.path.exists(exe):
        raise SystemExit(f"Build produced no {exe}")
    print(f"\n{exe}  ({os.path.getsize(exe) / (1024 * 1024):.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--onedir", action="store_true",
                        help="build only the one-dir installer input")
    parser.add_argument("--onefile", action="store_true",
                        help="build only the portable one-file exe")
    args = parser.parse_args()

    both = not (args.onedir or args.onefile)
    if args.onedir or both:
        build_onedir()
    if args.onefile or both:
        build_onefile()

    print("\nDone. To build the installer over the one-dir output:")
    print('  "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe" '
          '/DMyAppVersion=x.y.z installer\\scores.iss')
    return 0


if __name__ == "__main__":
    sys.exit(main())
