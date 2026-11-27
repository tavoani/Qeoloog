"""Preview and export a depth-scaled local lithology column in QGIS."""

import csv
from copy import deepcopy
from datetime import date
from io import StringIO
from math import isfinite
from pathlib import Path
import re

from qgis.PyQt.QtCore import QIODevice, QSaveFile, Qt, QTimer
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .basement_measurements import read_basement_measurements
from .etl_domains import domain_match
from .section_workspace import SectionWorkspaceError


_BASEMENT_EXAMPLE = Path(__file__).with_name('templates') / 'Lisa5-aluskorra-mootenais.xlsx'

_BASEMENT_FIELDS = {
    'density_probe': 'Sonditihedus',
    'density_sample': 'Proovitihedus',
    'magnetic': 'Mag. vastuvõtlikkus',
    'structures': 'Struktuurielemendid',
    'migmatization': 'Migmatiseerumise aste',
}


def _depth_number(text, *, optional=False):
    raw = str(text).strip().replace(',', '.')
    if optional and not raw:
        return None
    number = float(raw)
    if not isfinite(number):
        raise ValueError('Non-finite depth or measurement')
    return number


def read_gamma_csv(path):
    """Read a bounded literal depth/value log; do not interpolate missing rows."""
    with Path(path).open('rb') as stream:
        raw = stream.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError('CSV > 4 MB')
    source = raw.decode('utf-8-sig')
    first = next((line for line in source.splitlines() if line.strip()), '')
    if not first:
        raise ValueError('CSV: depth,value')
    sep = ';' if ';' in first else '\t' if '\t' in first else ','
    reader = csv.DictReader(StringIO(source.lstrip()), delimiter=sep)
    headers = {name.strip().casefold(): name for name in (reader.fieldnames or ())}
    if len(headers) != len(reader.fieldnames or ()):
        raise ValueError('CSV: duplicate columns / korduvad veerud')
    depth = next((headers[key] for key in ('depth', 'depth_m', 'sügavus', 'sygavus') if key in headers), None)
    value = next((headers[key] for key in ('value', 'gamma', 'väärtus', 'vaartus') if key in headers), None)
    if not depth or not value:
        raise ValueError('CSV: depth,value / sügavus;väärtus')
    points = {}
    for row in reader:
        if None in row and any(piece.strip() for piece in row[None]):
            raise ValueError(f'CSV: rida / row {reader.line_num}')
        d = (row.get(depth) or '').strip()
        v = (row.get(value) or '').strip()
        if not d and not v:
            continue
        try:
            depth_m, result = _depth_number(d), _depth_number(v)
            if depth_m < 0 or (depth_m in points and points[depth_m] != result):
                raise ValueError()
        except ValueError as error:
            raise ValueError(f'CSV: rida / row {reader.line_num}') from error
        points[depth_m] = result
        if len(points) > 25_000:
            raise ValueError('CSV: > 25 000')
    if not points:
        raise ValueError('CSV: no measurements / mõõtmised puuduvad')
    return [{'depth': depth_m, 'value': points[depth_m]} for depth_m in sorted(points)]


