"""JAWS stray-dialog-text harness. One exe, variants by command line:

  --buddy      the dialog's top label is the list's buddy
  --event N    after the dialog closes, NotifyWinEvent(N, main hwnd, OBJID_CLIENT, CHILDID_SELF)
  --event-window N   the same with OBJID_WINDOW
  --qtreorder  after the dialog closes, a Qt ObjectReorder accessibility event on the main window
  --noowner    the dialog's native window has no owner
  --delete     WA_DeleteOnClose on the dialog
  --nolabel    the dialog has no label at all (control)

Main window: a label, a list. Enter on "Open dialog" opens a modal dialog whose first text is
"HARNESS DIALOG LABEL". Escape on the main window changes its title (as a view swap does).
"""
import ctypes
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QDialog, QLabel, QListWidget, QMainWindow, QVBoxLayout,
                             QWidget)

ARGS = sys.argv[1:]


def arg_value(name):
    if name in ARGS:
        i = ARGS.index(name)
        return int(ARGS[i + 1], 0)
    return None


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Harness Main - " + (" ".join(ARGS) or "default"))
        central = QWidget()
        lay = QVBoxLayout(central)
        if "--mainstatic" in ARGS:
            lay.addWidget(QLabel("MAIN STATIC TEXT"))
        if "--blank" in ARGS:
            blank = QLabel("")
            blank.setAccessibleName(" ")
            lay.addWidget(blank)
        if "--zwsp" in ARGS:
            z = QLabel("")
            z.setAccessibleName("​")
            lay.addWidget(z)
        self.label = QLabel("Main list:")
        self.list = QListWidget()
        self.list.setAccessibleName("Main List")
        self.label.setBuddy(self.list)
        self.list.addItems(["Open dialog", "Item two", "Item three"])
        self.list.setCurrentRow(0)
        self.list.itemActivated.connect(self.open_dialog)
        lay.addWidget(self.label)
        lay.addWidget(self.list)
        self.setCentralWidget(central)
        self.flip = False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.flip = not self.flip
            self.setWindowTitle(("Harness Home - " if self.flip else "Harness Main - ") + (" ".join(ARGS) or "default"))
            return
        super().keyPressEvent(e)

    def open_dialog(self, item):
        if item.text() == "Item three":
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Harness Box", "HARNESS MESSAGE BOX TEXT")
            return
        if item.text() == "Item two":  # an empty dialog: no text at all
            d = QDialog(self)
            d.setWindowTitle("Empty Dialog")
            QVBoxLayout(d).addWidget(QListWidget())
            d.exec()
            return
        if item.text() != "Open dialog":
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Harness Dialog")
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        lst.setAccessibleName("Dialog List")
        lst.addItems(["Dialog item one", "Dialog item two"])
        lst.setCurrentRow(0)
        if "--nested" in ARGS:
            header = QWidget()
            hl = QVBoxLayout(header)
            hl.addWidget(QLabel("HARNESS DIALOG LABEL press Enter to open:"))
            lay.addWidget(header)
            lay.addWidget(lst)
        elif "--groupbox" in ARGS:
            from PyQt6.QtWidgets import QGroupBox
            box = QGroupBox("HARNESS DIALOG LABEL press Enter to open:")
            QVBoxLayout(box).addWidget(lst)
            lay.addWidget(box)
        elif "--labelafter" in ARGS:
            lay.addWidget(lst)
            lay.addWidget(QLabel("HARNESS DIALOG LABEL press Enter to open:"))
        elif "--delaylabel" in ARGS:
            from PyQt6.QtCore import QTimer
            lab = QLabel("")
            lay.addWidget(lab)
            lay.addWidget(lst)
            QTimer.singleShot(1500, lambda: lab.setText("HARNESS DIALOG LABEL press Enter to open:"))
        else:
            if "--nolabel" not in ARGS:
                lab = QLabel("HARNESS DIALOG LABEL press Enter to open:")
                if "--buddy" in ARGS:
                    lab.setBuddy(lst)
                lay.addWidget(lab)
            lay.addWidget(lst)
            if "--raise" in ARGS or "--dlgdesc" in ARGS:
                lab.raise_()
            if "--dlgdesc" in ARGS:
                dlg.setAccessibleDescription("HARNESS DIALOG LABEL press Enter to open:")
        if "--tool" in ARGS:
            dlg.setWindowFlag(Qt.WindowType.Tool, True)
        if "--delete" in ARGS:
            dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if "--noowner" in ARGS:
            dlg.winId()
            dlg.windowHandle().setTransientParent(None)
        if "--proxyowner" in ARGS:
            from PyQt6.QtGui import QWindow
            if not hasattr(self, "_proxy"):
                self._proxy = QWindow()
                self._proxy.create()
            dlg.winId()
            dlg.windowHandle().setTransientParent(self._proxy)
        if "--filter" in ARGS:
            pass  # the app-wide event filter below does it
        lst.setFocus()
        dlg.exec()
        hwnd = int(self.winId())
        ev = arg_value("--event")
        if ev is not None:
            ctypes.windll.user32.NotifyWinEvent(ev, hwnd, -4, 0)
        ev = arg_value("--event-window")
        if ev is not None:
            ctypes.windll.user32.NotifyWinEvent(ev, hwnd, 0, 0)

from PyQt6.QtCore import QEvent, QObject  # noqa: E402


def _has_focusable(w):
    if w.focusPolicy() != Qt.FocusPolicy.NoFocus:
        return True
    return any(_has_focusable(c) for c in w.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly))


def defer_static(w):
    """Put each child subtree with nothing focusable after the rest, in Qt's accessibility
    order (raise_ moves a widget to the end of its parent's children), recursing into
    containers that hold focusable widgets but aren't focusable themselves."""
    for c in list(w.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)):
        if c.isWindow():
            continue
        if not _has_focusable(c):
            c.raise_()
        elif c.focusPolicy() == Qt.FocusPolicy.NoFocus:
            defer_static(c)


class Deferrer(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QDialog) and obj.isWindow():
            if "--defer-msgbox" in ARGS or type(obj).__name__ != "QMessageBox":
                defer_static(obj)
        return False


class Unowner(QObject):
    """--filter: the app-wide way, clearing a dialog's transient parent in its show event,
    which Qt sends before the native window is shown."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QDialog) and obj.isWindow():
            handle = obj.windowHandle()
            if handle is not None and handle.transientParent() is not None:
                handle.setTransientParent(None)
        return False


app = QApplication(sys.argv)
if "--filter" in ARGS:
    _unowner = Unowner()
    app.installEventFilter(_unowner)
if "--defer" in ARGS or "--defer-msgbox" in ARGS:
    _deferrer = Deferrer()
    app.installEventFilter(_deferrer)
w = Main()
w.resize(500, 400)
w.show()
sys.exit(app.exec())
