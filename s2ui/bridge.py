"""
Module that bridges data between Python and JavaScript via PyQt.

Rendering images is done in Python as the browser doesn't support TGA images.
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
import base64
import io

import PIL.Image
from PyQt6.QtCore import QObject, Qt, pyqtSlot
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItemIterator

import s2ui.rendering
from s2ui.state import State
from submodules.sims2_4k_ui_patch.sims2patcher import dbpf, uiscript


def get_s2ui_element_id(element: uiscript.UIScriptElement) -> str:
    """
    Generate a unique ID for selecting this element internally between HTML/JS and PyQt.
    """
    return f"s2ui_{id(element)}"


def get_image_as_png(image_attr: str) -> io.BytesIO|None:
    """
    Extract an image from the currently loaded packages ("state").
    For Qt and WebView compatibility, it will be converted to a PNG.

    Return as an in-memory PNG image file.
    """
    try:
        _group_id, _instance_id = image_attr[1:-1].split(",")
        group_id = int(_group_id, 16)
        instance_id = int(_instance_id, 16)
    except ValueError:
        print(f"Invalid image group/instance ID: {image_attr}")
        return None

    try:
        entry = State.graphics[(group_id, instance_id)]
    except KeyError:
        print(f"Image not found: Group ID {hex(group_id)}, Instance ID {hex(instance_id)}")
        return None

    # Convert to PNG as browser doesn't support TGA
    io_out = io.BytesIO()
    try:
        io_in = io.BytesIO(entry.data_safe)
        tga = PIL.Image.open(io_in)
        tga = tga.convert("RGBA") # Remove transparency
        tga.save(io_out, format="PNG")
    except dbpf.errors.QFSError:
        print(f"Image failed to extract: Group ID {hex(group_id)}, Instance ID {hex(instance_id)}")
        return None

    io_out.seek(0)
    return io_out


class Bridge(QObject):
    """
    Bridge between Python and JavaScript.
    """
    def __init__(self, element_tree: QTreeWidget, elements_menu: QMenu) -> None:
        super().__init__()
        self.element_tree = element_tree
        self.elements_menu = elements_menu

    @pyqtSlot(str, bool, int, int, result=str) # type: ignore
    def get_image(self, image_attr: str, is_edge_image: bool, width: int, height: int) -> str:
        """
        Return a base64 encoded PNG image for a TGA graphic extracted from the package.

        Additional attributes will be read to determine whether post-processing
        is required (such as to render a dialog background).

        Expected:
            - image_attr: "{group_id, instance_id}"
            - wparam_attr: "0x0300d422,uint32,1"
            - is_edge_image: Whether edgeimage="yes" or "blttype="edge" is set
            - height and width of element (for post processing purposes)
        """
        image = get_image_as_png(image_attr)
        if image is None:
            return ""

        # Perform post processing if necessary
        if is_edge_image:
            image = s2ui.rendering.render_edge_image(image, width, height)

        return base64.b64encode(image.getvalue()).decode("utf-8")

    @pyqtSlot(str)
    def select_element(self, element_id: str):
        """
        User clicked on an element in webview. Highlight new element in the tree.
        """
        iterator = QTreeWidgetItemIterator(self.element_tree)
        while iterator.value():
            item = iterator.value()
            if not item:
                return

            if item.data(2, Qt.ItemDataRole.UserRole) == element_id:
                self.element_tree.setCurrentItem(item)
                self.element_tree.scrollToItem(item)
                break

            iterator += 1

    @pyqtSlot(str)
    def hover_element(self, element_id: str):
        """
        User hovered over an element in webview. Highlight this element in the tree.
        """
        iterator = QTreeWidgetItemIterator(self.element_tree)
        while iterator.value():
            item = iterator.value()
            if not item:
                return

            if item.data(2, Qt.ItemDataRole.UserRole) == element_id:
                for c in range(item.columnCount()):
                    item.setBackground(c, Qt.GlobalColor.darkGray)
            else:
                # Reset background colour
                for c in range(item.columnCount()):
                    item.setData(c, Qt.ItemDataRole.BackgroundRole, None)

            iterator += 1

    @pyqtSlot()
    def right_click_element(self):
        """
        Open the right click menu for the selected element.
        """
        self.elements_menu.exec(QCursor.pos())
