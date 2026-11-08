"""mac-build branch: check on macOS that Return opens a list row once mac_keys is installed,
and didn't before. Exits 1 if not. Run offscreen in the Mac build workflow."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QListWidget  # noqa: E402

import mac_keys  # noqa: E402

app = QApplication([])


def presses(installed):
    widget = QListWidget()
    widget.addItems(["first", "second"])
    widget.setCurrentRow(1)
    opened = []
    widget.itemActivated.connect(lambda item: opened.append(item.text()))
    widget.show()
    QTest.keyClick(widget, Qt.Key.Key_Return)
    return opened


before = presses(False)
keys = mac_keys.install(app)
after = presses(True)
print(f"before: {before}, after: {after}")
if sys.platform == "darwin" and after != ["second"]:
    print("Return did not open the row on macOS")
    sys.exit(1)
print("Return opens the current row")
