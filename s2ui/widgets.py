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
from PyQt6.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem


class FilterBox(QLineEdit):
    """A text box to quickly filter a tree in a dock widget"""
    def __init__(self, tree: QTreeWidget):
        super().__init__()
        self.tree_widget = tree

        self.setPlaceholderText("Filter...")
        self.setClearButtonEnabled(True)
        self.textChanged.connect(self.update_tree)

    def update_tree(self, criteria: str):
        """Filter the UI scripts by group ID or caption."""
        for i in range(self.tree_widget.topLevelItemCount()):
            item: QTreeWidgetItem = self.tree_widget.topLevelItem(i) # type: ignore
            if not item:
                continue

            if criteria == "":
                item.setHidden(False)
                for c in range(0, item.columnCount()):
                    item.setData(c, Qt.ItemDataRole.BackgroundRole, None)
                continue

            criteria = criteria.lower()
            matches = False
            for c in range(0, item.columnCount()):
                if criteria in item.text(c).lower() or criteria in item.toolTip(c).lower():
                    matches = True
                    item.setBackground(c, Qt.GlobalColor.darkGreen)
                else:
                    item.setData(c, Qt.ItemDataRole.BackgroundRole, None)

            item.setHidden(not matches)
