"""
Module for globally searching all UI Scripts for attributes, values or pairs.
"""
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Copyright (C) 2025 Luke Horwell <code@horwell.me>
#

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QAbstractScrollArea, QDialog, QHBoxLayout,
                             QLineEdit, QMainWindow, QToolButton, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout)

from s2ui.bridge import get_s2ui_element_id
from s2ui.widgets import iterate_children
from sims2patcher import uiscript


class GlobalSearchDialog(QDialog):
    """
    Dialog to search all packages for an attribute, value or pair.
    """
    def __init__(self, parent: QMainWindow, uiscripts_tree: QTreeWidget, elements_tree: QTreeWidget, attributes_tree: QTreeWidget):
        super().__init__(parent)
        self.main_window = parent
        self.uiscripts_tree = uiscripts_tree
        self.elements_tree = elements_tree
        self.attributes_tree = attributes_tree

        self.setMinimumWidth(400)
        self.setMinimumHeight(200)
        self.resize(900, 400)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(False)
        self.setWindowTitle("Find References")

        self.dialog_layout = QVBoxLayout()
        self.setLayout(self.dialog_layout)

        self.search_layout = QHBoxLayout()
        self.search_box_attrib = QLineEdit()
        self.search_box_attrib.setPlaceholderText("Find attribute...")
        self.search_box_attrib.setToolTip("Enter the attribute name to find.")
        self.search_box_attrib.setClearButtonEnabled(True)
        self.search_box_attrib.textChanged.connect(self.validate_input)
        self.search_box_attrib.returnPressed.connect(self.search)

        self.search_box_value = QLineEdit()
        self.search_box_value.setPlaceholderText("Find value...")
        self.search_box_value.setToolTip("Enter the value of the attribute to find. If no attribute is specified, all attributes will be searched.")
        self.search_box_value.setClearButtonEnabled(True)
        self.search_box_value.textChanged.connect(self.validate_input)
        self.search_box_value.returnPressed.connect(self.search)

        self.search_btn = QToolButton()
        self.search_btn.setText("Search")
        self.search_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.search_btn.setIcon(QIcon.fromTheme("edit-find"))
        self.search_btn.clicked.connect(self.search)

        self.search_layout.addWidget(self.search_box_attrib)
        self.search_layout.addWidget(self.search_box_value)
        self.search_layout.addWidget(self.search_btn)
        self.dialog_layout.addLayout(self.search_layout)

        # Results tree
        # QTreeWidgetItem data columns:
        #   0: QTreeWidgetItem: UI Script TreeWidget item
        #   1: str: S2UI Element ID
        self.results = QTreeWidget()
        self.results.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.results.setHeaderLabels(["Attribute", "Value", "Group ID", "Instance ID", "Package"])
        self.results.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.results.setRootIsDecorated(False)
        self.results.setColumnWidth(0, 200)
        self.results.setColumnWidth(1, 200)
        self.results.setSortingEnabled(True)
        self.results.itemClicked.connect(self.open_result)
        self.dialog_layout.addWidget(self.results)

        self.validate_input()

    def validate_input(self):
        """
        Set the search button state depending on the input boxes.
        """
        attrib = self.search_box_attrib.text()
        value = self.search_box_value.text()
        self.search_btn.setEnabled(bool(attrib or value))

    def _add_result(self, uiscript_item: QTreeWidgetItem, element: uiscript.UIScriptElement, key: str, value: str, found_attrib: bool, found_value: bool):
        """
        Add a search result. Clicking the item will jump to that particular item.
        """
        item = QTreeWidgetItem()
        item.setText(0, key)
        item.setText(1, value)
        item.setText(2, uiscript_item.text(0))
        item.setText(3, uiscript_item.text(1))

        item.setText(4, f"{uiscript_item.text(3)} ({uiscript_item.text(4)})")
        item.setToolTip(4, f"Found in games:\n{uiscript_item.toolTip(3)}\n\nFound in packages:\n{uiscript_item.toolTip(4)}")

        item.setData(0, Qt.ItemDataRole.UserRole, uiscript_item)
        item.setData(1, Qt.ItemDataRole.UserRole, get_s2ui_element_id(element))

        if found_attrib:
            item.setBackground(0, Qt.GlobalColor.darkGreen)
        if found_value:
            item.setBackground(1, Qt.GlobalColor.darkGreen)

        self.results.addTopLevelItem(item)

    def search(self):
        """
        Search all packages for the given criteria.
        """
        self.results.clear()

        text_attrib = self.search_box_attrib.text().lower()
        text_value = self.search_box_value.text().lower()

        tree_root = self.uiscripts_tree.invisibleRootItem()
        if not tree_root:
            return

        for item in iterate_children(tree_root):
            if not item:
                continue

            root: uiscript.UIScriptRoot = item.data(1, Qt.ItemDataRole.UserRole)
            if not item or not root:
                continue

            for element in root.get_all_elements():
                assert isinstance(element, uiscript.UIScriptElement)

                for key, values in element.attributes.items():
                    if isinstance(values, str):
                        values = [values]

                    for value in values:
                        found_attrib = False
                        found_value = False

                        if text_attrib and text_attrib in key.lower():
                            found_attrib = True

                        if text_value and text_value in value.lower():
                            found_value = True

                        if text_attrib and text_value and not all([found_attrib, found_value]):
                            continue

                        if found_attrib or found_value:
                            self._add_result(item, element, key, value, found_attrib, found_value)

        if not self.results.topLevelItemCount():
            item = QTreeWidgetItem()
            item.setText(0, "No results found.")
            item.setDisabled(True)
            self.results.addTopLevelItem(item)

    def open_result(self):
        """
        User clicks on an item in the search results.
        Open the associated UI script and jump to the element.
        """
        item = self.results.currentItem()
        if not item:
            return

        uiscript_item: QTreeWidgetItem = item.data(0, Qt.ItemDataRole.UserRole)
        element_id = item.data(1, Qt.ItemDataRole.UserRole)
        attribute_name = item.text(0)
        if not uiscript_item or not element_id:
            return

        self.uiscripts_tree.setCurrentItem(uiscript_item)
        self.uiscripts_tree.scrollToItem(uiscript_item)

        element_tree_root = self.elements_tree.invisibleRootItem()
        if element_tree_root:
            for child in iterate_children(element_tree_root):
                if child.data(2, Qt.ItemDataRole.UserRole) == element_id:
                    self.elements_tree.setCurrentItem(child)
                    self.elements_tree.scrollToItem(child)
                    break

        attribute_tree_root = self.attributes_tree.invisibleRootItem()
        if attribute_tree_root:
            for child in iterate_children(attribute_tree_root):
                if child.text(0) == attribute_name:
                    self.attributes_tree.setCurrentItem(child)
                    self.attributes_tree.scrollToItem(child)
                    break

        self.main_window.raise_()
        self.main_window.activateWindow()

    def reset(self):
        """Reset the state of the search dialog"""
        self.search_box_attrib.clear()
        self.search_box_value.clear()
        self.results.clear()
        self.validate_input()
