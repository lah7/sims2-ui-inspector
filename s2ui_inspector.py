#!/usr/bin/python3
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
# Copyright (C) 2024-2025 Luke Horwell <code@horwell.me>
#
"""
S2UI Inspector is a cross-platform PyQt6 application that browses
and recreates user interfaces from The Sims 2. It parses UI Scripts
and graphics for visual inspection outside the game.
"""
import base64
import glob
import hashlib
import io
import os
import re
import signal
import sys
import webbrowser

import PIL.Image
from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QAbstractScrollArea, QApplication, QDockWidget,
                             QFileDialog, QHBoxLayout, QMainWindow, QMenu,
                             QMenuBar, QMessageBox, QSplitter, QStatusBar,
                             QTreeWidget, QTreeWidgetItem, QWidget)

from sims2patcher import dbpf

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
PROJECT_URL = "https://github.com/lah7/sims2-ui-inspector"
VERSION = "0.1.0"


def uiscript_to_html(orig: str) -> str:
    """
    Convert .uiscript files to plain HTML.
    UI Scripts are XML-like formats with unquoted attribute values.

    Example:
        <LEGACY clsid=GZWinGen iid=IGZWinGen area=(10,10,605,432) >

    Becomes:
        <div class="GZWinGen" id="IGZWinGen" x="10" y="10" width="605" height="432"></div>
    """
    output = ""
    for line in orig.split("\n"):
        if line.startswith("#"):
            continue
        output += line + "\n"

    # Replace <LEGACY> and <CHILDREN> tags with <div>
    output = output.replace("<LEGACY", "<div class=\"LEGACY\"")
    output = output.replace("<CHILDREN", "<div class=\"CHILDREN\"")
    output = output.replace("</LEGACY>", "</div>")
    output = output.replace("</CHILDREN>", "</div>")

    # <LEGACY> tags didn't have closing tags, add one if not present
    output = output.replace(" >", "></div>")

    return output


class State:
    """A collection of entries from a .package file"""
    file_list: list[str] = [] # List of paths
    graphics: dict[tuple, dbpf.Entry] = {} # (group_id, instance_id) -> Entry


class Bridge(QObject):
    """Bridge between Python and JavaScript"""
    @pyqtSlot(str, bool, int, int, result=str) # type: ignore
    def get_image(self, image_attr: str, is_edge_image: bool, height: int, width: int) -> str:
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
        try:
            _group_id, _instance_id = image_attr[1:-1].split(",")
            group_id = int(_group_id, 16)
            instance_id = int(_instance_id, 16)
        except ValueError:
            print(f"Invalid image group/instance ID: {image_attr}")
            return ""

        try:
            entry = State.graphics[(group_id, instance_id)]
        except KeyError:
            print(f"Image not found: Group ID {hex(group_id)}, Instance ID {hex(instance_id)}")
            return ""

        # Convert to PNG as browser doesn't support TGA
        io_out = io.BytesIO()
        try:
            io_in = io.BytesIO(entry.data_safe)
            tga = PIL.Image.open(io_in)
            tga = tga.convert("RGBA") # Remove transparency
            tga.save(io_out, format="PNG")
        except dbpf.errors.QFSError:
            print(f"Image failed to extract: Group ID {hex(group_id)}, Instance ID {hex(instance_id)}")
            return ""

        # Post processing required?
        if is_edge_image:
            io_out = self._render_dialog_image(io_out, height, width)

        return base64.b64encode(io_out.getvalue()).decode("utf-8")

    def _render_dialog_image(self, data_io: io.BytesIO, height: int, width: int) -> io.BytesIO:
        """
        Generate a new image replicating how the game renders a dialog background image.
        """
        original = PIL.Image.open(data_io).convert("RGBA")

        def _copy_pixels(src_x: int, src_y: int, width: int, height: int, dst_x: int, dst_y: int):
            """Copy pixels from one image to another"""
            src = original.crop((src_x, src_y, src_x + width, src_y + height))
            canvas.paste(src, (dst_x, dst_y, dst_x + width, dst_y + height))

        def _tile_pixels(src_x: int, src_y: int, width: int, height: int, dst_x: int, dst_y: int, dst_x2: int, dst_y2: int):
            """Repeat an image from the source image to the destination (within boundaries)"""
            src = original.crop((src_x, src_y, src_x + width, src_y + height))
            for x in range(dst_x, dst_x2, width):
                for y in range(dst_y, dst_y2, height):
                    canvas.paste(src, (x, y, x + width, y + height))

        # Example image: Group 0x499db772, Instance 0xa9500615 (90x186 pixels)
        canvas = PIL.Image.new("RGBA", (width, height), (0, 0, 0, 0))

        # Handle the corners and edges of the dialog
        right_edge_starts = width - 30
        bottom_edge_starts = height - 62

        _tile_pixels(30, 30, 30, 30, 30, 30, right_edge_starts, bottom_edge_starts) # Center / Inner

        _tile_pixels(0, 30, 30, 30, 0, 30, 30, bottom_edge_starts)                                         # Left edge
        _tile_pixels(60, 30, 30, 30, right_edge_starts, 30, right_edge_starts + 30, bottom_edge_starts)    # Right edge
        _tile_pixels(30, 0, 30, 30, 30, 0, right_edge_starts, 30)                                          # Top edge
        _tile_pixels(30, 124, 30, 62, 30, bottom_edge_starts, right_edge_starts, bottom_edge_starts + 124) # Bottom edge

        _copy_pixels(0, 0, 30, 30, 0, 0)                                     # Top-left corner
        _copy_pixels(60, 0, 30, 30, right_edge_starts, 0)                    # Top-right corner
        _copy_pixels(0, 124, 30, 62, 0, bottom_edge_starts)                  # Bottom-left corner
        _copy_pixels(60, 124, 30, 62, right_edge_starts, bottom_edge_starts) # Bottom-right corner

        output = io.BytesIO()
        canvas.save(output, format="PNG")
        return output


