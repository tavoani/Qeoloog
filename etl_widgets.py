"""Explicit preview/commit controls for local field and laboratory ETL data."""

from copy import deepcopy
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from .etl_preflight import review_etl
from .etl_workbooks import EtlWorkbookError, export_etl, import_etl
from .local_objects import LocalObjectStore, local_object_name
from .section_workspace import SectionWorkspaceError


def _workspace(plugin):
    return getattr(getattr(getattr(plugin, 'dock', None), 'cross_sections', None), 'workspace', None)


def _workspace_key(workspace):
    return (workspace.workspace_id, workspace.folder) if workspace is not None else None


def _report(plugin, widget, message, *, warning=False):
    box = QMessageBox(widget)
    box.setWindowTitle('Qeoloog')
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(str(message))
    box.setIcon(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information)
    box.exec()


def _editor(view):
    view.setReadOnly(True)
    view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)


class EtlImportWidget(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.preview = None
        self.workspace_id = None
        self.expected = {}
        t = plugin.t
        layout = QVBoxLayout(self)
        info = QLabel(t('Vali koos ETL6 (objektid), ETL10 (geoloogia), ETL7 (proovid) ja/või ETL8 (analüüsid). ETL7/8 saab lisada ka olemasolevatele kohalikele objektidele, kui ID-d kattuvad üheselt.'))
        info.setWordWrap(True)
        layout.addWidget(info)
        controls = QHBoxLayout()
        choose = QPushButton(t('Vali ETL-failid…'))
        choose.clicked.connect(self.choose_files)
        controls.addWidget(choose)
        self.commit_button = QPushButton(t('Salvesta tööruumi'))
        self.commit_button.clicked.connect(self.commit)
        controls.addWidget(self.commit_button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        _editor(self.log)
        layout.addWidget(self.log, 1)
        self.workspace_changed()

    def workspace_changed(self):
        self.preview = None
        self.workspace_id = None
        self.expected = {}
        self.commit_button.setEnabled(False)
        self.log.clear()
        self.status.setText(self.plugin.t(
            'Vali failid eelvaateks.' if _workspace(self.plugin)
            else 'Salvestamiseks loo või ava tööruum paanis Kohalikud andmed.'
        ))

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.plugin.t('Vali ETL-failid…'), '', 'Excel (*.xlsx)',
        )
        if paths:
            self.preview_files(paths)

    def preview_files(self, paths):
        t = self.plugin.t
        self.workspace_changed()
        workspace = _workspace(self.plugin)
        try:
            existing = LocalObjectStore(workspace).list_objects() if workspace else []
            baseline = {record['id']: deepcopy(record) for record in existing}
            result = import_etl(paths, existing_records=existing)
        except (EtlWorkbookError, OSError, ValueError, SectionWorkspaceError) as error:
            self.status.setText(f"{t('Import ebaõnnestus')}: {error}")
            return False
        self.preview = result
        self.workspace_id = _workspace_key(workspace)
        self.expected = {record['id']: baseline[record['id']] for record in result.updates}
        unlinked = sum(len(rows) for rows in result.unlinked.values())
        unit_count = sum(len(item.get('units') or ()) for item in result.records)
        def additions(sheet):
            return (sum(len(item.get('related', {}).get(sheet, ())) for item in result.records)
                    + sum(len(item.get('related', {}).get(sheet, ()))
                          - len(self.expected[item['id']].get('related', {}).get(sheet, ()))
                          for item in result.updates))
        self.status.setText(
            f"{t('Objekte')}: {len(result.records)} · {t('Geoloogilised üksused')}: {unit_count}"
            f" · {t('Proovid')}: {additions('mall_proov')} · {t('Analüüsid')}: {additions('mall_mootmine')}"
            f" · {t('Sidumata ridu')}: {unlinked}"
        )
        lines = [str(Path(p).name) for p in paths]
        if not workspace:
            lines.append(t('Salvestamiseks loo või ava tööruum paanis Kohalikud andmed.'))
        if unlinked:
            lines.append(t('Sidumata read tuleb failis parandada. Import ei jäta ridu vaikides välja.'))
        lines.extend(result.warnings)
        lines.extend(f"{local_object_name(item)} · {len(item.get('units') or ())}" for item in result.records)
        if result.updates:
            lines.append(f"{t('Laboriandmete täiendused olemasolevatele objektidele')}: {len(result.updates)}")
            lines.extend(local_object_name(item) for item in result.updates)
        self.log.setPlainText('\n'.join(lines))
        self.commit_button.setEnabled(bool(workspace and (result.records or result.updates) and not unlinked))
        return not bool(unlinked)

    def commit(self):
        workspace = _workspace(self.plugin)
        result = self.preview
        if not (workspace and result and self.workspace_id == _workspace_key(workspace) and
                not any(result.unlinked.values()) and self.commit_button.isEnabled()):
            return False
        try:
            saved = LocalObjectStore(workspace).commit_etl(result.records, result.updates, self.expected)
        except (SectionWorkspaceError, OSError, ValueError) as error:
            self.log.appendPlainText(f"{self.plugin.t('Import ebaõnnestus')}: {error}")
            return False
        self.preview = None
        self.expected = {}
        self.commit_button.setEnabled(False)
        self.status.setText(f"{self.plugin.t('Imporditi kohalikke objekte')}: {len(saved)}")
        if hasattr(self.plugin, 'local_objects_changed'):
            self.plugin.local_objects_changed()
        return True


class EtlPreflightDialog(QDialog):
    def __init__(self, plugin, report, object_count, parent=None):
        super().__init__(parent)
        t = plugin.t
        self.report = report
        self.setObjectName('qeoloogEtlPreflight')
        self.setWindowTitle(t('Kontrolli ETL-eksporti'))
        self.resize(740, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t('Kontrollitud objekte: {count}').format(count=object_count)))
        message = (
            'Paranda vead või eemalda vigased objektid ekspordivalikust. Faile ei looda.'
            if report.errors else
            'Hoiatused ei muuda andmeid. Selle valiku saad eksportida mustandina.'
            if report.warnings else
            'Qeoloogi kontroll ei leidnud probleeme. See ei kinnita faili vastuvõttu EGT-laaduris.'
        )
        note = QLabel(t(message))
        note.setWordWrap(True)
        layout.addWidget(note)
        if report.errors or report.warnings:
            tabs = QTabWidget()
            for name, label, findings in (
                ('errors', 'Vead', report.errors),
                ('warnings', 'Hoiatused', report.warnings),
            ):
                details = QPlainTextEdit('\n'.join(map(str, findings)))
                details.setObjectName('qeoloogEtlPreflight_' + name)
                _editor(details)
                tabs.addTab(details, f'{t(label)} ({len(findings)})')
            if not report.errors:
                tabs.setCurrentIndex(1)
            layout.addWidget(tabs, 1)
        else:
            layout.addStretch()
            self.resize(610, 200)
        buttons = QDialogButtonBox()
        back = buttons.addButton(t('Tagasi objektide valikusse'), QDialogButtonBox.ButtonRole.RejectRole)
        back.clicked.connect(self.reject)
        self.proceed = None
        if not report.errors:
            label = 'Ekspordi mustand…' if report.warnings else 'Vali ekspordikaust…'
            self.proceed = buttons.addButton(t(label), QDialogButtonBox.ButtonRole.AcceptRole)
            self.proceed.setObjectName('qeoloogEtlPreflightProceed')
            self.proceed.clicked.connect(self.accept)
        layout.addWidget(buttons)

    def accept(self):
        if not self.report.errors:
            super().accept()


