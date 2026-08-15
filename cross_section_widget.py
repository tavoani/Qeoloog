"""Interactive multi-well cross-section builder for Qeoloog."""

import json
from math import ceil

from qgis.PyQt.QtCore import QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QFont,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)
from qgis.PyQt.QtSvg import QSvgGenerator
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeatureRequest,
    QgsMapRendererCustomPainterJob,
    QgsMapSettings,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
)

from .cross_section import (
    elevation_range,
    line_from_items,
    number,
    point_at_station,
    polyline_length,
    section_positions,
)


STATE_SCOPE = "Qeoloog"
STATE_KEY = "cross_section_v1"
METRIC_CRS = QgsCoordinateReferenceSystem("EPSG:3301")


def _safe_number(value, fallback=0.0):
    result = number(value)
    return fallback if result is None else result


def _unit_index(unit):
    index = unit.get("indeks") or unit.get("indeks_orig") or ""
    if str(index).strip().casefold() != "liitüksus":
        return str(index)
    lower = str(unit.get("liityksus_indeks_alumine") or "").strip()
    upper = str(unit.get("liityksus_indeks_ylemine") or "").strip()
    invalid = {"", "ei kohaldu", "teadmata"}
    lower = "" if lower.casefold() in invalid else lower
    upper = "" if upper.casefold() in invalid else upper
    return f"{lower}-{upper}" if lower and upper and lower != upper else lower or upper


def _stratigraphic_color(unit):
    first = _unit_index(unit).replace(" ", "").upper().split("-", 1)[0]
    mappings = (
        ("Q2", "#fff2cc"), ("Q1", "#fff2ae"), ("Q", "#fcfc8b"),
        ("D3", "#f1e19d"), ("D2-3", "#f1d583"),
        ("D2", "#f1c868"), ("D1-2", "#ebba5b"),
        ("D1", "#e5ac4d"), ("D", "#cb8c37"),
        ("S4", "#e6f5e1"), ("S3-4", "#d3eed8"),
        ("S3", "#bfe6cf"), ("S2-3", "#b3e1c2"),
        ("S2", "#a6dcbb"), ("S1-2", "#99d7b3"),
        ("S1", "#8cd1a3"), ("S", "#b3e1b6"),
        ("O3", "#7fca93"), ("O2", "#4db47e"),
        ("O1-2", "#34a977"), ("O1", "#1a9d6f"),
        ("O", "#009270"), ("CM4", "#b3e095"),
        ("CM3", "#a6cf86"), ("CM2", "#99c078"),
        ("CM1", "#8cb06c"), ("CM", "#7fa056"),
        ("E", "#ffdc88"), ("MP", "#fac180"), ("PP", "#ec607e"),
    )
    for prefix, color in mappings:
        if first.startswith(prefix):
            return QColor(color)
    category = int(_safe_number(
        unit.get("klassif_yksus_kood") or unit.get("yksus_kood")
    ))
    return QColor({
        1: "#fcfc8b", 2: "#a7a7a7", 3: "#ec607e", 997: "#a7a7a7",
    }.get(category, "#a7a7a7"))