class MainInspectorWindow(QMainWindow):
    """
    Main interface for inspecting .uiScript files
    """
    def __init__(self):
        super().__init__()
        self.items: list[QTreeWidgetItem] = []

        # Layout
        self.base_widget = QWidget()
        self.base_layout = QHBoxLayout()
        self.base_widget.setLayout(self.base_layout)
        self.setCentralWidget(self.base_widget)

        self.file_tree = QTreeWidget(self.base_widget)
        self.file_tree.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.file_tree.setHeaderLabels(["Group ID", "Instance ID", "Caption Hint", "Package", "Appears in"])
        self.file_tree.setColumnWidth(0, 120)
        self.file_tree.setColumnWidth(1, 100)
        self.file_tree.setColumnWidth(2, 150)
        self.file_tree.setColumnWidth(3, 130)
        self.file_tree.setColumnWidth(4, 100)
        self.file_tree.setSortingEnabled(True)
        self.file_tree.currentItemChanged.connect(self.inspect_ui_file)

        self.list_dock = QDockWidget("UI Scripts", self)
        self.list_dock.setMinimumWidth(400)
        self.list_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.list_dock.setWidget(self.file_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.list_dock)

        self.status_bar: QStatusBar = self.statusBar() # type: ignore
        self.status_bar.showMessage("Loading...")

        # UI Preview
        self._webview = QWidget()
        self._webview_layout = QHBoxLayout()
        self._webview_layout.setContentsMargins(0, 0, 0, 0)
        self._webview.setLayout(self._webview_layout)
        self.webview = QWebEngineView(self._webview)
        self._webview_layout.addWidget(self.webview)
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setHtml("<style>body { background: #003062; }</style>")

        # Inspector View
        self._inspector = QWidget()
        self._inspector_layout = QHBoxLayout()
        self._inspector_layout.setContentsMargins(0, 0, 0, 0)
        self._inspector.setLayout(self._inspector_layout)
        self.inspector = QWebEngineView(self._inspector)
        self._inspector_layout.addWidget(self.inspector)
        self.inspector.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.inspector.page().setInspectedPage(self.webview.page()) # type: ignore

        self.web_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.web_splitter.addWidget(self._webview)
        self.web_splitter.addWidget(self._inspector)
        self.web_splitter.setSizes([1000, 500])
        self.base_layout.addWidget(self.web_splitter)

        # The bridge allows the web view to communicate with Python
        self.channel = QWebChannel()
        self.webview.page().setWebChannel(self.channel) # type: ignore
        self.bridge = Bridge()
        self.channel.registerObject("python", self.bridge)

        # Menu bar
        self.menu_bar = QMenuBar()
        self.setMenuBar(self.menu_bar)

        # -- File
        self.menu_file = QMenu("File")
        self.menu_bar.addMenu(self.menu_file)

        self.action_open_pkg = QAction(QIcon.fromTheme("document-open"), "Open Package...")
        self.action_open_pkg.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open_pkg.triggered.connect(lambda: self.browse(open_dir=False))
        self.menu_file.addAction(self.action_open_pkg)

        self.action_open_dir = QAction(QIcon.fromTheme("document-open-folder"), "Open Game Folder...")
        self.action_open_dir.triggered.connect(lambda: self.browse(open_dir=True))
        self.menu_file.addAction(self.action_open_dir)

        self.menu_file.addSeparator()
        self.action_exit = QAction(QIcon.fromTheme("application-exit"), "Exit")
        self.action_exit.triggered.connect(self.close)
        self.menu_file.addAction(self.action_exit)

        # -- Help
        self.menu_help = QMenu("Help")
        self.menu_bar.addMenu(self.menu_help)

        self.action_online = QAction(QIcon.fromTheme("globe"), "View on GitHub")
        self.action_online.triggered.connect(lambda: webbrowser.open(PROJECT_URL))
        self.menu_help.addAction(self.action_online)

        self.menu_help.addSeparator()
        self.action_about_qt = QAction(QIcon.fromTheme("qtcreator"), "About Qt")
        self.action_about_qt.triggered.connect(lambda: QMessageBox.aboutQt(self))
        self.menu_help.addAction(self.action_about_qt)

        self.action_about_app = QAction(QIcon.fromTheme("help-about"), "About S2UI Inspector")
        self.action_about_app.triggered.connect(lambda: QMessageBox.about(self, "About S2UI Inspector", f"S2UI Inspector v{VERSION}\n{PROJECT_URL}\n\nA graphical user interface viewer for The Sims 2."))
        self.menu_help.addAction(self.action_about_app)

        # Window properties
        self.resize(1424, 768)
        self.setWindowTitle("S2UI Inspector")
        self.setWindowIcon(QIcon(os.path.abspath(os.path.join(DATA_DIR, "icon.svg"))))
        self.show()
        self.status_bar.showMessage("Ready")

        # Auto load file/folder when passed as a command line argument
        if len(sys.argv) > 1:
            path = sys.argv[1]
            if os.path.exists(path) and os.path.isdir(path):
                self.discover_files(path)
                self.load_files()
            elif os.path.exists(path):
                State.file_list = [path]
                self.load_files()
        else:
            self.browse(open_dir=True)

    def browse(self, open_dir: bool):
        """
        Show the file/folder dialog to select a package file.
        """
        browser = QFileDialog(self)
        if open_dir:
            browser.setFileMode(QFileDialog.FileMode.Directory)
            browser.setViewMode(QFileDialog.ViewMode.List)
        else:
            browser.setFileMode(QFileDialog.FileMode.ExistingFile)
            browser.setViewMode(QFileDialog.ViewMode.Detail)
            browser.setNameFilter("The Sims 2 Package Files (*.package CaSIEUI.data)")

        if browser.exec() == QFileDialog.DialogCode.Accepted:
            self.clear_state()
            if open_dir:
                self.discover_files(browser.selectedFiles()[0])
            else:
                State.file_list = browser.selectedFiles()
            self.load_files()

        self.setStatusTip("No files opened.")

    def clear_state(self):
        """
        Reset the inspector ready to open new files.
        """
        State.graphics = {}
        self.file_tree.clear()

    def discover_files(self, path: str):
        """
        Gather a file list of packages containing UI scripts.
        """
        State.file_list = []
        for filename in ["TSData/Res/UI/ui.package", "TSData/Res/UI/CaSIEUI.data"]:
            State.file_list += glob.glob(f"{path}/**/{filename}", recursive=True)

        if not State.file_list:
            for filename in ["ui.package", "CaSIEUI.data"]:
                State.file_list += glob.glob(f"{path}/**/{filename}", recursive=True)

    def load_files(self):
        """
        Load all UI scripts found in game directories.
        Display unique instances of UI scripts, and where they were found.
        """
        self.status_bar.showMessage(f"Opening {len(State.file_list)} packages...")
        self.setCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()

        ui_dups: dict[tuple, list[dbpf.Entry]] = {}
        entry_to_game: dict[dbpf.Entry, str] = {}
        entry_to_package: dict[dbpf.Entry, str] = {}

        for path in State.file_list:
            package = dbpf.DBPF(path)
            package_name = os.path.basename(path)

            # Create list of UI files, but also identify duplicates across EPs/SPs
            for entry in [entry for entry in package.entries if entry.type_id == dbpf.TYPE_UI_DATA]:
                key = (entry.group_id, entry.instance_id)

                # Ignore binary files
                if entry.decompressed_size > 1024 * 1024:
                    continue

                # Look up an entry by group and instance ID
                if key in ui_dups:
                    ui_dups[key].append(entry)
                else:
                    ui_dups[key] = [entry]

                # Look up which game/package an entry belongs to
                entry_to_game[entry] = package.game_name
                entry_to_package[entry] = package_name

            # Graphics can be looked up by group and instance ID
            for entry in [entry for entry in package.entries if entry.type_id == dbpf.TYPE_IMAGE]:
                State.graphics[(entry.group_id, entry.instance_id)] = entry

        self.status_bar.showMessage(f"Reading {len(ui_dups.keys())} UI scripts...")
        QApplication.processEvents()

        # Display items by group/instance; secondary by game (if the contents differ)
        for group_id, instance_id in ui_dups:
            entries: list[dbpf.Entry] = ui_dups[(group_id, instance_id)]
            key = (group_id, instance_id)
            checksums: dict[dbpf.Entry, str] = {}
            for entry in entries:
                checksums[entry] = hashlib.md5(entry.data_safe).hexdigest()
            identical = len(set(checksums.values())) == 1
            package_names = ", ".join(list(set(entry_to_package[entry] for entry in entries)))

            # Display a single item when UI scripts are identical across all games (or is only one)
            if identical:
                game_names = ", ".join([entry_to_game[entry] for entry in entries])
                entry = entries[0]
                item = QTreeWidgetItem(self.file_tree, [str(hex(group_id)), str(hex(instance_id)), "", package_names, game_names])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                self.items.append(item)

            # Display a tree item for each unique instance of the UI script
            else:
                parent = QTreeWidgetItem(self.file_tree, [str(hex(group_id)), str(hex(instance_id)), "", package_names, f"{len(entries)} games"])
                parent.setData(0, Qt.ItemDataRole.UserRole, entries[0])
                self.items.append(parent)
                _md5_to_item: dict[str, QTreeWidgetItem] = {}
                _game_names = []

                for entry in entries:
                    checksum = checksums[entry]
                    game_name = entry_to_game[entry]
                    package_name = entry_to_package[entry]
                    _game_names.append(game_name)

                    try:
                        # Append to existing item
                        child: QTreeWidgetItem = _md5_to_item[checksum]
                        if not package_name in child.text(3):
                            child.setText(3, f"{child.text(3)}, {package_name}")
                        if not game_name in child.text(4):
                            child.setText(4, f"{child.text(4)}, {game_name}")
                    except KeyError:
                        # Create new item
                        child = QTreeWidgetItem(parent, [str(hex(group_id)), str(hex(instance_id)), "", package_name, game_name])
                        child.setData(0, Qt.ItemDataRole.UserRole, entry)
                        self.items.append(child)
                        _md5_to_item[checksum] = child

                parent.setToolTip(4, "\n".join(sorted(_game_names)))

        # Show games under tooltips
        for item in self.items:
            games = item.text(4).split(", ")
            if len(games) > 1:
                games = sorted(games)
                item.setToolTip(4, "\n".join(games))
                item.setText(4, f"{len(games)} games")

        total = len(ui_dups.keys())
        self.status_bar.showMessage(f"Found {total} UI scripts", 3000)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        timer = QTimer(self)
        timer.singleShot(1000, self.preload_files)

    def inspect_ui_file(self, item: QTreeWidgetItem):
        """
        Open the selected .uiScript file in the web view.
        """
        if not item:
            return

        entry: dbpf.Entry = item.data(0, Qt.ItemDataRole.UserRole)

        try:
            html = uiscript_to_html(entry.data.decode("utf-8"))
        except UnicodeDecodeError:
            html = "Unable to decode. It may be binary data."
        with open(os.path.join(DATA_DIR, "inspector.html"), "r", encoding="utf-8") as f:
            html = f.read().replace("PLACEHOLDER", html)
        self.webview.setHtml(html, baseUrl=QUrl.fromLocalFile(f"{DATA_DIR}/"))

    def preload_files(self):
        """
        Continue loading files in the background to identify captions.
        """
        while self.items:
            item = self.items.pop(0)
            entry: dbpf.Entry = item.data(0, Qt.ItemDataRole.UserRole)

            if entry.decompressed_size > 1024 * 1024: # Likely binary (over 1 MiB)
                item.setDisabled(True)
                item.setText(2, "Binary data")
                continue

            html = entry.data.decode("utf-8")
            matches = re.findall(r'\bcaption="([^"]+)"', html)

            # Use longest caption as the title
            if matches:
                # Exclude captions used for technical key/value pairs
                matches = [match.replace("\n", "") for match in matches if (not match.find("=") != -1 and not match.isupper()) or match.islower()]

                item.setText(2, max(matches, key=len))
                item.setToolTip(2, "\n".join(matches))


if __name__ == "__main__":
    # CTRL+C to exit
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    window = MainInspectorWindow()
    app.exec()
