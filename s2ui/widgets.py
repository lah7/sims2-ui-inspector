"""
Module for Qt widgets used in the UI.
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
from PyQt6.QtWidgets import (QAbstractScrollArea, QDockWidget, QLineEdit,
                             QMainWindow, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)


class DockTree(QDockWidget):
    """A dock widget with a title and a tree widget."""
    def __init__(self, parent: QMainWindow, title: str, min_width: int, position: Qt.DockWidgetArea):
        super().__init__(title, parent)

        # Dock properties
        self.setMinimumWidth(min_width)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable | QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetClosable)

        # Dock widget/layout
        self.base_widget = QWidget()
        self.base_layout = QVBoxLayout()
        self.base_widget.setLayout(self.base_layout)
        self.setWidget(self.base_widget)
        parent.addDockWidget(position, self)

        # Widgets
        self.tree = QTreeWidget()
        self.tree.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.filter = FilterBox(self.tree)

        self.base_layout.addWidget(self.filter)
        self.base_layout.addWidget(self.tree)


class FilterBox(QLineEdit):
    """
    A text box to quickly filter a tree in a dock widget.
    """
    def __init__(self, tree: QTreeWidget):
        super().__init__()
        self.tree_widget = tree

        self.setPlaceholderText("Filter...")
        self.setClearButtonEnabled(True)
        self.textChanged.connect(self.update_tree)

    def _get_all_children(self, item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
        """
        Get all children of an item recursively.
        """
        if not item:
            return []

        children = []
        for i in range(item.childCount()):
            child = item.child(i)
            if not item:
                continue
            children.append(child)
            children += self._get_all_children(child) # type: ignore
        return children

    def _reset_tree(self):
        """
        Loop through all items in the tree and show them.
        """
        for item in self._get_all_children(self.tree_widget.invisibleRootItem()): # type: ignore
            item.setHidden(False)
            for col in range(0, item.columnCount()):
                item.setData(col, Qt.ItemDataRole.BackgroundRole, None)

    def _update_item(self, item: QTreeWidgetItem, criteria: str):
        """
        Update the item's visibility based on the criteria.
        Always show the parent(s) if a child matches.
        """
        if not item:
            return

        criteria = criteria.lower()
        matches = False
        for col in range(0, item.columnCount()):
            if criteria in item.text(col).lower() or criteria in item.toolTip(col).lower():
                matches = True
                item.setBackground(col, Qt.GlobalColor.darkGreen)
            else:
                item.setData(col, Qt.ItemDataRole.BackgroundRole, None)

        item.setHidden(not matches)

        if matches:
            parent = item.parent()
            while parent:
                parent.setHidden(False)
                parent = parent.parent()

    def update_tree(self, criteria: str):
        """
        Filter the UI scripts by group ID or caption.
        """
        if not criteria:
            self._reset_tree()
            return

        for item in self._get_all_children(self.tree_widget.invisibleRootItem()): # type: ignore
            self._update_item(item, criteria)

    def refresh_tree(self):
        """
        Refresh the filtered tree widget when the tree changes.
        """
        self.update_tree(self.text())

    def is_filtered(self) -> bool:
        """
        Check if the tree is currently filtered.
        """
        return bool(self.text())