class CrossSectionCanvas(QWidget):
    """Draw several existing Qeoloog profile snapshots on shared axes."""

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.items = []
        self.mode = "line"
        self.line = []
        self.terrain = []
        self.horizontal_scale = 0.12
        self.vertical_scale = 4.0
        self.display = {
            "indices": True,
            "lithology": True,
            "boundaries": True,
            "core": True,
            "samples": True,
            "analyses": True,
            "specimens": True,
            "construction": True,
            "water": True,
            "wellheads": True,
            "terrain": True,
        }
        self.setMinimumSize(700, 500)

    def set_model(
        self, items=None, mode=None, line=None, terrain=None,
        horizontal_scale=None, vertical_scale=None, display=None,
    ):
        if items is not None:
            self.items = list(items)
        if mode is not None:
            self.mode = mode
        if line is not None:
            self.line = list(line)
        if terrain is not None:
            self.terrain = list(terrain)
        if horizontal_scale is not None:
            self.horizontal_scale = float(horizontal_scale)
        if vertical_scale is not None:
            self.vertical_scale = float(vertical_scale)
        if display is not None:
            self.display.update(display)
        rows = section_positions(self.items, self.mode, self.line)
        stations = [
            row["_station"] for row in rows if row.get("_station") is not None
        ]
        span = max(stations, default=0.0) - min(stations, default=0.0)
        minimum, maximum = elevation_range(rows, self.terrain)
        self.setMinimumWidth(max(700, round(260 + span * self.horizontal_scale)))
        self.setMinimumHeight(max(
            500, round(150 + (maximum - minimum) * self.vertical_scale)
        ))
        self.updateGeometry()
        self.update()

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
            self.vertical_scale = max(0.5, min(30.0, self.vertical_scale * factor))
            self.set_model(vertical_scale=self.vertical_scale)
            event.accept()
            return
        if modifiers & Qt.KeyboardModifier.AltModifier:
            factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
            self.horizontal_scale = max(
                0.005, min(5.0, self.horizontal_scale * factor)
            )
            self.set_model(horizontal_scale=self.horizontal_scale)
            event.accept()
            return
        event.ignore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))
        self.draw_section(painter, QRectF(self.rect()), fit=False)

    def draw_section(self, painter, rect, fit=True, show_heading=True):
        rows = section_positions(self.items, self.mode, self.line)
        drawable = [
            row for row in rows
            if row.get("_station") is not None
            and number(row.get("elevation")) is not None
        ]
        painter.save()
        painter.setClipRect(rect)
        family = painter.font().family()
        painter.setFont(QFont(family, 8))
        if not drawable:
            painter.setPen(QColor("#555555"))
            painter.setFont(QFont(family, 9))
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignCenter,
                self.plugin.t(
                    "Lisa läbilõikele vähemalt üks koordinaatide ja "
                    "absoluutkõrgusega objekt."
                ),
            )
            painter.restore()
            return

        min_elevation, max_elevation = elevation_range(drawable, self.terrain)
        min_station = min(row["_station"] for row in drawable)
        max_station = max(row["_station"] for row in drawable)
        station_span = max(1.0, max_station - min_station)
        left_margin, right_margin = 78.0, 80.0
        top_margin, bottom_margin = 80.0, 55.0
        if fit:
            x_scale = max(
                0.001,
                (rect.width() - left_margin - right_margin) / station_span,
            )
            y_scale = max(
                0.001,
                (rect.height() - top_margin - bottom_margin)
                / max(1.0, max_elevation - min_elevation),
            )
        else:
            x_scale = self.horizontal_scale
            y_scale = self.vertical_scale
        origin_x = rect.left() + left_margin
        origin_y = rect.top() + top_margin

        def x_for(station):
            return origin_x + (station - min_station) * x_scale

        def y_for(elevation):
            return origin_y + (max_elevation - elevation) * y_scale

        content_right = x_for(max_station) + right_margin
        content_bottom = y_for(min_elevation)
        painter.setPen(QPen(QColor("#7c858d"), 1))
        painter.drawLine(
            round(origin_x - 10), round(origin_y),
            round(origin_x - 10), round(content_bottom),
        )
        step = self._nice_elevation_step(
            max_elevation - min_elevation, rect.height()
        )
        elevation = ceil(min_elevation / step) * step
        while elevation <= max_elevation + step / 100:
            y = y_for(elevation)
            painter.setPen(QPen(QColor(100, 110, 120, 45), 1))
            painter.drawLine(
                round(origin_x - 14), round(y),
                round(content_right), round(y),
            )
            painter.setPen(QColor("#4e565d"))
            painter.setFont(QFont(family, 8))
            painter.drawText(
                QRectF(rect.left(), y - 9, left_margin - 16, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{elevation:g} m",
            )
            elevation += step

        if self.display["terrain"] and self.terrain:
            terrain_points = [
                (x_for(station), y_for(elevation))
                for station, elevation in self.terrain
                if number(elevation) is not None
            ]
            painter.setPen(QPen(QColor("#5c8c42"), 2.2))
            for first, second in zip(terrain_points, terrain_points[1:]):
                painter.drawLine(
                    round(first[0]), round(first[1]),
                    round(second[0]), round(second[1]),
                )

        if self.display["wellheads"]:
            painter.setPen(QPen(QColor("#725f46"), 1.4))
            surface = [
                (x_for(row["_station"]), y_for(float(row["elevation"])))
                for row in drawable
            ]
            for first, second in zip(surface, surface[1:]):
                painter.drawLine(
                    round(first[0]), round(first[1]),
                    round(second[0]), round(second[1]),
                )

        for row in drawable:
            self._draw_item(
                painter, row, x_for(row["_station"]), y_for, x_scale,
                min_station,
            )

        mode_label = self.plugin.t({
            "line": "Kaardijoone järgi",
            "order": "Objektide järjekorra järgi",
            "equal": "Võrdsete vahedega",
        }.get(self.mode, self.mode))
        if show_heading:
            painter.setPen(QColor("#41484e"))
            painter.setFont(QFont(family, 11, QFont.Weight.Bold))
            painter.drawText(
                QRectF(
                    rect.left() + 5, rect.top() + 5,
                    rect.width() - 10, 26,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.plugin.t("Koondläbilõige"),
            )
            painter.setPen(QColor("#687078"))
            painter.setFont(QFont(family, 8))
            painter.drawText(
                QRectF(
                    rect.left() + 5, rect.top() + 30,
                    rect.width() - 10, 22,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                mode_label,
            )
        else:
            painter.setPen(QColor("#687078"))
            painter.setFont(QFont(family, 8))
            painter.drawText(
                QRectF(
                    rect.left() + 5, rect.top() + 4,
                    rect.width() - 10, 20,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                mode_label,
            )
        legend_x = rect.right() - 190
        legend_y = rect.top() + 14
        painter.setFont(QFont(family, 7))
        if self.display["wellheads"]:
            painter.setPen(QPen(QColor("#725f46"), 1.4))
            painter.drawLine(
                round(legend_x), round(legend_y),
                round(legend_x + 22), round(legend_y),
            )
            painter.setPen(QColor("#596169"))
            painter.drawText(
                QRectF(legend_x + 28, legend_y - 9, 150, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.plugin.t("Andmete absoluutkõrgus"),
            )
            legend_y += 18
        if self.display["terrain"] and self.terrain:
            painter.setPen(QPen(QColor("#5c8c42"), 2.2))
            painter.drawLine(
                round(legend_x), round(legend_y),
                round(legend_x + 22), round(legend_y),
            )
            painter.setPen(QColor("#596169"))
            painter.drawText(
                QRectF(legend_x + 28, legend_y - 9, 150, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.plugin.t("DEM maapind"),
            )
        painter.restore()

    def _draw_item(self, painter, row, center_x, y_for, x_scale, min_station):
        elevation = float(row["elevation"])
        depth = max(0.0, _safe_number(row.get("depth")))
        bar_width = 58.0
        left = center_x - bar_width / 2
        painter.save()
        painter.setPen(QPen(QColor("#33383c"), 1.2))
        painter.drawLine(
            round(center_x), round(y_for(elevation)),
            round(center_x), round(y_for(elevation - depth)),
        )

        units = row.get("units") or []
        for unit in units:
            top = _safe_number(unit.get("z_suht_ylemine"))
            bottom = _safe_number(unit.get("z_suht_alumine"), top)
            if bottom < top:
                continue
            y_top = y_for(elevation - top)
            y_bottom = y_for(elevation - bottom)
            height = max(2.0, y_bottom - y_top)
            painter.fillRect(
                QRectF(left, y_top, bar_width, height),
                _stratigraphic_color(unit),
            )
            if self.display["boundaries"]:
                painter.setPen(QPen(QColor("#555b60"), 0.8))
                painter.drawRect(QRectF(left, y_top, bar_width, height))
            label_x = left + bar_width + 4
            label = []
            if self.display["indices"] and _unit_index(unit):
                label.append(_unit_index(unit))
            lithology = unit.get("litoloogia") or unit.get("litoloogia_orig")
            if self.display["lithology"] and lithology:
                label.append(str(lithology))
            if label and height >= 7:
                painter.setPen(QColor("#42484d"))
                painter.setFont(QFont(painter.font().family(), 7))
                painter.drawText(
                    QRectF(label_x, y_top, 130, max(14, height)),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    " · ".join(label),
                )

        if self.display["core"]:
            painter.setPen(QPen(
                QColor("#2d2d2d"), 0.8, Qt.PenStyle.DashLine
            ))
            for box in (row.get("core_boxes") or []) + (
                row.get("sarv_core_boxes") or []
            ):
                for key in ("z_suht_ylemine", "z_suht_alumine"):
                    box_depth = number(box.get(key))
                    if box_depth is not None:
                        y = y_for(elevation - box_depth)
                        painter.drawLine(
                            round(left), round(y),
                            round(left + bar_width), round(y),
                        )

        track_left = left + bar_width + 1
        tracks = (
            ("samples", row.get("samples") or [], QColor("#4f9b61")),
            ("analyses", row.get("analyses") or [], QColor("#8b4a9b")),
            ("samples", row.get("sarv_samples") or [], QColor("#267d92")),
            ("analyses", row.get("sarv_analyses") or [], QColor("#c06b25")),
            ("specimens", row.get("sarv_specimens") or [], QColor("#b23a62")),
        )
        for key, values, color in tracks:
            if not self.display[key]:
                continue
            painter.setPen(QPen(color.darker(130), 0.8))
            painter.setBrush(color)
            for interval in values:
                top = _safe_number(interval.get("z_suht_ylemine"))
                bottom = _safe_number(
                    interval.get("z_suht_alumine"), top
                )
                y_top = y_for(elevation - top)
                y_bottom = y_for(elevation - bottom)
                painter.drawRect(QRectF(
                    track_left, y_top, 6, max(3, y_bottom - y_top)
                ))
            track_left += 8
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self.display["construction"]:
            construction_left = left - 13
            for part in row.get("veka_construction") or []:
                top = _safe_number(
                    part.get("z_suht_ylemine", part.get("alg"))
                )
                bottom = _safe_number(
                    part.get("z_suht_alumine", part.get("lopp")), top
                )
                y_top = y_for(elevation - top)
                y_bottom = y_for(elevation - bottom)
                category = part.get("_category", "other")
                color = {
                    "filter": QColor("#237a9b"),
                    "casing": QColor("#3f474d"),
                    "open": QColor("#d07a22"),
                    "drill": QColor("#737b82"),
                }.get(category, QColor("#92989d"))
                style = (
                    Qt.PenStyle.DashLine
                    if category == "open" else Qt.PenStyle.SolidLine
                )
                painter.setPen(QPen(color, 2, style))
                painter.drawLine(
                    round(construction_left), round(y_top),
                    round(construction_left), round(y_bottom),
                )

        if self.display["water"] and row.get("static_water"):
            water_depth = number(row["static_water"].get("st_veetase"))
            if water_depth is not None:
                y = y_for(elevation - water_depth)
                painter.setPen(QPen(
                    QColor("#1677b8"), 1.4, Qt.PenStyle.DashDotLine
                ))
                painter.drawLine(
                    round(left - 7), round(y),
                    round(track_left + 6), round(y),
                )

        surface_y = y_for(elevation)
        station = row.get("_station")
        terrain_height = self._terrain_at(station)
        delta_color = QColor("#626b72")
        if terrain_height is not None:
            delta = elevation - terrain_height
            delta_color = (
                QColor("#b3261e") if abs(delta) >= 3.0
                else QColor("#a06400") if abs(delta) >= 1.0
                else QColor("#527342")
            )
            terrain_y = y_for(terrain_height)
            comparison_x = left - 7
            painter.setPen(QPen(
                delta_color, 1.1, Qt.PenStyle.DashLine
            ))
            painter.drawLine(
                round(comparison_x), round(surface_y),
                round(comparison_x), round(terrain_y),
            )
            painter.drawLine(
                round(comparison_x - 3), round(surface_y),
                round(comparison_x + 3), round(surface_y),
            )
            painter.drawLine(
                round(comparison_x - 3), round(terrain_y),
                round(comparison_x + 3), round(terrain_y),
            )
        painter.setPen(QPen(QColor("#22272b"), 1))
        painter.setBrush(QColor("#22272b"))
        painter.drawEllipse(QRectF(center_x - 3, surface_y - 3, 6, 6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        name = str(row.get("name") or row.get("id") or "")
        if len(name) > 22:
            name = name[:20] + "…"
        offset = row.get("_offset")
        subtitle = (
            f"{station:g} m"
            if self.mode != "equal" and station is not None
            else str(row.get("source") or "")
        )
        if offset is not None and self.mode == "line":
            subtitle += f" · ±{offset:g} m"
        if terrain_height is not None:
            subtitle += f" · ΔDEM {elevation - terrain_height:+.1f} m"
        painter.setPen(QColor("#293038"))
        painter.setFont(QFont(painter.font().family(), 8, QFont.Weight.Bold))
        painter.drawText(
            QRectF(center_x - 72, surface_y - 47, 144, 18),
            Qt.AlignmentFlag.AlignCenter, name,
        )
        painter.setFont(QFont(painter.font().family(), 7))
        painter.setPen(delta_color)
        painter.drawText(
            QRectF(center_x - 82, surface_y - 30, 164, 18),
            Qt.AlignmentFlag.AlignCenter, subtitle,
        )
        painter.restore()

    def _terrain_at(self, station):
        if station is None or not self.terrain:
            return None
        return min(
            self.terrain, key=lambda pair: abs(pair[0] - station)
        )[1]

    @staticmethod
    def _nice_elevation_step(span, height):
        target = max(2.0, span / max(4, int(height / 90)))
        choices = (1, 2, 5, 10, 20, 25, 50, 100, 200, 500)
        return next((value for value in choices if value >= target), choices[-1])


class CrossSectionWidget(QWidget):
    """Manage the current project cross-section and its export."""

    modelChanged = pyqtSignal(int)

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.items = []
        self.line = []
        self.terrain = []
        self._updating = False
        self._build_ui()
        self.reload_rasters()
        self.load_project_state()

    def _build_ui(self):
        t = self.plugin.t
        outer = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.name = QLineEdit(t("Koondläbilõige"))
        self.name.editingFinished.connect(self.save_project_state)
        toolbar.addWidget(QLabel(t("Nimi")))
        toolbar.addWidget(self.name, 1)
        self.mode = QComboBox()
        for label, value in (
            ("Kaardijoone järgi", "line"),
            ("Objektide järjekorra järgi", "order"),
            ("Võrdsete vahedega", "equal"),
        ):
            self.mode.addItem(t(label), value)
        self.mode.currentIndexChanged.connect(self._model_changed)
        toolbar.addWidget(self.mode)
        draw_line = QPushButton(t("Joonista kaardil"))
        draw_line.clicked.connect(self.plugin.start_cross_section_line)
        toolbar.addWidget(draw_line)
        clear = QPushButton(t("Uus / tühjenda"))
        clear.clicked.connect(self.clear)
        toolbar.addWidget(clear)
        outer.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels((
            t("Kuva"), t("Allikas"), t("Nimi"), t("Absoluutkõrgus"),
            t("Sügavus"), t("Pikett"), t("Kõrvalekalle"),
        ))
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.itemChanged.connect(self._table_changed)
        left_layout.addWidget(self.table)
        row_actions = QHBoxLayout()
        for label, callback in (
            ("↑", lambda: self.move_selected(-1)),
            ("↓", lambda: self.move_selected(1)),
            ("Pööra", self.reverse),
            ("Määra kõrgus", self.set_selected_elevation),
            ("Eemalda", self.remove_selected),
        ):
            button = QPushButton(t(label))
            button.clicked.connect(callback)
            row_actions.addWidget(button)
        left_layout.addLayout(row_actions)
        splitter.addWidget(left)

        self.canvas = CrossSectionCanvas(self.plugin)
        canvas_scroll = QScrollArea()
        canvas_scroll.setWidgetResizable(False)
        canvas_scroll.setWidget(self.canvas)
        splitter.addWidget(canvas_scroll)

        options = QWidget()
        options_layout = QVBoxLayout(options)
        display_group = QGroupBox(t("Kuvamine"))
        display_layout = QVBoxLayout(display_group)
        self.display_checks = {}
        for key, label in (
            ("indices", "Indeksid"),
            ("lithology", "Litoloogia"),
            ("boundaries", "Piiride sügavused"),
            ("core", "Puursüdamiku kastid"),
            ("samples", "Proovid"),
            ("analyses", "Analüüsid"),
            ("specimens", "Eksemplarid"),
            ("construction", "Konstruktsioon"),
            ("water", "Staatiline veetase"),
            ("wellheads", "Ühenda suudmed"),
            ("terrain", "DEM maapinnaprofiil"),
        ):
            checkbox = QCheckBox(t(label))
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._display_changed)
            self.display_checks[key] = checkbox
            display_layout.addWidget(checkbox)
        options_layout.addWidget(display_group)

        scale_group = QGroupBox(t("Mõõtkava"))
        scale_form = QFormLayout(scale_group)
        self.horizontal_scale = QDoubleSpinBox()
        self.horizontal_scale.setRange(0.005, 5.0)
        self.horizontal_scale.setDecimals(3)
        self.horizontal_scale.setSingleStep(0.02)
        self.horizontal_scale.setValue(0.12)
        self.horizontal_scale.valueChanged.connect(self._model_changed)
        self.vertical_scale = QDoubleSpinBox()
        self.vertical_scale.setRange(0.5, 30.0)
        self.vertical_scale.setSingleStep(0.5)
        self.vertical_scale.setValue(4.0)
        self.vertical_scale.valueChanged.connect(self._model_changed)
        scale_form.addRow(t("Horisontaalne px/m"), self.horizontal_scale)
        scale_form.addRow(t("Vertikaalne px/m"), self.vertical_scale)
        options_layout.addWidget(scale_group)

        dem_group = QGroupBox(t("DEM"))
        dem_form = QFormLayout(dem_group)
        self.dem_layer = QComboBox()
        self.dem_band = QSpinBox()
        self.dem_band.setRange(1, 99)
        self.dem_band.setValue(1)
        self.dem_band.valueChanged.connect(self.sample_dem)
        refresh_dem = QPushButton(t("Värskenda rasterkihte"))
        refresh_dem.clicked.connect(self.reload_rasters)
        sample_dem = QPushButton(t("Loe DEM-profiil"))
        sample_dem.clicked.connect(self.sample_dem)
        dem_form.addRow(t("Rasterkiht"), self.dem_layer)
        dem_form.addRow(t("Kõrguskanal"), self.dem_band)
        dem_form.addRow(refresh_dem)
        dem_form.addRow(sample_dem)
        options_layout.addWidget(dem_group)

        map_group = QGroupBox(t("Kaart ja eksport"))
        map_layout = QVBoxLayout(map_group)
        self.show_map_line = QCheckBox(t("Kuva läbilõikejoon kaardil"))
        self.show_map_line.setChecked(True)
        self.show_map_line.toggled.connect(self._map_line_changed)
        self.include_overview = QCheckBox(t("Lisa ülevaatekaart"))
        self.include_overview.setChecked(True)
        export_svg = QPushButton(t("Ekspordi SVG"))
        export_pdf = QPushButton(t("Ekspordi PDF"))
        export_svg.clicked.connect(lambda: self.export("svg"))
        export_pdf.clicked.connect(lambda: self.export("pdf"))
        map_layout.addWidget(self.show_map_line)
        map_layout.addWidget(self.include_overview)
        map_layout.addWidget(export_svg)
        map_layout.addWidget(export_pdf)
        options_layout.addWidget(map_group)
        options_layout.addStretch(1)
        options_scroll = QScrollArea()
        options_scroll.setWidgetResizable(True)
        options_scroll.setMinimumWidth(250)
        options_scroll.setWidget(options)
        splitter.addWidget(options_scroll)
        splitter.setSizes((330, 850, 260))
        self.status = QLabel()
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

    def item_key(self, snapshot):
        return str(snapshot.get("key") or "")

    def contains(self, key):
        return any(self.item_key(item) == str(key) for item in self.items)

    def add_snapshot(self, snapshot):
        if not snapshot or not snapshot.get("key"):
            return
        snapshot = self._json_safe(snapshot)
        key = self.item_key(snapshot)
        for index, item in enumerate(self.items):
            if self.item_key(item) == key:
                enabled = item.get("enabled", True)
                replacement = {**snapshot, "enabled": enabled}
                if item.get("elevation_override"):
                    replacement["elevation"] = item.get("elevation")
                    replacement["elevation_override"] = True
                    replacement["elevation_source"] = "manual"
                self.items[index] = replacement
                break
        else:
            snapshot["enabled"] = True
            self.items.append(snapshot)
        self.refresh()
        self.save_project_state()

    def backfill_egt_elevations(self):
        """Recover elevations missing from snapshots made before PointZ support."""
        missing = [
            item for item in self.items
            if item.get("role") in {"boreholes", "observations"}
            and number(item.get("elevation")) is None
            and number(item.get("x")) is not None
            and number(item.get("y")) is not None
        ]
        if not missing:
            return 0
        recovered = 0
        project = QgsProject.instance()
        for item in missing:
            expected_id = str(item.get("id") or "").strip().casefold()
            for layer in self.plugin._role_layers(item["role"]):
                try:
                    point = QgsCoordinateTransform(
                        METRIC_CRS, layer.crs(), project
                    ).transform(QgsPointXY(
                        float(item["x"]), float(item["y"])
                    ))
                except (QgsCsException, TypeError, ValueError):
                    continue
                radius = 0.00001 if layer.crs().isGeographic() else 1.0
                request = QgsFeatureRequest().setFilterRect(QgsRectangle(
                    point.x() - radius, point.y() - radius,
                    point.x() + radius, point.y() + radius,
                ))
                candidates = list(layer.getFeatures(request))
                if not candidates:
                    continue
                feature = next((
                    candidate for candidate in candidates
                    if expected_id and expected_id == str(
                        candidate.attribute("esri_globalid")
                        if layer.fields().indexOf("esri_globalid") >= 0
                        else candidate.attribute("globalid")
                        if layer.fields().indexOf("globalid") >= 0
                        else ""
                    ).strip().casefold()
                ), candidates[0])
                attributes = self.plugin._detail_attributes_with_location(
                    {}, layer, feature
                )
                elevation = number(attributes.get("z_abs"))
                if elevation is None:
                    continue
                item["elevation"] = elevation
                item["elevation_source"] = "WFS PointZ"
                recovered += 1
                break
        if recovered:
            self.refresh()
            self.save_project_state()
        return recovered

    def remove_key(self, key):
        self.items = [
            item for item in self.items if self.item_key(item) != str(key)
        ]
        self.refresh()
        self.save_project_state()

    def clear(self):
        if self.items and QMessageBox.question(
            self, self.plugin.t("Uus / tühjenda"),
            self.plugin.t("Kas eemaldada kõik koondläbilõike objektid?"),
        ) != QMessageBox.StandardButton.Yes:
            return
        self.items = []
        self.line = []
        self.terrain = []
        self.refresh()
        self.save_project_state()

    def move_selected(self, direction):
        row = self.table.currentRow()
        target = row + direction
        if row < 0 or not 0 <= target < len(self.items):
            return
        self.items[row], self.items[target] = self.items[target], self.items[row]
        self.refresh()
        self.table.selectRow(target)
        self.save_project_state()

    def reverse(self):
        self.items.reverse()
        self.line.reverse()
        self.refresh()
        self.save_project_state()

    def remove_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.items):
            self.items.pop(row)
            self.refresh()
            self.save_project_state()

    def set_selected_elevation(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.items):
            return
        current = number(self.items[row].get("elevation")) or 0.0
        value, accepted = QInputDialog.getDouble(
            self, self.plugin.t("Määra kõrgus"),
            self.plugin.t("Absoluutkõrgus"), current,
            -500.0, 10000.0, 2,
        )
        if accepted:
            self.items[row]["elevation"] = value
            self.items[row]["elevation_override"] = True
            self.refresh()
            self.save_project_state()

    def set_line(self, points):
        self.line = [
            [float(point[0]), float(point[1])] for point in points
        ]
        self.mode.setCurrentIndex(self.mode.findData("line"))
        self.terrain = []
        self.refresh()
        self.sample_dem()
        self.save_project_state()

    def effective_line(self):
        if self.mode.currentData() == "line" and len(self.line) >= 2:
            return list(self.line)
        return line_from_items(self.items)

    def refresh(self):
        rows = section_positions(
            self.items, self.mode.currentData(), self.line
        )
        by_key = {self.item_key(row): row for row in rows}
        self._updating = True
        self.table.setRowCount(len(self.items))
        for row_index, item in enumerate(self.items):
            display = by_key.get(self.item_key(item), item)
            values = (
                "", item.get("source"), item.get("name"),
                item.get("elevation"), item.get("depth"),
                display.get("_station"), display.get("_offset"),
            )
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(
                    "" if value is None else
                    f"{value:g}" if isinstance(value, float) else str(value)
                )
                if column == 0:
                    table_item.setFlags(
                        table_item.flags()
                        | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    table_item.setCheckState(
                        Qt.CheckState.Checked
                        if item.get("enabled", True)
                        else Qt.CheckState.Unchecked
                    )
                else:
                    table_item.setFlags(
                        table_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                    )
                self.table.setItem(row_index, column, table_item)
        self._updating = False
        self.table.resizeColumnsToContents()
        self.canvas.set_model(
            items=self.items,
            mode=self.mode.currentData(),
            line=self.line,
            terrain=self.terrain,
            horizontal_scale=self.horizontal_scale.value(),
            vertical_scale=self.vertical_scale.value(),
            display={
                key: checkbox.isChecked()
                for key, checkbox in self.display_checks.items()
            },
        )
        missing_elevation = sum(
            number(item.get("elevation")) is None for item in self.items
        )
        self.status.setText(
            f"{len(self.items)} {self.plugin.t('objekti')}"
            + (
                f" · {missing_elevation} "
                + self.plugin.t("objektil puudub absoluutkõrgus")
                if missing_elevation else ""
            )
        )
        self.modelChanged.emit(len(self.items))
        self._map_line_changed()

    def _table_changed(self, item):
        if self._updating or item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.items):
            self.items[row]["enabled"] = (
                item.checkState() == Qt.CheckState.Checked
            )
            self.refresh()
            self.save_project_state()

    def _model_changed(self):
        if self._updating:
            return
        if self.mode.currentData() != "line":
            self.terrain = []
        self.refresh()
        if self.mode.currentData() != "equal":
            self.sample_dem()
        self.save_project_state()

    def _display_changed(self):
        self.refresh()
        self.save_project_state()

    def _map_line_changed(self):
        self.plugin.update_cross_section_map_line(
            self.effective_line(), self.show_map_line.isChecked()
        )

    def reload_rasters(self):
        previous = self.dem_layer.currentData() if self.dem_layer.count() else ""
        self.dem_layer.clear()
        self.dem_layer.addItem(self.plugin.t("DEM puudub"), "")
        for layer in QgsProject.instance().mapLayers().values():
            if (
                isinstance(layer, QgsRasterLayer)
                and layer.providerType().casefold() != "wms"
            ):
                self.dem_layer.addItem(layer.name(), layer.id())
        index = self.dem_layer.findData(previous)
        self.dem_layer.setCurrentIndex(max(0, index))

    def sample_dem(self):
        layer = QgsProject.instance().mapLayer(self.dem_layer.currentData())
        line = self.effective_line()
        if not isinstance(layer, QgsRasterLayer) or len(line) < 2:
            self.terrain = []
            self.refresh()
            return
        length = polyline_length(line)
        if length <= 0:
            return
        count = max(2, min(800, round(length / 10) + 1))
        step = length / (count - 1)
        transform = QgsCoordinateTransform(
            METRIC_CRS, layer.crs(), QgsProject.instance()
        )
        terrain = []
        provider = layer.dataProvider()
        band = min(max(1, self.dem_band.value()), layer.bandCount())
        for index in range(count):
            station = index * step
            point = point_at_station(line, station)
            if not point:
                continue
            try:
                raster_point = transform.transform(
                    QgsPointXY(point[0], point[1])
                )
                value, valid = provider.sample(raster_point, band)
            except Exception:
                valid = False
                value = None
            if valid and number(value) is not None:
                terrain.append((station, float(value)))
        self.terrain = terrain
        self.refresh()
        self.save_project_state()

    def save_project_state(self):
        if self._updating:
            return
        state = {
            "version": 1,
            "name": self.name.text(),
            "mode": self.mode.currentData(),
            "line": self.line,
            "items": self.items,
            "terrain": self.terrain,
            "dem_layer_name": self.dem_layer.currentText(),
            "dem_band": self.dem_band.value(),
            "horizontal_scale": self.horizontal_scale.value(),
            "vertical_scale": self.vertical_scale.value(),
            "display": {
                key: checkbox.isChecked()
                for key, checkbox in self.display_checks.items()
            },
            "show_map_line": self.show_map_line.isChecked(),
            "include_overview": self.include_overview.isChecked(),
        }
        QgsProject.instance().writeEntry(
            STATE_SCOPE,
            STATE_KEY,
            json.dumps(self._json_safe(state), ensure_ascii=False),
        )

    def load_project_state(self):
        payload, found = QgsProject.instance().readEntry(
            STATE_SCOPE, STATE_KEY, ""
        )
        if not found or not payload:
            self.refresh()
            return
        try:
            state = json.loads(str(payload))
        except (TypeError, ValueError):
            self.refresh()
            return
        self._updating = True
        self.name.setText(state.get("name") or self.plugin.t("Koondläbilõige"))
        self.items = list(state.get("items") or [])
        self.line = list(state.get("line") or [])
        self.terrain = [
            tuple(pair) for pair in (state.get("terrain") or [])
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        ]
        index = self.mode.findData(state.get("mode", "line"))
        self.mode.setCurrentIndex(max(0, index))
        self.horizontal_scale.setValue(
            float(state.get("horizontal_scale", 0.12))
        )
        self.vertical_scale.setValue(
            float(state.get("vertical_scale", 4.0))
        )
        for key, checked in (state.get("display") or {}).items():
            if key in self.display_checks:
                self.display_checks[key].setChecked(bool(checked))
        self.show_map_line.setChecked(bool(state.get("show_map_line", True)))
        self.include_overview.setChecked(bool(
            state.get("include_overview", True)
        ))
        self.dem_band.setValue(int(state.get("dem_band", 1)))
        dem_name = state.get("dem_layer_name")
        if dem_name:
            index = self.dem_layer.findText(dem_name)
            if index >= 0:
                self.dem_layer.setCurrentIndex(index)
        self._updating = False
        self.refresh()

    def export(self, kind):
        if not self.items:
            QMessageBox.information(
                self, self.plugin.t("Eksport"),
                self.plugin.t("Koondläbilõikele pole objekte lisatud."),
            )
            return
        extension = f".{kind}"
        path, _ = QFileDialog.getSaveFileName(
            self, self.plugin.t("Eksport"),
            f"{self.name.text() or 'koondlabiloige'}{extension}",
            (
                "Scalable Vector Graphics (*.svg)"
                if kind == "svg" else "PDF (*.pdf)"
            ),
        )
        if not path:
            return
        if not path.casefold().endswith(extension):
            path += extension
        if kind == "svg":
            generator = QSvgGenerator()
            generator.setFileName(path)
            generator.setSize(QSize(1800, 1200))
            generator.setViewBox(QRectF(0, 0, 1800, 1200))
            generator.setTitle(self.name.text())
            painter = QPainter(generator)
            page = QRectF(0, 0, 1800, 1200)
        else:
            writer = QPdfWriter(path)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A3))
            writer.setPageOrientation(QPageLayout.Orientation.Landscape)
            writer.setResolution(150)
            painter = QPainter(writer)
            page = QRectF(0, 0, writer.width(), writer.height())
        try:
            painter.fillRect(page, QColor("white"))
            painter.setPen(QColor("#20252a"))
            painter.setFont(QFont(painter.font().family(), 15, QFont.Weight.Bold))
            painter.drawText(
                QRectF(page.left() + 30, page.top() + 20, page.width() - 60, 36),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.name.text(),
            )
            overview_height = page.height() * 0.25 if self.include_overview.isChecked() else 0
            if overview_height:
                map_rect = QRectF(
                    page.right() - page.width() * 0.34 - 30,
                    page.top() + 65,
                    page.width() * 0.34,
                    overview_height - 20,
                )
                self._draw_overview(painter, map_rect)
            section_top = page.top() + 70 + overview_height
            section_rect = QRectF(
                page.left() + 25, section_top,
                page.width() - 50, page.bottom() - section_top - 25,
            )
            self.canvas.draw_section(
                painter, section_rect, fit=True, show_heading=False
            )
        finally:
            painter.end()
        self.status.setText(
            self.plugin.t("Eksporditud") + f": {path}"
        )

    def _draw_overview(self, painter, rect):
        line = self.effective_line()
        points = [
            (number(item.get("x")), number(item.get("y")))
            for item in self.items
            if number(item.get("x")) is not None
            and number(item.get("y")) is not None
        ]
        coordinates = list(line) + points
        if not coordinates:
            return
        extent = QgsRectangle()
        extent.setMinimal()
        for x, y in coordinates:
            extent.include(QgsPointXY(x, y))
        buffer = max(100.0, max(extent.width(), extent.height()) * 0.18)
        extent.grow(buffer)
        image = QImage(
            max(10, round(rect.width())),
            max(10, round(rect.height())),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(QColor("white"))
        settings = QgsMapSettings()
        settings.setLayers(self.plugin.iface.mapCanvas().layers())
        settings.setDestinationCrs(METRIC_CRS)
        settings.setExtent(extent)
        settings.setOutputSize(image.size())
        map_painter = QPainter(image)
        job = QgsMapRendererCustomPainterJob(settings, map_painter)
        job.start()
        job.waitForFinished()
        map_painter.end()
        painter.drawImage(rect, image)

        def map_point(point):
            x = rect.left() + (
                (point[0] - extent.xMinimum()) / max(1.0, extent.width())
            ) * rect.width()
            y = rect.bottom() - (
                (point[1] - extent.yMinimum()) / max(1.0, extent.height())
            ) * rect.height()
            return x, y

        painter.save()
        painter.setPen(QPen(QColor("#d04432"), 2))
        for first, second in zip(line, line[1:]):
            a, b = map_point(first), map_point(second)
            painter.drawLine(round(a[0]), round(a[1]), round(b[0]), round(b[1]))
        painter.setPen(QPen(QColor("#17242e"), 1))
        painter.setBrush(QColor("#ffd34e"))
        for point in points:
            x, y = map_point(point)
            painter.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#59636b"), 1))
        painter.drawRect(rect)
        painter.restore()

    @staticmethod
    def _json_safe(value):
        return json.loads(json.dumps(
            value, ensure_ascii=False, default=str
        ))


class CrossSectionWindow(QDialog):
    """Resizable, non-modal top-level window for the combined section."""

    visibilityChanged = pyqtSignal(bool)

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.setWindowTitle(plugin.t("Läbilõiked"))
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(1400, 900)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.content = CrossSectionWidget(plugin)
        layout.addWidget(self.content)

    def showEvent(self, event):
        super().showEvent(event)
        self.visibilityChanged.emit(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibilityChanged.emit(False)


class CrossSectionLauncher(QWidget):
    """Compact dock-page launcher for the separate section window."""

    def __init__(self, plugin, window):
        super().__init__()
        self.plugin = plugin
        self.window = window
        layout = QVBoxLayout(self)
        message = QLabel(plugin.t(
            "Koondläbilõige avaneb eraldi aknas, et Qeoloogi põhipaan "
            "jääks kompaktseks."
        ))
        message.setWordWrap(True)
        layout.addWidget(message)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.toggle = QPushButton()
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._toggle_window)
        layout.addWidget(self.toggle)
        layout.addStretch(1)
        window.visibilityChanged.connect(self._window_visibility_changed)
        window.content.modelChanged.connect(self._set_count)
        self._set_count(len(window.content.items))
        self._window_visibility_changed(window.isVisible())

    def _toggle_window(self, visible):
        if visible:
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()
        else:
            self.window.hide()

    def _window_visibility_changed(self, visible):
        self.toggle.blockSignals(True)
        self.toggle.setChecked(bool(visible))
        self.toggle.setText(self.plugin.t(
            "Peida läbilõikeaken" if visible else "Ava läbilõikeaken"
        ))
        self.toggle.blockSignals(False)

    def _set_count(self, count):
        self.status.setText(
            f"{int(count)} {self.plugin.t('objekti')} "
            + self.plugin.t("koondläbilõikel")
        )
