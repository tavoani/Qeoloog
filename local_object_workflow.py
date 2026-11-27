"""Controller for local objects. Never dispatches remote writes."""

from copy import deepcopy

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox

from .local_objects import LocalObjectConflict, LocalObjectStore
from .local_object_sources import local_cross_section, local_object_from_source, public_object_ref
from .section_workspace import SectionWorkspaceError


class LocalObjectWorkflowMixin:
    def _local_object_store(self):
        sections = getattr(getattr(self, 'dock', None), 'cross_sections', None)
        workspace = getattr(sections, 'workspace', None)
        return LocalObjectStore(workspace) if workspace is not None else None

    def find_local_object(self, ref):
        store = self._local_object_store()
        if store and ref:
            try:
                return store.find_source(ref)
            except (OSError, SectionWorkspaceError) as error:
                self.warning(str(error))
        return None

    def load_local_object(self, identifier):
        store = self._local_object_store()
        if store and identifier:
            try:
                return store.load(identifier)
            except (OSError, SectionWorkspaceError):
                return None
        return None

    def local_workspace_changed(self):
        dock = getattr(self, 'dock', None)
        if not dock:
            return
        importer = getattr(dock, 'etl_import', None)
        if importer:
            importer.workspace_changed()
        self.local_objects_changed()

    def local_objects_changed(self, record=None):
        dock = getattr(self, 'dock', None)
        if not dock:
            return
        if getattr(dock, 'local_objects', None):
            dock.local_objects.reload(select_id=(record or {}).get('id'))
        if getattr(dock, 'details', None):
            dock.details.refresh_local_detail_match()

    def open_local_object_list(self, identifier=None, *, edit=False):
        if not self.dock:
            return
        widget = self.dock.local_objects
        if identifier:
            widget.search.clear()
        widget.reload(select_id=identifier)
        self.dock.tabs.setCurrentWidget(widget)
        self.dock.show()
        self.dock.raise_()
        if edit and identifier:
            widget.edit_selected()

    def show_local_object(self, record):
        if not self.dock or not record:
            return
        # In-flight live requests must not be able to switch this selection.
        self._detail_token += 1
        self.dock.show_details()
        self.dock.details.show_standalone_local_detail(record)

    def _confirm_local_copy(self, text):
        box = QMessageBox(self.dock)
        box.setWindowTitle(self.t('Kopeeri kohalikuks'))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Yes

    def copy_current_local_object(self):
        if not self.dock:
            return None
        details = self.dock.details
        attrs = details._current_detail_attributes
        role = details._current_detail_role
        ref = public_object_ref(role, attrs)
        if not ref:
            return None
        store = self._local_object_store()
        if not store:
            self.open_local_object_list()
            self.message(self.t('Loo või ava tööruum. Seejärel saad valitud objekti kohalikuks kopeerida.'))
            return None
        existing = self.find_local_object(ref)
        if existing:
            self.open_local_object_list(existing['id'])
            return existing
        profile_status = details._local_profile_status
        if profile_status == 'pending':
            self.message(self.t('Oota, kuni lähteobjekti läbilõige on laaditud.'))
            return None
        if profile_status == 'failed' and not self._confirm_local_copy(self.t(
            'Lähteobjekti läbilõige ei laadinud. Kas kopeerida ainult üldandmed?'
        )):
            return None
        record = local_object_from_source(details._current_detail_name, role, attrs,
                                          details._egt_profile_units,
                                          profile_status=profile_status,
                                          profile_source=getattr(details, '_local_profile_source', ''))
        if not record:
            return None
        if not record['units'] and profile_status == 'loaded' and not self._confirm_local_copy(self.t(
            'Lähteobjekti vaates pole geoloogilisi üksusi. Kas kopeerida ainult üldandmed?'
        )):
            return None
        if profile_status == 'failed' or not record['units']:
            record['provenance']['profile_status'] = 'incomplete' if profile_status == 'failed' else 'empty'
        try:
            saved = store.save(record)
        except (OSError, SectionWorkspaceError, ValueError) as error:
            self.warning(str(error))
            return None
        self.local_objects_changed(saved)
        self.open_local_object_list(saved['id'])
        return saved

    def add_local_object_to_section(self, record):
        if self.dock and record:
            self.dock.cross_sections.add_snapshot(local_cross_section(record))

    def open_local_lithology_report(self, record, *, editable=True):
        if not record or not self.dock:
            return None
        from .lithology_report_ui import LithologyReportDialog

        store = self._local_object_store() if editable and record.get('id') else None
        baseline = deepcopy(record) if store is not None else None

        def persist_measurements(measurements):
            nonlocal baseline
            active = self._local_object_store()
            if (active is None or active.workspace.folder != store.workspace.folder
                    or active.workspace.workspace_id != store.workspace.workspace_id):
                raise SectionWorkspaceError(self.t('Tööruum on vahetunud. Ava litotulp uuesti.'))
            revised = deepcopy(baseline)
            if any(measurements.values()):
                revised['basement_measurements'] = deepcopy(measurements)
            else:
                revised.pop('basement_measurements', None)
            try:
                saved = store.save_if_unchanged(revised, baseline)
            except LocalObjectConflict as error:
                raise SectionWorkspaceError(self.t(
                    'Objekt on vahepeal muutunud. Ava litotulp uuesti; salvestatud andmeid ei kirjutatud üle.'
                )) from error
            baseline = deepcopy(saved)
            self.local_objects_changed(saved)
            return saved

        dialog = LithologyReportDialog(
            self, record, self.dock, editable=editable,
            persist_measurements=persist_measurements if store is not None else None,
        )
        dialog.show()
        dialog.raise_()
        return dialog
