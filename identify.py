"""Map tool for selecting EGT boreholes and observation points."""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.core import Qgis, QgsPointXY, QgsProject, QgsSnappingConfig, QgsSnappingUtils
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker


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


class FaktikaPointTool(QgsMapTool):
    """Pick one PointZ location for a newly created Faktika object."""

    pointSelected = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pointSelected.emit(event.mapPoint())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)


class ElevationCandidateTool(QgsMapTool):
    """Pick a candidate XY for a Portal object's DEM height check."""

    pointSelected = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pointSelected.emit(event.mapPoint())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)


class CrossSectionLineTool(QgsMapTool):
    """Collect a multi-segment section line; right-click or Enter finishes."""

    lineFinished = pyqtSignal(object)
    cancelled = pyqtSignal()
    SNAP_TOLERANCE_PIXELS = 12.0

    def __init__(self, canvas, snap_layers=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.snap_layers = snap_layers or (lambda: ())
        self.points = []
        self.preview_point = None
        self._snap_signature = None
        self._saved_snapping_config = None
        self._watched_layers = []
        self._snapping = QgsSnappingUtils(self, False)
        self._snapping.setIndexingStrategy(QgsSnappingUtils.IndexExtent)
        self.band = QgsRubberBand(canvas, Qgis.GeometryType.Line)
        self.band.setColor(QColor("#d04432"))
        self.band.setWidth(2)
        self.band.setZValue(10000)
        self.band.hide()
        self.snap_marker = QgsVertexMarker(canvas)
        self.snap_marker.setColor(QColor("#ffd43b"))
        self.snap_marker.setFillColor(QColor(255, 212, 59, 55))
        self.snap_marker.setIconType(QgsVertexMarker.ICON_BOX)
        self.snap_marker.setIconSize(13)
        self.snap_marker.setPenWidth(2)
        self.snap_marker.setZValue(10001)
        self.snap_marker.hide()
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def activate(self):
        if self._saved_snapping_config is None:
            self._saved_snapping_config = QgsSnappingConfig(
                QgsProject.instance().snappingConfig()
            )
        self.points = []
        self.preview_point = None
        self._snap_signature = None
        self._configure_snapping()
        self.band.reset(Qgis.GeometryType.Line)
        self.band.show()
        self.snap_marker.hide()
        super().activate()

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.finish()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point, snapped = self._snap_point(event.mapPoint(), relaxed=False)
        self.points.append(point)
        self.preview_point = None
        self._show_snap_marker(point, snapped)
        self._refresh()

    def canvasMoveEvent(self, event):
        point, snapped = self._snap_point(event.mapPoint(), relaxed=True)
        self._show_snap_marker(point, snapped)
        if self.points:
            self.preview_point = point
            self._refresh()

    def canvasDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point, snapped = self._snap_point(
                event.mapPoint(), relaxed=False
            )
            self._show_snap_marker(point, snapped)
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
        self.snap_marker.hide()

    def cancel(self):
        self.points = []
        self.preview_point = None
        self.band.reset(Qgis.GeometryType.Line)
        self.band.hide()
        self.snap_marker.hide()
        self.cancelled.emit()

    def deactivate(self):
        self.band.reset(Qgis.GeometryType.Line)
        self.band.hide()
        self.snap_marker.hide()
        self._disconnect_snap_layers()
        if self._saved_snapping_config is not None:
            config = self._saved_snapping_config
            self._saved_snapping_config = None
            QgsProject.instance().setSnappingConfig(config)
            self.canvas.snappingUtils().setConfig(config)
        super().deactivate()

    def _invalidate_snapping(self, *_args):
        # Rebuild on the next mouse event, outside provider/render signals.
        # Reusing an empty locator after changing EGT filters otherwise
        # silently prevents all later snaps, including after reactivation.
        self._snap_signature = None

    def _disconnect_snap_layers(self):
        for layer in self._watched_layers:
            try:
                for signal in (
                    layer.repaintRequested, layer.dataChanged,
                    layer.rendererChanged, layer.subsetStringChanged,
                ):
                    signal.disconnect(self._invalidate_snapping)
            except (TypeError, RuntimeError):
                pass
        self._watched_layers = []

    def _configuration_signature(self, layers):
        settings = self.canvas.mapSettings()
        extent = settings.extent()
        return (
            settings.destinationCrs().authid(),
            round(extent.xMinimum(), 9), round(extent.yMinimum(), 9),
            round(extent.xMaximum(), 9), round(extent.yMaximum(), 9),
            settings.outputSize().width(), settings.outputSize().height(),
            settings.rotation(),
            tuple(layer.id() for layer in layers),
        )

    def _configure_snapping(self):
        layers = [
            layer for layer in self.snap_layers()
            if layer is not None and layer.isValid()
        ]
        signature = self._configuration_signature(layers)
        if signature == self._snap_signature:
            return
        self._disconnect_snap_layers()
        # setConfig alone does not discard a cached empty/filtered locator.
        self._snapping.clearAllLocators()
        config = QgsSnappingConfig()
        config.clearIndividualLayerSettings()
        config.setEnabled(True)
        config.setMode(QgsSnappingConfig.AdvancedConfiguration)
        config.setTypeFlag(Qgis.SnappingType.Vertex)
        config.setTolerance(self.SNAP_TOLERANCE_PIXELS)
        config.setUnits(Qgis.MapToolUnit.Pixels)
        config.setIntersectionSnapping(False)
        config.setSelfSnapping(False)
        config.setScaleDependencyMode(QgsSnappingConfig.Disabled)
        for layer in layers:
            config.setIndividualLayerSettings(
                layer,
                QgsSnappingConfig.IndividualLayerSettings(
                    True,
                    Qgis.SnappingType.Vertex,
                    self.SNAP_TOLERANCE_PIXELS,
                    Qgis.MapToolUnit.Pixels,
                ),
            )
        self._snapping.setMapSettings(self.canvas.mapSettings())
        self._snapping.setConfig(config)
        if self._saved_snapping_config is not None:
            # Enable the QGIS snapping toggle and show the actual point-layer
            # rules automatically for the lifetime of this drawing tool.
            QgsProject.instance().setSnappingConfig(config)
            self.canvas.snappingUtils().setConfig(config)
            for layer in layers:
                for signal in (
                    layer.repaintRequested, layer.dataChanged,
                    layer.rendererChanged, layer.subsetStringChanged,
                ):
                    signal.connect(self._invalidate_snapping)
            self._watched_layers = layers
        self._snap_signature = signature

    def _snap_point(self, map_point, relaxed=False):
        """Return the exact nearby section-object coordinate when available."""
        self._configure_snapping()
        match = self._snapping.snapToMap(
            QgsPointXY(map_point), None, bool(relaxed)
        )
        if match.isValid() and match.hasVertex():
            return QgsPointXY(match.point()), True
        return QgsPointXY(map_point), False

    def _show_snap_marker(self, point, snapped):
        if snapped:
            self.snap_marker.setCenter(point)
            self.snap_marker.show()
        else:
            self.snap_marker.hide()

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
