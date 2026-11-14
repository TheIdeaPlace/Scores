"""Shared by every test. Qt draws offscreen here, before any test module makes a widget, so no
test opens a window on the PC it runs on, whichever file is run on its own. Some test modules set
this themselves; the ones that didn't opened real windows when run alone."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