class EtlExportBox(QGroupBox):
    def __init__(self, plugin):
        super().__init__(plugin.t('Kohalike andmete ETL-eksport'))
        self.plugin = plugin
        layout = QVBoxLayout(self)
        note = QLabel(plugin.t('ETL6/10: objektid ja geoloogia. Lisa soovi korral ETL7/8 proovid ja analüüsid. Väljundit ei kinnitata EGT-laaduris.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        button = QPushButton(plugin.t('Vali objektid ja ekspordi Excelisse…'))
        button.clicked.connect(self._select_objects)
        layout.addWidget(button)

    def _select_objects(self):
        t = self.plugin.t
        workspace = _workspace(self.plugin)
        try:
            records = LocalObjectStore(workspace).list_objects() if workspace else []
        except (SectionWorkspaceError, OSError) as error:
            _report(self.plugin, self, error, warning=True)
            return
        if not records:
            _report(self.plugin, self, t('Aktiivses tööruumis pole kohalikke objekte.'))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.title())
        dialog.resize(560, 490)
        layout = QVBoxLayout(dialog)
        choices = QListWidget()
        for obj in records:
            item = QListWidgetItem(local_object_name(obj), choices)
            item.setData(Qt.ItemDataRole.UserRole, obj['id'])
            item.setCheckState(Qt.CheckState.Checked)
        layout.addWidget(choices)
        buttons_row = QHBoxLayout()
        for label, state in (('Vali kõik', Qt.CheckState.Checked), ('Tühjenda valik', Qt.CheckState.Unchecked)):
            button = QPushButton(t(label))
            button.clicked.connect(lambda _checked=False, s=state: [choices.item(i).setCheckState(s) for i in range(choices.count())])
            buttons_row.addWidget(button)
        layout.addLayout(buttons_row)
        saved_note = QLabel(t('Kontrollitakse tööruumi salvestatud andmeid.'))
        saved_note.setWordWrap(True)
        layout.addWidget(saved_note)
        lab = QCheckBox(t('Lisa proovid ja analüüsid (ETL7/ETL8)'))
        lab.setChecked(any(any(k.startswith('mall_') and rows for k, rows in obj.get('related', {}).items())
                           for obj in records))
        layout.addWidget(lab)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        confirm = buttons.button(QDialogButtonBox.StandardButton.Ok)
        confirm.setText(t('Kontrolli valikut'))
        confirm.setObjectName('qeoloogEtlCheckSelection')

        def check_selection():
            confirm.setEnabled(any(
                choices.item(i).checkState() == Qt.CheckState.Checked for i in range(choices.count())
            ))

        choices.itemChanged.connect(lambda _item: check_selection())
        check_selection()
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        try:
            while dialog.exec() == QDialog.DialogCode.Accepted:
                selected = {choices.item(i).data(Qt.ItemDataRole.UserRole) for i in range(choices.count())
                            if choices.item(i).checkState() == Qt.CheckState.Checked}
                export = [obj for obj in records if obj['id'] in selected]
                if not export:
                    continue
                with_lab = lab.isChecked()
                try:
                    report = review_etl(export, lab=with_lab)
                except (EtlWorkbookError, OSError, ValueError) as error:
                    _report(self.plugin, self, error, warning=True)
                    return
                review = EtlPreflightDialog(self.plugin, report, len(export), self)
                try:
                    if review.exec() == QDialog.DialogCode.Accepted and not report.errors:
                        break
                finally:
                    review.deleteLater()
            else:
                return
        finally:
            dialog.deleteLater()
        path = QFileDialog.getExistingDirectory(self, t('Vali ETL-ekspordi kaust'))
        if not path:
            return
        try:
            files = export_etl(path, export, lab=with_lab)
        except (EtlWorkbookError, OSError, ValueError) as error:
            _report(self.plugin, self, error, warning=True)
            return
        _report(self.plugin, self, f"{t('Eksporditud failid')}:\n" + '\n'.join(map(str, files)))

