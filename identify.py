"""Map tool for selecting EGT boreholes and observation points."""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.core import Qgis
from qgis.gui import QgsMapTool, QgsRubberBand


class EgtIdentifyTool(QgsMapTool):
    """Forward a canvas click to the plugin while retaining QGIS map-tool behaviour."""

    def __init__(self, canvas, plugin):
        super().__init__(canvas)
        self.plugin = plugin
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def canvasReleaseEvent(self, event):
        self.plugin.identify_at(event.mapPoint())

    def deactivate(self):
        super().deactivate()
        self.plugin.identify_tool_deactivated()


class CrossSectionLineTool(QgsMapTool):
    """Collect a multi-segment section line; right-click or Enter finishes."""

    lineFinished = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.points = []
        self.preview_point = None
        self.band = QgsRubberBand(canvas, Qgis.GeometryType.Line)
        self.band.setColor(QColor("#d04432"))
        self.band.setWidth(2)
        self.band.setZValue(10000)
        self.band.hide()
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def activate(self):
        self.points = []
        self.preview_point = None
        self.band.reset(Qgis.GeometryType.Line)
        self.band.show()
        super().activate()

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.finish()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.points.append(event.mapPoint())
        self.preview_point = None
        self._refresh()

    def canvasMoveEvent(self, event):
        if self.points:
            self.preview_point = event.mapPoint()
            self._refresh()

    def canvasDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = event.mapPoint()
            if not self.points or self.points[-1] != point:
                self.points.append(point)
            self.finish()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish()
            return
        super().keyPressEvent(event)

    def finish(self):
        if len(self.points) >= 2:
            self.lineFinished.emit([
                (point.x(), point.y()) for point in self.points
            ])
        else:
            self.cancelled.emit()
        self.band.reset(Qgis.GeometryType.Line)
        self.band.hide()

    def cancel(self):
        self.points = []
        self.preview_point = None
        self.band.reset(Qgis.GeometryType.Line)
        self.band.hide()
        self.cancelled.emit()

    def deactivate(self):
        self.band.reset(Qgis.GeometryType.Line)
        self.band.hide()
        super().deactivate()

    def _refresh(self):
        self.band.reset(Qgis.GeometryType.Line)
        for point in self.points:
            self.band.addPoint(point, False)
        if self.preview_point is not None:
            self.band.addPoint(self.preview_point, False)
        self.band.updatePosition()
        self.band.show()
        self.canvas.update()


class ExportAreaTool(QgsMapTool):
    """Collect a polygon used to limit Leapfrog exports."""

    areaFinished = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.points = []
        self.preview_point = None
        self.band = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self.band.setColor(QColor(53, 132, 228, 55))
        self.band.setStrokeColor(QColor("#3584e4"))
        self.band.setWidth(2)
        self.band.setZValue(10000)
        self.band.hide()
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def activate(self):
        self.points = []
        self.preview_point = None
        self.band.reset(Qgis.GeometryType.Polygon)
        self.band.show()
        super().activate()

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.finish()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.points.append(event.mapPoint())
        self.preview_point = None
        self._refresh()

    def canvasMoveEvent(self, event):
        if self.points:
            self.preview_point = event.mapPoint()
            self._refresh()

    def canvasDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = event.mapPoint()
            if not self.points or self.points[-1] != point:
                self.points.append(point)
            self.finish()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish()
            return
        super().keyPressEvent(event)

    def finish(self):
        if len(self.points) >= 3:
            self.areaFinished.emit([
                (point.x(), point.y()) for point in self.points
            ])
        else:
            self.cancelled.emit()
        self.band.reset(Qgis.GeometryType.Polygon)
        self.band.hide()

    def cancel(self):
        self.points = []
        self.preview_point = None
        self.band.reset(Qgis.GeometryType.Polygon)
        self.band.hide()
        self.cancelled.emit()

    def deactivate(self):
        self.band.reset(Qgis.GeometryType.Polygon)
        self.band.hide()
        super().deactivate()

    def _refresh(self):
        self.band.reset(Qgis.GeometryType.Polygon)
        for point in self.points:
            self.band.addPoint(point, False)
        if self.preview_point is not None:
            self.band.addPoint(self.preview_point, False)
        self.band.updatePosition()
        self.band.show()
        self.canvas.update()
