"""Small shared safeguards for Qeoloog form controls."""

from qgis.PyQt.QtCore import QEvent, QObject
from qgis.PyQt.QtWidgets import QAbstractScrollArea, QComboBox


class ClosedComboWheelGuard(QObject):
    """Prevent a closed combo box changing while its page is scrolled."""

    def eventFilter(self, watched, event):
        if (
            event.type() != QEvent.Type.Wheel
            or not isinstance(watched, QComboBox)
        ):
            return False
        view = watched.view()
        if view is not None and view.isVisible():
            return False

        parent = watched.parentWidget()
        while parent is not None and not isinstance(
            parent, QAbstractScrollArea
        ):
            parent = parent.parentWidget()
        if parent is not None:
            bar = parent.verticalScrollBar()
            pixel_delta = event.pixelDelta().y()
            if pixel_delta:
                bar.setValue(bar.value() - pixel_delta)
            else:
                steps = event.angleDelta().y() / 120.0
                if steps:
                    bar.setValue(
                        bar.value()
                        - round(steps * max(1, bar.singleStep()) * 3)
                    )
        event.accept()
        return True


def guard_closed_combo_wheels(widget):
    """Install one retained wheel guard on all current child combo boxes."""
    guard = ClosedComboWheelGuard(widget)
    for combo in widget.findChildren(QComboBox):
        combo.installEventFilter(guard)
    widget._qeoloog_combo_wheel_guard = guard
    return guard
