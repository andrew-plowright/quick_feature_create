from quick_feature_create.template.template_functions import *
from typing import Dict, List
from qgis.core import QgsMessageLog, QgsDefaultValue, QgsProject, Qgis
from quick_feature_create.__about__ import __title__
from qgis.PyQt.QtCore import QModelIndex, Qt, QAbstractTableModel, QVariant, QObject
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import QShortcut
from pathlib import Path
import json


class Template(QObject):

    def __init__(self, parent, name: str, shortcut_str: str, map_lyr_name: str, default_values: Dict[str, QgsDefaultValue]):

        super().__init__(parent)

        QgsMessageLog.logMessage(f'Parent of this tempate: {parent.objectName()}', tag=__title__, level=Qgis.Info)

        self.name = name
        self.map_lyr_name = map_lyr_name
        self.default_values = default_values
        self.shortcut_str = shortcut_str
        self.shortcut = QShortcut(QKeySequence(self.shortcut_str), parent)
        self.shortcut.activated.connect(lambda: QgsMessageLog.logMessage(f"Shortcut activated for '{self.name}'", tag=__title__, level=Qgis.Info))

        # Store default values and 'suppression' setting for when template is deactivated
        self.revert_suppress = 0
        self.revert_values = {}

        # Switches
        self.valid = False
        self.active = False

        # Attempt to load layer
        self.map_lyr = None
        self.load_lyr()


    def load_lyr(self):
        map_lyrs = QgsProject().instance().mapLayersByName(self.map_lyr_name)
        if len(map_lyrs) == 1:
            self.map_lyr = map_lyrs[0]
            self.valid = True
            QgsMessageLog.logMessage(f"Loaded layer {self.map_lyr_name}", tag=__title__, level=Qgis.Info)
        elif len(map_lyrs) == 0:
            self.map_lyr = None
            self.valid = False
            QgsMessageLog.logMessage(f"Found no map layers named {self.map_lyr_name}", tag=__title__, level=Qgis.Critical)
        else:
            self.map_lyr = None
            self.valid = False
            QgsMessageLog.logMessage(f"Multiple layers named {self.map_lyr_name}", tag=__title__, level=Qgis.Critical)

    def default_values_to_str(self) -> str:
        vals = self.default_values
        return ', '.join([key + ': ' + vals[key].expression() for key in vals])

    def activate_template(self) -> None:
        if not self.active:
            QgsMessageLog.logMessage(f"Activated template '{self.name}'", tag=__title__, level=Qgis.Info)

            # Get values that will be reverted
            field_names = [field_name for field_name in self.default_values]
            self.revert_values = get_existing_default_definitions(self.map_lyr, field_names)
            self.revert_suppress = get_existing_form_suppress(self.map_lyr)

            # Set default definition and suppress form
            set_default_definitions(self.map_lyr, self.default_values)
            set_form_suppress(self.map_lyr, 1)

            # Set this template as active
            self.active = True

    def deactivate_template(self) -> None:
        if self.active:
            QgsMessageLog.logMessage(f"Deactivated template '{self.name}'", tag=__title__, level=Qgis.Info)

            # Revert default value definitions and form suppression settings
            set_default_definitions(self.map_lyr, self.revert_values)
            set_form_suppress(self.map_lyr, self.revert_suppress)

            # Set this template as inactive
            self.active = False

    def unregister_shortcut(self) -> None:

        self.shortcut.setParent(None)
        self.shortcut.deleteLater()


class TemplateTableModel(QAbstractTableModel):
    header_labels = [
        "Name",
        "Default Values",
        "Shortcut",
        "May Layer Name",
        "Valid",
        "Active",
    ]

    templates = []

    def __init__(self, parent=None, templates: List[Template] = None):
        super().__init__(parent)
        if templates is not None:
            self.templates = templates

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.header_labels[section]
        return super().headerData(section, orientation, role)

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.templates)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.header_labels)

    def data(self, index, role):

        if not index.isValid():
            return QVariant()

        row = index.row()
        column = index.column()
        column_header_label = self.header_labels[column]

        if row >= len(self.templates):
            return QVariant()

        if role == Qt.ItemDataRole.DisplayRole:
            if column_header_label == "Name":
                return self.templates[row].name
            elif column_header_label == "Default Values":
                return self.templates[row].default_values_to_str()
            elif column_header_label == "Shortcut":
                return self.templates[row].shortcut_str
            elif column_header_label == "May Layer Name":
                return self.templates[row].map_lyr_name
            elif column_header_label == "Valid":
                return self.templates[row].valid

        if role == Qt.CheckStateRole:
            if column_header_label == "Active":
                if self.templates[row].active:
                    return Qt.Checked
                else:
                    return Qt.Unchecked

    def flags(self, index):

        if not index.isValid():
            return None

        column_header_label = self.header_labels[index.column()]

        if column_header_label == 'Active':
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
        else:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index, value, role=Qt.EditRole):

        if not index.isValid():
            return None

        column_header_label = self.header_labels[index.column()]

        if column_header_label == 'Active' and role == Qt.CheckStateRole:
            self.toggle_template(self.templates[index.row()])
            # checked = value == Qt.Checked
            # if checked:
            #     self.select_template(self.templates[index.row()])
            # else:
            #     self.deselect_template(self.templates[index.row()])

            return True

    def add_templates(self, templates: List[Template]) -> None:

        row = self.rowCount()

        self.beginInsertRows(QModelIndex(), row, row + len(templates) - 1)

        for template in templates:

            self.templates.append(template)

        self.endInsertRows()

    def remove_template(self, template: Template) -> None:
        try:
            row = self.templates.index(template)

            self.beginRemoveRows(QModelIndex(), row, row)

            template.unregister_shortcut()
            template.deactivate_template()

            self.templates.remove(template)

            self.endRemoveRows()
        except ValueError:
            print(f'Template not found')

    def clear_templates(self):
        if len(self.templates) > 0:

            self.beginRemoveRows(QModelIndex(), 0, self.rowCount() -1)

            for template in self.templates:
                template.unregister_shortcut()
                template.deactivate_template()
            self.templates.clear()

            self.endRemoveRows()

    def print_templates(self) -> None:
        for tp in self.templates:
            print({f"Template: '{tp.name}', Active: {str(tp.active)}"})

    def toggle_template(self, template: Template) -> None:
        if template.active:
            self.deselect_template(template)
        else:
            self.select_template(template)

    def select_template(self, template: Template) -> None:

        col = self.header_labels.index('Active')

        # Deactivate other templates first
        for row in range(len(self.templates)):
            if not self.templates[row] == template:
                self.templates[row].deactivate_template()

        # Activate selected template
        template.activate_template()

        # Update view
        index_start = self.createIndex(0, col)
        index_end = self.createIndex(self.rowCount() - 1, col)
        self.dataChanged.emit(index_start, index_end)

    def deselect_template(self, template: Template) -> None:

        template.deactivate_template()

        # Update view
        row = self.templates.index(template)
        col = self.header_labels.index('Active')
        index = self.createIndex(row, col)
        self.dataChanged.emit(index, index)

    def from_json(self, path: Path):

        with open(path) as f:
            data = json.load(f)

        self.clear_templates()

        templates = []

        for d in data:
            default_values = {key: QgsDefaultValue(f"'{value}'") for key, value in d['default_values'].items()}
            templates.append(Template(parent=self.parent(), name=d['name'], shortcut_str=d['shortcut_str'],
                                      map_lyr_name=d['map_lyr_name'], default_values=default_values))

        self.add_templates(templates)

