"""Map tool for selecting EGT boreholes and observation points."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor
from qgis.gui import QgsMapTool


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
