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
import glob
import hashlib
import os
import re
import signal
import sys
import webbrowser

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import (QAction, QColor, QCursor, QFontDatabase, QIcon,
                         QImage, QKeySequence, QPainter, QPixmap)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QAbstractScrollArea, QApplication, QDialog,
                             QDialogButtonBox, QFileDialog, QHBoxLayout,
                             QMainWindow, QMenu, QMenuBar, QMessageBox,
                             QSplitter, QStatusBar, QTextEdit, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

import s2ui.widgets
from s2ui.bridge import Bridge, get_image_as_png
from s2ui.state import State
from sims2patcher import dbpf, uiscript

PROJECT_URL = "https://github.com/lah7/sims2-ui-inspector"
VERSION = "0.1.0"


@staticmethod
def get_resource(filename: str) -> str:
    """
    Get a resource bundled with the application or from the same directory as the program.
    """
    if getattr(sys, "frozen", False):
        data_dir = os.path.join(os.path.dirname(sys.executable), "data")
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "data")
    return os.path.join(data_dir, filename)


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

        # Dock: UI Scripts
        # QTreeWidgetItem data columns:
        # - 0: dbpf.Entry
        self.uiscript_dock = s2ui.widgets.DockTree(self, "UI Scripts", 400, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.uiscript_dock.tree.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.uiscript_dock.tree.setHeaderLabels(["Group ID", "Instance ID", "Caption Hint", "Package", "Appears in"])
        self.uiscript_dock.tree.setColumnWidth(0, 120)
        self.uiscript_dock.tree.setColumnWidth(1, 100)
        self.uiscript_dock.tree.setColumnWidth(2, 150)
        self.uiscript_dock.tree.setColumnWidth(3, 130)
        self.uiscript_dock.tree.setColumnWidth(4, 100)
        self.uiscript_dock.tree.setSortingEnabled(True)
        self.uiscript_dock.tree.currentItemChanged.connect(self.inspect_ui_file)
        self.uiscript_dock.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.uiscript_dock.tree.customContextMenuRequested.connect(lambda: self.menu_tools.exec(QCursor.pos()))

        # Dock: Elements
        # QTreeWidgetItem data columns:
        # - 0: uiscript.UIScriptElement
        # - 1: bool: Visible
        # - 2: str: s2ui_element_id
        self.elements_dock = s2ui.widgets.DockTree(self, "Elements", 400, Qt.DockWidgetArea.RightDockWidgetArea)
        self.elements_dock.tree.setHeaderLabels(["Element", "Caption", "ID", "Position"])
        self.elements_dock.tree.setColumnWidth(0, 225)
        self.elements_dock.tree.setColumnWidth(3, 100)
        self.elements_dock.tree.currentItemChanged.connect(self.inspect_element)
        self.elements_dock.tree.setMouseTracking(True)
        self.elements_dock.tree.itemEntered.connect(self.hover_element)

        # Dock: Properties
        self.properties_dock = s2ui.widgets.DockTree(self, "Properties", 400, Qt.DockWidgetArea.RightDockWidgetArea)
        self.properties_dock.tree.setHeaderLabels(["Attribute", "Value"])
        self.properties_dock.tree.setColumnWidth(0, 200)
        self.properties_dock.tree.setSortingEnabled(True)
        self.properties_dock.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # Allow drag-and-dropping docks into each other
        self.setDockOptions(QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AllowNestedDocks)

        # Menu bar; add actions to dock toolbars
        self._create_menu_bar()
        self.uiscript_dock.toolbar.addAction(self.action_script_src)
        self.uiscript_dock.toolbar.addAction(self.action_copy_ids)

        # Status bar
        self.status_bar: QStatusBar = self.statusBar() # type: ignore
        self.status_bar.showMessage("Loading...")

        # UI rendering
        self.webview = QWebEngineView()
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setHtml("<style>body { background: #003062; }</style>")
        self.webview_page = self.webview.page() or QWebEnginePage() # 'Or' to satisfy strong type checking
        self.base_layout.addWidget(self.webview)

        # The bridge allows the web view to communicate with Python
        self.channel = QWebChannel()
        self.webview_page.setWebChannel(self.channel)
        self.bridge = Bridge(self.elements_dock.tree)
        self.channel.registerObject("python", self.bridge)

        # Window properties
        self.resize(1424, 768)
        self.setWindowTitle("S2UI Inspector")
        self.setWindowIcon(QIcon(os.path.abspath(get_resource("icon.ico"))))
        self.show()
        self.status_bar.showMessage("Ready")
        QApplication.processEvents()

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

    def _create_menu_bar(self):
        """Create the actions for the application's menu bar"""
        self.menu_bar = QMenuBar()
        self.setMenuBar(self.menu_bar)

        # === File ===
        self.menu_file = QMenu("File")
        self.menu_bar.addMenu(self.menu_file)

        self.action_open_dir = QAction(QIcon.fromTheme("document-open-folder"), "Open Game Folder...")
        self.action_open_dir.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open_dir.triggered.connect(lambda: self.browse(open_dir=True))
        self.menu_file.addAction(self.action_open_dir)

        self.action_open_pkg = QAction(QIcon.fromTheme("document-open"), "Open Single Package...")
        self.action_open_pkg.triggered.connect(lambda: self.browse(open_dir=False))
        self.menu_file.addAction(self.action_open_pkg)

        self.menu_file.addSeparator()
        self.action_reload = QAction(QIcon.fromTheme("view-refresh"), "Reload Packages")
        self.action_reload.triggered.connect(self.reload_files)
        self.menu_file.addAction(self.action_reload)

        self.menu_file.addSeparator()
        self.action_exit = QAction(QIcon.fromTheme("application-exit"), "Exit")
        self.action_exit.triggered.connect(self.close)
        self.menu_file.addAction(self.action_exit)

        # === View ===
        self.menu_view = QMenu("View")
        self.menu_bar.addMenu(self.menu_view)
        self._actions = [] # To prevent garbage collection

        for dock in [self.uiscript_dock, self.elements_dock, self.properties_dock]:
            dock_action = QAction(dock.windowTitle())
            dock_action.setCheckable(True)
            dock_action.setChecked(dock.isVisible())
            dock_action.triggered.connect(lambda checked, dock=dock: dock.setVisible(checked))
            dock.visibilityChanged.connect(dock_action.setChecked)
            self.menu_view.addAction(dock_action)
            self._actions.append(dock_action)

        self.menu_view.addSeparator()

        self.action_zoom_in = QAction(QIcon.fromTheme("zoom-in"), "Zoom In")
        self.action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.action_zoom_in.triggered.connect(lambda: self.webview.setZoomFactor(self.webview.zoomFactor() + 0.1))
        self.menu_view.addAction(self.action_zoom_in)

        self.action_zoom_out = QAction(QIcon.fromTheme("zoom-out"), "Zoom Out")
        self.action_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.action_zoom_out.triggered.connect(lambda: self.webview.setZoomFactor(self.webview.zoomFactor() - 0.1))
        self.menu_view.addAction(self.action_zoom_out)

        self.menu_view.addSeparator()

        for index, level in enumerate([50, 100, 150, 200]):
            zoom_action = QAction(QIcon.fromTheme("zoom"), f"Zoom {level}%")
            zoom_action.triggered.connect(lambda x, level=level: self.webview.setZoomFactor(level / 100))
            zoom_action.setShortcut(QKeySequence.fromString(f"Ctrl+{index + 1}"))
            self.menu_view.addAction(zoom_action)
            self._actions.append(zoom_action)

        self.menu_view.addSeparator()

        # === Tools ===
        self.menu_tools = QMenu("Tools")
        self.menu_bar.addMenu(self.menu_tools)

        self.action_script_src = QAction(QIcon.fromTheme("format-text-code"), "View Original Code")
        self.action_script_src.triggered.connect(self.open_original_code)
        self.action_script_src.setDisabled(True)
        self.menu_tools.addAction(self.action_script_src)

        self.menu_copy_ids = QMenu()

        self.action_copy_group_id = QAction(QIcon.fromTheme("edit-copy"), "Copy Group ID")
        self.action_copy_group_id.triggered.connect(lambda: self._copy_to_clipboard(State.current_group_id))
        self.menu_copy_ids.addAction(self.action_copy_group_id)

        self.action_copy_instance_id = QAction(QIcon.fromTheme("edit-copy"), "Copy Instance ID")
        self.action_copy_instance_id.triggered.connect(lambda: self._copy_to_clipboard(State.current_instance_id))
        self.menu_copy_ids.addAction(self.action_copy_instance_id)

        self.action_copy_ids = QAction(QIcon.fromTheme("edit-copy"), "Copy IDs")
        self.action_copy_ids.setMenu(self.menu_copy_ids)
        self.action_copy_ids.setToolTip("Copy Group ID and Instance ID to clipboard")
        self.action_copy_ids.setShortcut(QKeySequence.fromString("Ctrl+Shift+C"))
        self.action_copy_ids.triggered.connect(lambda: self._copy_to_clipboard(f"{hex(State.current_group_id)}_{hex(State.current_instance_id)}"))
        self.action_copy_ids.setDisabled(True)
        self.menu_tools.addAction(self.action_copy_ids)

        self.menu_tools.addSeparator()
        self.action_debug_inspect = QAction(QIcon.fromTheme("tools-symbolic"), "Debug Web View")
        self.action_debug_inspect.triggered.connect(self.open_web_dev_tools)
        self.menu_tools.addAction(self.action_debug_inspect)

        # === Help ===
        self.menu_help = QMenu("Help")
        self.menu_bar.addMenu(self.menu_help)

        self.action_online = QAction(QIcon.fromTheme("globe"), "View on GitHub")
        self.action_online.triggered.connect(lambda: webbrowser.open(PROJECT_URL))
        self.menu_help.addAction(self.action_online)

        self.action_releases = QAction("Check Releases")
        self.action_releases.triggered.connect(lambda: webbrowser.open(f"{PROJECT_URL}/releases"))
        self.menu_help.addAction(self.action_releases)

        self.menu_help.addSeparator()
        self.action_about_qt = QAction(QIcon.fromTheme("qtcreator"), "About Qt")
        self.action_about_qt.triggered.connect(lambda: QMessageBox.aboutQt(self))
        self.menu_help.addAction(self.action_about_qt)

        self.action_about_app = QAction(QIcon.fromTheme("help-about"), "About S2UI Inspector")
        self.action_about_app.triggered.connect(lambda: QMessageBox.about(self, "About S2UI Inspector", f"S2UI Inspector v{VERSION}\n{PROJECT_URL}\n\nA graphical user interface viewer for The Sims 2."))
        self.menu_help.addAction(self.action_about_app)

    def _copy_to_clipboard(self, text: str|int):
        """Copy text to the clipboard"""
        clipboard = QApplication.clipboard()
        if isinstance(text, int):
            text = hex(text)
        if clipboard:
            clipboard.setText(text)
            self.status_bar.showMessage(f"Text copied: {text}", 5000)
        else:
            self.status_bar.showMessage("Unable to copy to clipboard")

    def browse(self, open_dir: bool):
        """
        Show the file/folder dialog to select a package file.
        """
        browser = QFileDialog(self, "Open Game Folder" if open_dir else "Open Package File")
        if open_dir:
            browser.setFileMode(QFileDialog.FileMode.Directory)
            browser.setViewMode(QFileDialog.ViewMode.List)
        else:
            browser.setFileMode(QFileDialog.FileMode.ExistingFile)
            browser.setViewMode(QFileDialog.ViewMode.Detail)
            browser.setNameFilter("The Sims 2 Package Files (*.package CaSIEUI.data)")

        if browser.exec() == QFileDialog.DialogCode.Accepted:
            self.action_reload.setEnabled(False)
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
        self.uiscript_dock.tree.clear()
        self.action_script_src.setDisabled(True)
        self.action_copy_ids.setDisabled(True)

        State.graphics = {}
        State.current_group_id = 0x0
        State.current_instance_id = 0x0

    def discover_files(self, path: str):
        """
        Gather a file list of packages containing UI scripts.
        """
        self.status_bar.showMessage(f"Discovering files: {path}")
        QApplication.processEvents()
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
        self.action_reload.setEnabled(False)
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
                item = QTreeWidgetItem(self.uiscript_dock.tree, [str(hex(group_id)), str(hex(instance_id)), "", package_names, game_names])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                self.items.append(item)

            # Display a tree item for each unique instance of the UI script
            else:
                parent = QTreeWidgetItem(self.uiscript_dock.tree, [str(hex(group_id)), str(hex(instance_id)), "", package_names, f"{len(entries)} games"])
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

        if self.uiscript_dock.filter.is_filtered():
            self.uiscript_dock.filter.refresh_tree()

        timer = QTimer(self)
        timer.singleShot(1000, self.preload_files)

    def reload_files(self):
        """Reload all files again from disk"""
        self.clear_state()
        self.load_files()

    def _get_s2ui_element_id(self, element: uiscript.UIScriptElement) -> str:
        """
        Generate a unique ID for selecting this element internally between HTML/JS and PyQt.
        """
        parts = []
        for key, value in element.attributes.items():
            parts.append(key)
            parts.append(value)
        digest = hashlib.md5("".join(parts).encode("utf-8")).hexdigest()
        return f"s2ui_{digest}"

    def _uiscript_to_html(self, root: uiscript.UIScriptRoot) -> str:
        """
        Render UI Script files into HTML for the webview.
        UI Scripts are XML-like formats with (mostly) unquoted attribute values.
        """
        def _process_line(element: uiscript.UIScriptElement) -> str:
            parts = ["<div class=\"LEGACY\""]
            for key, value in element.attributes.items():
                if not key == "id":
                    parts.append(f"{key}=\"{value}\"")

            s2ui_element_id = self._get_s2ui_element_id(element)
            parts.append(f"id=\"{s2ui_element_id}\"")
            parts.append(">")
            for child in element.children:
                parts.append(_process_line(child))
            parts.append("</div>")
            return " ".join(parts)

        lines = []
        for element in root.children:
            lines.append(_process_line(element))

        return "\n".join(lines)

    def inspect_ui_file(self, item: QTreeWidgetItem):
        """
        Change the currently selected .uiScript file for viewing/rendering.
        """
        if not item:
            return

        entry: dbpf.Entry = item.data(0, Qt.ItemDataRole.UserRole)
        State.current_group_id = entry.group_id
        State.current_instance_id = entry.instance_id

        self.elements_dock.tree.clear()
        self.properties_dock.tree.clear()

        try:
            data: uiscript.UIScriptRoot = uiscript.serialize_uiscript(entry.data.decode("utf-8"))
        except UnicodeDecodeError:
            self.webview.setHtml("")
            return QMessageBox.critical(self, "Cannot read file", "This file is not a valid .uiScript file.", QMessageBox.StandardButton.Ok)

        # Render the UI into HTML
        html = self._uiscript_to_html(data)
        with open(get_resource("inspector.html"), "r", encoding="utf-8") as f:
            html = f.read().replace("PLACEHOLDER", html)
        self.webview.setHtml(html, baseUrl=QUrl.fromLocalFile(get_resource("")))

        # Update the elements and properties dock
        def _process_element(element: uiscript.UIScriptElement, parent: QTreeWidget|QTreeWidgetItem):
            iid = element.attributes.get("iid", "Unknown")
            caption = element.attributes.get("caption", "")
            element_id = element.attributes.get("id", "")
            xpos, ypos, width, height = element.attributes.get("area", "(0,0,0,0)").strip("()").split(",")
            image_attr = element.attributes.get("image", "")

            item = QTreeWidgetItem(parent, [iid, caption, element_id, f"({xpos}, {ypos})"])
            item.setData(0, Qt.ItemDataRole.UserRole, element)
            item.setData(2, Qt.ItemDataRole.UserRole, self._get_s2ui_element_id(element))
            item.setToolTip(1, caption)
            item.setToolTip(2, element_id)
            item.setToolTip(3, f"X: {xpos}\nY: {ypos}\nWidth: {width}\nHeight: {height}")

            if image_attr:
                png = get_image_as_png(image_attr)
                if png is None:
                    pixmap = QPixmap(16, 16)
                    pixmap.fill(Qt.GlobalColor.red)
                else:
                    png_data = png.getvalue()
                    pixmap = QPixmap()
                    pixmap.loadFromData(png_data)

                    # For buttons, crop to the second 1/4 (normal state)
                    if iid == "IGZWinBtn":
                        quarter = pixmap.width() // 4
                        pixmap = QPixmap.fromImage(QImage.fromData(png_data).copy(quarter, 0, quarter, pixmap.height()))

                # Scale to square aspect ratio (16x16) for uniformity
                scaled_pixmap = pixmap.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                square_pixmap = QPixmap(16, 16)
                square_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(square_pixmap)
                x = (16 - scaled_pixmap.width()) // 2
                y = (16 - scaled_pixmap.height()) // 2
                painter.drawPixmap(x, y, scaled_pixmap)
                painter.end()
                item.setIcon(0, QIcon(square_pixmap))

            for child in element.children:
                _process_element(child, item)

            return item

        for element in data.children:
            _process_element(element, self.elements_dock.tree)

        self.elements_dock.tree.expandAll()
        self.elements_dock.tree.resizeColumnToContents(3)

        if self.elements_dock.filter.is_filtered():
            self.elements_dock.filter.refresh_tree()

        first_item = self.elements_dock.tree.topLevelItem(0)
        if first_item:
            self.elements_dock.tree.setCurrentItem(first_item)

    def hover_element(self, item: QTreeWidgetItem):
        """
        Highlight the hovered element in the webview.
        """
        if not item:
            return

        element_id: str = item.data(2, Qt.ItemDataRole.UserRole)
        self.webview_page.runJavaScript(f"hoverElement('{element_id}')")

    def inspect_element(self, item: QTreeWidgetItem):
        """
        Display the properties of the selected element.
        """
        if not item:
            return

        self.action_script_src.setEnabled(True)
        self.action_copy_ids.setEnabled(True)

        element: uiscript.UIScriptElement = item.data(0, Qt.ItemDataRole.UserRole)
        element_id: str = item.data(2, Qt.ItemDataRole.UserRole)
        self.webview_page.runJavaScript(f"selectElement('{element_id}')")

        self.properties_dock.tree.clear()

        for key, value in element.attributes.items():
            prop = QTreeWidgetItem(self.properties_dock.tree, [key, value])
            prop.setToolTip(1, value)

            # Expanded attributes
            match key:
                case "area":
                    x, y, width, height = value[1:-1].split(",")
                    for name, value in [("X", x), ("Y", y), ("Width", width), ("Height", height)]:
                        QTreeWidgetItem(prop, [name, value])
                case "image":
                    image_attr = element.attributes.get("image", "")
                    if image_attr:
                        _group_id, _instance_id = image_attr[1:-1].split(",")
                        group_id = int(_group_id, 16)
                        instance_id = int(_instance_id, 16)
                        QTreeWidgetItem(prop, ["Group ID", hex(group_id)])
                        QTreeWidgetItem(prop, ["Instance ID", hex(instance_id)])

            if key.find("color") != -1 and len(value.split(",")) == 3: # (R, G, B)
                _color = value[1:-1].split(",")
                pixmap = QPixmap(16, 16)
                pixmap.fill(QColor.fromRgb(int(_color[0]), int(_color[1]), int(_color[2])))
                prop.setIcon(1, QIcon(pixmap))

            prop.setExpanded(True)

        if self.properties_dock.filter.is_filtered():
            self.properties_dock.filter.refresh_tree()

    def preload_files(self):
        """
        Continue loading files in the background to identify captions.
        """
        self.action_reload.setEnabled(False)
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

        self.action_reload.setEnabled(True)

    def open_original_code(self):
        """
        Open the currently opened UI Script file's original code in a pop up window.
        """
        item: QTreeWidgetItem|None = self.uiscript_dock.tree.currentItem()
        if not item:
            return

        entry: dbpf.Entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not entry:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Source Code for Group ID {hex(State.current_group_id)}, Instance ID {hex(State.current_instance_id)}")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        dialog.setLayout(layout)

        code = QTextEdit(dialog)
        code.setPlainText(entry.data.decode("utf-8"))
        code.setReadOnly(True)
        code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)

        layout.addWidget(code)
        layout.addWidget(buttons)

        dialog.setMinimumSize(800, 600)
        dialog.adjustSize()
        dialog.exec()

    def open_web_dev_tools(self):
        """
        Open the web inspector for debugging this application.
        This is a one-way action. Place the web inspector tools into the main window.
        """
        # pylint: disable=attribute-defined-outside-init
        self._webview = QWidget()
        self._webview_layout = QHBoxLayout()
        self._webview_layout.setContentsMargins(0, 0, 0, 0)
        self._webview.setLayout(self._webview_layout)
        self._webview_layout.addWidget(self.webview)

        self._inspector = QWidget()
        self._inspector_layout = QHBoxLayout()
        self._inspector_layout.setContentsMargins(0, 0, 0, 0)
        self._inspector.setLayout(self._inspector_layout)
        self.inspector = QWebEngineView(self._inspector)
        self._inspector_layout.addWidget(self.inspector)
        self.inspector.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        inspector_page = self.inspector.page()
        if inspector_page:
            inspector_page.setInspectedPage(self.webview_page)

        self.web_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.web_splitter.addWidget(self._webview)
        self.web_splitter.addWidget(self._inspector)
        self.web_splitter.setSizes([1000, 500])

        self.base_layout.addWidget(self.web_splitter)
        self.action_debug_inspect.setDisabled(True)


if __name__ == "__main__":
    # CTRL+C to exit
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    window = MainInspectorWindow()
    app.exec()