class LithologyReportDialog(QDialog):
    def __init__(self, plugin, record, parent=None, *, persist_measurements=None, editable=True):
        super().__init__(parent)
        self.plugin, self.record = plugin, record
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(plugin.t('Litotulp'))
        self.resize(1000, 845)
        self._gamma = []
        self._persist_measurements = persist_measurements
        self._measurement_editable = editable
        saved = record.get('basement_measurements')
        self._basement = {
            key: deepcopy(saved[key]) if isinstance(saved, dict) and isinstance(saved.get(key), list) else []
            for key in _BASEMENT_FIELDS
        }
        self._stored_basement = deepcopy(self._basement)
        self._report = None
        self._page = 0
        t = plugin.t
        layout = QVBoxLayout(self)
        primary = QHBoxLayout()
        self.start, self.end = QLineEdit(), QLineEdit()
        for widget, caption in ((self.start, 'Algus (m)'), (self.end, 'Lõpp (m)')):
            label = QLabel(t(caption))
            label.setBuddy(widget)
            primary.addWidget(label)
            widget.setPlaceholderText(t('Automaatne'))
            widget.setMaximumWidth(112)
            primary.addWidget(widget)
        self.scale = QSpinBox()
        self.scale.setRange(10, 20000)
        self.scale.setPrefix('1:')
        self.scale.setValue(self._initial_scale())
        label = QLabel(t('Mõõtkava'))
        label.setBuddy(self.scale)
        primary.addWidget(label)
        primary.addWidget(self.scale)
        self.paper = QComboBox()
        self.paper.addItem('Lisa 5 - ' + self._bi('pealiskord', 'sedimentary cover'), 'lisa5-cover')
        self.paper.addItem('Lisa 5 - ' + self._bi('aluskord', 'basement'), 'lisa5-basement')
        self.paper.addItem('A4 - ' + t('Püstpaigutus'), 'a4-portrait')
        self.paper.addItem('A4 - ' + t('Rõhtpaigutus'), 'a4-landscape')
        self.paper.setCurrentIndex(self._initial_layout())
        primary.addWidget(self.paper)
        primary.addStretch(1)
        layout.addLayout(primary)

        tracks = QHBoxLayout()
        self.samples = QCheckBox(t('Proovid'))
        self.analyses = QCheckBox(t('Analüüsid'))
        self.xrd = QCheckBox('XRD')
        self.colors = QCheckBox(t('Värvid'))
        self.patterns = QCheckBox(t('Mustrid'))
        self.legend = QCheckBox(t('Legend'))
        for checkbox in (self.samples, self.analyses, self.xrd, self.colors, self.patterns, self.legend):
            checkbox.setChecked(True)
            tracks.addWidget(checkbox)
        self.author = QLineEdit()
        self.author.setPlaceholderText(t('Koostaja'))
        self.author.setClearButtonEnabled(True)
        tracks.addWidget(self.author, 1)
        layout.addLayout(tracks)
        tracks = QHBoxLayout()
        add = QPushButton(t('Lisa gammalogi (CSV)…'))
        add.clicked.connect(self.choose_gamma)
        tracks.addWidget(add)
        self.remove_gamma = QPushButton(t('Eemalda gammalogi'))
        self.remove_gamma.clicked.connect(self.clear_gamma)
        self.remove_gamma.setEnabled(False)
        tracks.addWidget(self.remove_gamma)
        self.gamma_unit = QLineEdit()
        self.gamma_unit.setPlaceholderText(t('Ühik'))
        self.gamma_unit.setToolTip(t('Gammalogi mõõtühik, näiteks API, kui see on failis kasutatud ühik.'))
        self.gamma_unit.setMaximumWidth(125)
        self.gamma_unit.setEnabled(False)
        tracks.addWidget(self.gamma_unit)
        tracks.addStretch(1)
        layout.addLayout(tracks)

        self.measurement_panel = QWidget()
        panel_layout = QVBoxLayout(self.measurement_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        self.import_basement = QPushButton(t('Impordi mõõteandmed…'))
        self.import_basement.setObjectName('qeoloogBasementImport')
        self.import_basement.setToolTip(t(
            'CSV, TSV või XLSX. Failis olevad rajad asendavad eelvaates ainult sama liiki rajad.'
        ))
        self.import_basement.clicked.connect(self.choose_basement_measurements)
        actions.addWidget(self.import_basement)
        self.download_basement_example = QPushButton(t('Exceli näidis…'))
        self.download_basement_example.setObjectName('qeoloogBasementExample')
        self.download_basement_example.setToolTip(t('Salvesta kaasasoleva Exceli näidisfaili koopia.'))
        self.download_basement_example.clicked.connect(self.save_basement_example)
        actions.addWidget(self.download_basement_example)
        self.clear_basement = QPushButton(t('Eemalda mõõteandmed'))
        self.clear_basement.clicked.connect(self.clear_basement_measurements)
        actions.addWidget(self.clear_basement)
        self.save_basement = QPushButton(t('Salvesta objekti juurde'))
        self.save_basement.clicked.connect(self.save_basement_measurements)
        self.save_basement.setVisible(persist_measurements is not None)
        actions.addWidget(self.save_basement)
        actions.addStretch(1)
        panel_layout.addLayout(actions)
        toggles = QHBoxLayout()
        self.basement_tracks = {}
        for key, caption in _BASEMENT_FIELDS.items():
            checkbox = QCheckBox(t(caption))
            checkbox.setChecked(True)
            if key == 'migmatization':
                checkbox.setToolTip(t('Kuvatakse kivimitulbas, kui Mustrid on sisse lülitatud.'))
            checkbox.toggled.connect(self._schedule_refresh)
            self.basement_tracks[key] = checkbox
            toggles.addWidget(checkbox)
        toggles.addStretch(1)
        panel_layout.addLayout(toggles)
        self.measurement_status = QLabel()
        self.measurement_status.setWordWrap(True)
        self.measurement_status.setTextFormat(Qt.TextFormat.PlainText)
        panel_layout.addWidget(self.measurement_status)
        layout.addWidget(self.measurement_panel)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.paper_preview = QLabel()
        self.paper_preview.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.paper_preview)
        self.preview_scroll = scroll
        layout.addWidget(scroll, 1)

        actions = QHBoxLayout()
        self.previous = QPushButton(t('Eelmine leht'))
        self.previous.clicked.connect(lambda: self._show_page(self._page - 1))
        self.next = QPushButton(t('Järgmine leht'))
        self.next.clicked.connect(lambda: self._show_page(self._page + 1))
        actions.addWidget(self.previous)
        self.page_label = QLabel()
        actions.addWidget(self.page_label)
        actions.addWidget(self.next)
        actions.addStretch(1)
        self.pdf = QPushButton(t('Ekspordi PDF…'))
        self.svg = QPushButton(t('Ekspordi SVG…'))
        self.pdf.clicked.connect(lambda: self.export('pdf'))
        self.svg.clicked.connect(lambda: self.export('svg'))
        actions.addWidget(self.pdf)
        actions.addWidget(self.svg)
        layout.addLayout(actions)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(180)
        self._render_timer.timeout.connect(self.refresh_report)
        for control in (self.start, self.end, self.gamma_unit, self.author):
            control.textChanged.connect(self._schedule_refresh)
        for control in (self.samples, self.analyses, self.xrd, self.colors, self.patterns, self.legend):
            control.toggled.connect(self._schedule_refresh)
        self.scale.valueChanged.connect(self._schedule_refresh)
        self.paper.currentIndexChanged.connect(self._sync_basement_controls)
        self.paper.currentIndexChanged.connect(self._schedule_refresh)
        self._sync_basement_controls()
        self.refresh_report()

    def _initial_scale(self):
        depths = []
        for row in self.record.get('units') or ():
            try:
                depths.append(_depth_number(row.get('z_suht_alumine', '')))
            except (TypeError, ValueError):
                pass
        attrs = self.record.get('attributes') or {}
        if self._initial_layout() == 1:
            tops = []
            for row in self.record.get('units') or ():
                try:
                    tops.append(_depth_number(row.get('z_suht_ylemine', '')))
                except (AttributeError, TypeError, ValueError):
                    continue
            if tops and depths and (span := max(depths) - min(tops)) > 0:
                return 100 if span <= 30 else 200 if span <= 110 else 500 if span <= 320 else 1000
        for key in ('pikkus', 'vertikaalne_ulatus'):
            try:
                depths.append(_depth_number(attrs.get(key, '')))
            except (TypeError, ValueError):
                pass
        depth = max(depths, default=0)
        return 100 if depth <= 30 else 200 if depth <= 110 else 500 if depth <= 320 else 1000

    def _bi(self, et, en):
        return en if getattr(self.plugin, 'language', 'et') == 'en' else et

    def _initial_layout(self):
        attrs = self.record.get('attributes') or {}
        if self.record.get('axis') == 'height' or attrs.get('axis') == 'height':
            return 2
        units = self.record.get('units') or ()
        kinds = {domain_match('geol_yksus_mall', 'yksus_kood', row.get('yksus_kood'))
                 for row in units if isinstance(row, dict)}
        kinds.discard(None)
        return 1 if kinds and all(choice[0] == 3 for choice in kinds) else 0

    def _schedule_refresh(self, *_):
        if hasattr(self, '_render_timer'):
            self._render_timer.start()

    def _sync_basement_controls(self, *_):
        self.measurement_panel.setVisible(self._measurement_editable and self.paper.currentData() == 'lisa5-basement')
        self.clear_basement.setEnabled(any(self._basement.values()))
        dirty = self._basement != self._stored_basement
        self.save_basement.setEnabled(self._persist_measurements is not None and dirty)
        for key, check in self.basement_tracks.items():
            count = sum(1 for row in self._basement[key]
                        if isinstance(row, (list, tuple)) and len(row) > 1 and row[1] is not None)
            check.setEnabled(bool(count))
            check.setText(f"{self.plugin.t(_BASEMENT_FIELDS[key])} ({count})")
        if dirty:
            label = ('Mõõteandmed on eelvaates, kuid objekti juurde salvestamata.'
                     if self._persist_measurements else 'Mõõteandmed kehtivad ainult selles eelvaates.')
        elif any(self._basement.values()):
            label = 'Mõõteandmed on salvestatud kohaliku objekti juurde.'
        else:
            label = 'Vali mõõteandmete fail. Excelis kasuta lehte „Mõõteandmed”.'
        self.measurement_status.setText(self.plugin.t(label))

    def choose_basement_measurements(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.plugin.t('Impordi mõõteandmed…'), '',
            'CSV / TSV / XLSX (*.csv *.tsv *.xlsx)',
        )
        if path:
            self.load_basement_measurements(path)

    def save_basement_example(self):
        t = self.plugin.t
        name, _ = QFileDialog.getSaveFileName(
            self, t('Salvesta Exceli näidis'), _BASEMENT_EXAMPLE.name, 'Excel (*.xlsx)',
        )
        if not name:
            return False
        destination = Path(name)
        if destination.suffix.casefold() != '.xlsx':
            destination = destination.with_name(destination.name + '.xlsx')
            # The native dialog may only have checked the name before the suffix was added.
            if destination.exists() and QMessageBox.question(
                self, t('Salvesta Exceli näidis'), t('Kas asendada olemasolev Exceli fail?'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return False
        try:
            data = _BASEMENT_EXAMPLE.read_bytes()
            output = QSaveFile(str(destination))
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            if output.write(data) != len(data):
                error = output.errorString()
                output.cancelWriting()
                raise OSError(error)
            if not output.commit():
                raise OSError(output.errorString())
        except OSError as error:
            self.measurement_status.setText(f"{t('Exceli näidist ei saanud salvestada')}: {error}")
            return False
        self.measurement_status.setText(f"{t('Exceli näidis salvestati')}: {destination}")
        return True

    def load_basement_measurements(self, path):
        if not self._measurement_editable:
            return False
        try:
            imported = read_basement_measurements(path)
        except (OSError, ValueError) as error:
            self.measurement_status.setText(
                f"{self.plugin.t('Mõõteandmete import ebaõnnestus')}: {error}"
            )
            return False
        for key, points in imported.items():
            if key in self._basement and points:
                self._basement[key] = points
                self.basement_tracks[key].setChecked(True)
        self._sync_basement_controls()
        self.refresh_report()
        return True

    def clear_basement_measurements(self):
        if self._measurement_editable:
            self._basement = {key: [] for key in self._basement}
            self._sync_basement_controls()
            self.refresh_report()

    def save_basement_measurements(self):
        if not self._measurement_editable or self._persist_measurements is None:
            return False
        if self._basement == self._stored_basement:
            return True
        try:
            self.record = self._persist_measurements(self._basement)
        except (OSError, SectionWorkspaceError, ValueError) as error:
            self.measurement_status.setText(
                f"{self.plugin.t('Mõõteandmeid ei saanud salvestada')}: {error}"
            )
            return False
        self._stored_basement = deepcopy(self._basement)
        self._sync_basement_controls()
        return True

    def choose_gamma(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.plugin.t('Lisa gammalogi (CSV)…'), '', 'CSV (*.csv *.tsv *.txt)',
        )
        if path:
            try:
                self._gamma = read_gamma_csv(path)
            except (OSError, UnicodeError, ValueError, csv.Error) as error:
                self.status.setText(f"{self.plugin.t('Gammalogi lugemine ebaõnnestus')}: {error}")
                return
            self.remove_gamma.setEnabled(True)
            self.gamma_unit.setEnabled(True)
            self.refresh_report()

    def clear_gamma(self):
        self._gamma = []
        self.remove_gamma.setEnabled(False)
        self.gamma_unit.setEnabled(False)
        self.refresh_report()

    def refresh_report(self):
        from .lithology_report import build_lithology_report

        self._render_timer.stop()
        try:
            start = _depth_number(self.start.text(), optional=True)
            end = _depth_number(self.end.text(), optional=True)
            if (start is not None and start < 0) or (end is not None and end <= (start or 0)):
                raise ValueError(self.plugin.t('Lõppsügavus peab olema algsügavusest suurem.'))
            layout = self.paper.currentData()
            today = date.today()
            self._report = build_lithology_report(
                self.record, start=start, end=end, scale=self.scale.value(),
                language=getattr(self.plugin, 'language', 'et'),
                options={'landscape': layout == 'a4-landscape', 'layout': layout,
                         'samples': self.samples.isChecked(), 'measurements': self.analyses.isChecked(),
                         'xrd': self.xrd.isChecked(),
                         'colors': self.colors.isChecked(), 'patterns': self.patterns.isChecked(),
                         'legend': self.legend.isChecked(), 'author': self.author.text().strip(),
                         'gamma': self._gamma, 'gamma_unit': self.gamma_unit.text().strip(),
                         'basement_measurements': {
                             key: self._basement[key] for key, box in self.basement_tracks.items()
                             if box.isChecked()
                         } if layout == 'lisa5-basement' else {},
                         'report_date': self._bi(today.strftime('%d.%m.%Y'), today.isoformat())
                         if layout.startswith('lisa5-') else ''},
            )
            self._show_page(self._page)
        except (ValueError, RuntimeError, TypeError) as error:
            self._report = None
            self.paper_preview.clear()
            self.page_label.clear()
            self.status.setText(f"{self.plugin.t('Litotulpa ei saanud koostada')}: {error}")
            for button in (self.pdf, self.svg, self.previous, self.next):
                button.setEnabled(False)
            return
        gamma = f" · {self.plugin.t('Gammalogi')}: {len(self._gamma)}" if self._gamma else ''
        self.status.setText(f"{self.plugin.t('Trükimõõtkava')}: 1:{self.scale.value()}{gamma}")
        self.pdf.setEnabled(True)
        self.svg.setEnabled(True)

    def _show_page(self, index):
        if self._report is None:
            return
        self._page = min(max(0, index), self._report.page_count - 1)
        image = self._report.page_image(self._page, dpi=82 if self._report.custom_paper else 100)
        self.paper_preview.setPixmap(QPixmap.fromImage(image))
        self.preview_scroll.verticalScrollBar().setValue(0)
        self.page_label.setText(f'{self._page + 1} / {self._report.page_count}')
        self.previous.setEnabled(self._page > 0)
        self.next.setEnabled(self._page + 1 < self._report.page_count)

    def export(self, fmt):
        from .lithology_report import export_lithology_pdf, export_lithology_svg

        if self._render_timer.isActive():
            self.refresh_report()
        if not self._report:
            return
        attrs = self.record.get('attributes') or {}
        name = re.sub(r'[^\w.-]+', '_', str(attrs.get('nimi') or attrs.get('ID_ajutine') or 'litotulp'))[:70]
        filename, _ = QFileDialog.getSaveFileName(
            self, self.plugin.t('Salvesta litotulp'), f'{name}.{fmt}', f'{fmt.upper()} (*.{fmt})',
        )
        if not filename:
            return
        if Path(filename).suffix.lower() != '.' + fmt:
            filename += '.' + fmt
        exporter = export_lithology_pdf if fmt == 'pdf' else export_lithology_svg
        try:
            exporter(self._report, filename)
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(f"{self.plugin.t('Litotulpa ei saanud salvestada')}: {error}")
        else:
            self.status.setText(f"{self.plugin.t('Litotulp salvestati')}: {filename}")
