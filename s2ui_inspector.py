#!/usr/bin/env python3
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
import signal
import sys
import webbrowser

import setproctitle
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import (QAction, QColor, QFontDatabase, QIcon, QImage,
                         QKeySequence, QPainter, QPixmap)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QAbstractScrollArea, QApplication, QDialog,
                             QDialogButtonBox, QFileDialog, QHBoxLayout,
                             QMainWindow, QMenu, QMenuBar, QMessageBox,
                             QSplitter, QStatusBar, QTextEdit, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

import s2ui.config
import s2ui.fontstyles
import s2ui.search
import s2ui.widgets
from s2ui.bridge import Bridge, get_image_as_png, get_s2ui_element_id
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
        self.config = s2ui.config.Preferences()
        self.fonts: dict[str, s2ui.fontstyles.FontStyle] = {}
        self.preload_items: list[QTreeWidgetItem] = []

        # Layout
        self.base_widget = QWidget()
        self.base_layout = QHBoxLayout()
        self.base_widget.setLayout(self.base_layout)
        self.setCentralWidget(self.base_widget)

        # Dock: UI Scripts
        # QTreeWidgetItem data columns:
        # - 0: dbpf.Entry
        # - 1: uiscript.UIScriptRoot
        # - 3: str: Checksum of original file
        self.uiscript_dock = s2ui.widgets.DockTree(self, "UI Scripts", 400, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.uiscript_dock.tree.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.uiscript_dock.tree.setHeaderLabels(["Group ID", "Instance ID", "Caption Hint", "Appears in", "Package"])
        self.uiscript_dock.tree.setColumnWidth(0, 120)
        self.uiscript_dock.tree.setColumnWidth(1, 100)
        self.uiscript_dock.tree.setColumnWidth(2, 150)
        self.uiscript_dock.tree.setColumnWidth(3, 130)
        self.uiscript_dock.tree.setColumnWidth(4, 100)
        self.uiscript_dock.tree.setSortingEnabled(True)
        self.uiscript_dock.tree.currentItemChanged.connect(self.inspect_ui_file)

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
        self.elements_dock.toolbar.addAction(self.action_element_visible)

        # Context menus
        self.uiscript_dock.setup_context_menu([self.action_script_src, "|", self.action_copy_ids, self.action_copy_group_id, self.action_copy_instance_id])
        self.elements_dock.setup_context_menu([self.action_element_visible, "|", self.action_copy_element_class, self.action_copy_element_caption, self.action_copy_element_id, self.action_copy_element_pos])
        self.properties_dock.setup_context_menu([self.action_copy_attribute, self.action_copy_value, "|", self.action_similar_attrib, self.action_similar_value, self.action_similar_attribvalue])
        self.context_menu_only_actions = [self.action_similar_attrib, self.action_similar_value, self.action_similar_attribvalue]

        # Status bar
        self.status_bar: QStatusBar = self.statusBar() # type: ignore
        self.status_bar.showMessage("Loading...")

        # UI renderer (HTML-based)
        self.webview = QWebEngineView()
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.default_html = "<style>body { background: #003062; }</style>"
        self.webview.setHtml(self.default_html)
        self.webview_page = self.webview.page() or QWebEnginePage() # 'Or' to satisfy strong type checking
        self.base_layout.addWidget(self.webview)

        # The bridge allows the web view to communicate with Python
        self.channel = QWebChannel()
        self.webview_page.setWebChannel(self.channel)
        self.bridge = Bridge(self.elements_dock.tree, self.elements_dock.context_menu)
        self.channel.registerObject("python", self.bridge)

        # Features
        self.search_dialog = s2ui.search.GlobalSearchDialog(self, self.uiscript_dock.tree, self.elements_dock.tree, self.properties_dock.tree)

        # Window properties
        self.resize(1424, 768)
        self.setWindowTitle("S2UI Inspector")
        self.setWindowIcon(QIcon(os.path.abspath(get_resource("icon.ico"))))
        self.clear_state()
        self.show()
        self.status_bar.showMessage("Ready")
        QApplication.processEvents()

        # Load initial package/game folder
        last_opened_dir = self.config.get_last_opened_dir()

        if len(sys.argv) > 1:
            # When passed as a command line argument
            path = sys.argv[1]
            if os.path.exists(path) and os.path.isdir(path):
                self.discover_files(path)
                self.load_font_styles(path)
                self.load_files()
            elif os.path.exists(path):
                State.file_list = [path]
                self.load_files()
        elif last_opened_dir and os.path.exists(last_opened_dir) and os.path.isdir(last_opened_dir):
            self.discover_files(last_opened_dir)
            self.load_font_styles(last_opened_dir)
            self.load_files()
        else:
            self.browse(open_dir=True)

    def _create_menu_bar(self):
        """Create the actions for the application's menu bar"""
        self.menu_bar = QMenuBar()
        self.setMenuBar(self.menu_bar)

        # === File ===
        self.menu_file = QMenu("&File")
        self.menu_bar.addMenu(self.menu_file)

        self.action_open_dir = QAction(QIcon.fromTheme("document-open-folder"), "&Open Game Folder...")
        self.action_open_dir.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open_dir.triggered.connect(lambda: self.browse(open_dir=True))
        self.menu_file.addAction(self.action_open_dir)

        self.action_open_pkg = QAction(QIcon.fromTheme("document-open"), "Open &Single Package...")
        self.action_open_pkg.setShortcut(QKeySequence.fromString("Ctrl+Shift+O"))
        self.action_open_pkg.triggered.connect(lambda: self.browse(open_dir=False))
        self.menu_file.addAction(self.action_open_pkg)

        self.menu_file.addSeparator()
        self.action_reload = QAction(QIcon.fromTheme("view-refresh"), "&Reload Packages")
        self.action_reload.setShortcut(QKeySequence.StandardKey.Refresh)
        self.action_reload.triggered.connect(self.reload_files)
        self.menu_file.addAction(self.action_reload)

        self.menu_file.addSeparator()
        self.action_exit = QAction(QIcon.fromTheme("application-exit"), "&Exit")
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_exit.triggered.connect(self.close)
        self.menu_file.addAction(self.action_exit)

        # === Edit ===
        self.menu_edit = QMenu("&Edit")
        self.menu_bar.addMenu(self.menu_edit)

        # ... for UI Script dock
        self.action_script_src = QAction(QIcon.fromTheme("format-text-code"), "Show &Original Code")
        self.action_script_src.triggered.connect(self.open_original_code)
        self.menu_edit.addAction(self.action_script_src)

        self.action_copy_ids = QAction(QIcon.fromTheme("edit-copy"), "Copy Group and Instance ID")
        self.action_copy_ids.setShortcut(QKeySequence.fromString("Ctrl+Shift+C"))
        self.action_copy_ids.triggered.connect(lambda: self._copy_to_clipboard(f"{hex(State.current_group_id)} {hex(State.current_instance_id)}"))
        self.menu_edit.addAction(self.action_copy_ids)

        self.action_copy_group_id = QAction(QIcon.fromTheme("edit-copy"), "Copy &Group ID")
        self.action_copy_group_id.triggered.connect(lambda: self._copy_to_clipboard(State.current_group_id))
        self.menu_edit.addAction(self.action_copy_group_id)

        self.action_copy_instance_id = QAction(QIcon.fromTheme("edit-copy"), "Copy &Instance ID")
        self.action_copy_instance_id.triggered.connect(lambda: self._copy_to_clipboard(State.current_instance_id))
        self.menu_edit.addAction(self.action_copy_instance_id)

        # ... for Elements dock
        self.menu_edit.addSeparator()
        self.action_element_visible = QAction(QIcon.fromTheme("view-visible"), "Show &Element")
        self.action_element_visible.setCheckable(True)
        self.action_element_visible.setShortcut(QKeySequence.fromString("Ctrl+E"))
        self.action_element_visible.triggered.connect(self.toggle_element_visibility)
        self.menu_edit.addAction(self.action_element_visible)

        self.action_copy_element_class = QAction(QIcon.fromTheme("edit-copy"), "Copy Element &Class")
        self.action_copy_element_class.triggered.connect(lambda: self._copy_tree_item_to_clipboard(self.elements_dock.tree, 0))
        self.menu_edit.addAction(self.action_copy_element_class)

        self.action_copy_element_caption = QAction(QIcon.fromTheme("edit-copy"), "Copy Element C&aption")
        self.action_copy_element_caption.triggered.connect(lambda: self._copy_tree_item_to_clipboard(self.elements_dock.tree, 1))
        self.menu_edit.addAction(self.action_copy_element_caption)

        self.action_copy_element_id = QAction(QIcon.fromTheme("edit-copy"), "Copy Element &ID")
        self.action_copy_element_id.triggered.connect(lambda: self._copy_tree_item_to_clipboard(self.elements_dock.tree, 2))
        self.menu_edit.addAction(self.action_copy_element_id)

        self.action_copy_element_pos = QAction(QIcon.fromTheme("edit-copy"), "Copy Element &Position")
        self.action_copy_element_pos.triggered.connect(lambda: self._copy_tree_item_to_clipboard(self.elements_dock.tree, 3))
        self.menu_edit.addAction(self.action_copy_element_pos)

        # ... for Properties dock
        self.menu_edit.addSeparator()
        self.action_copy_attribute = QAction(QIcon.fromTheme("edit-copy"), "Copy &Attribute")
        self.action_copy_attribute.triggered.connect(lambda: self._copy_tree_item_to_clipboard(self.properties_dock.tree, 0))
        self.menu_edit.addAction(self.action_copy_attribute)

        self.action_copy_value = QAction(QIcon.fromTheme("edit-copy"), "Copy &Value")
        self.action_copy_value.triggered.connect(lambda: self._copy_tree_item_to_clipboard(self.properties_dock.tree, 1))
        self.menu_edit.addAction(self.action_copy_value)

        # ... Only shown in context menu
        self.action_similar_attrib = QAction(QIcon.fromTheme("edit-find"), "Find elements with this &attribute")
        self.action_similar_attrib.triggered.connect(lambda: self.open_global_search(True, False))
        self.action_similar_attrib.setDisabled(True)

        self.action_similar_value = QAction(QIcon.fromTheme("edit-find"), "Find elements with this &value")
        self.action_similar_value.triggered.connect(lambda: self.open_global_search(False, True))
        self.action_similar_value.setDisabled(True)

        self.action_similar_attribvalue = QAction(QIcon.fromTheme("edit-find"), "Find elements with same attribute/value")
        self.action_similar_attribvalue.triggered.connect(lambda: self.open_global_search(True, True))
        self.action_similar_attribvalue.setDisabled(True)

        # ... Global
        self.menu_edit.addSeparator()
        self.action_global_search = QAction(QIcon.fromTheme("edit-find"), "&Find References...")
        self.action_global_search.setShortcut(QKeySequence.fromString("Ctrl+Shift+F"))
        self.action_global_search.triggered.connect(self.open_global_search)
        self.menu_edit.addAction(self.action_global_search)

        # === View ===
        self.menu_view = QMenu("&View")
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

        self.action_zoom_in = QAction(QIcon.fromTheme("zoom-in"), "Zoom &In")
        self.action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.action_zoom_in.triggered.connect(lambda: self.webview.setZoomFactor(self.webview.zoomFactor() + 0.1))
        self.menu_view.addAction(self.action_zoom_in)

        self.action_zoom_out = QAction(QIcon.fromTheme("zoom-out"), "Zoom &Out")
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

        self.debug_menu = QMenu("&Debug Tools")
        self.debug_menu.setIcon(QIcon.fromTheme("tools"))
        self.menu_view.addMenu(self.debug_menu)
        self.action_debug_inspect = QAction(QIcon.fromTheme("tools-symbolic"), "HTML Web Inspector")
        self.action_debug_inspect.triggered.connect(self.open_web_dev_tools)
        self.debug_menu.addAction(self.action_debug_inspect)

        # === Help ===
        self.menu_help = QMenu("&Help")
        self.menu_bar.addMenu(self.menu_help)

        self.action_online = QAction(QIcon.fromTheme("globe"), "View on &GitHub")
        self.action_online.triggered.connect(lambda: webbrowser.open(PROJECT_URL))
        self.menu_help.addAction(self.action_online)

        self.action_releases = QAction(QIcon.fromTheme("globe"), "View &Releases")
        self.action_releases.triggered.connect(lambda: webbrowser.open(f"{PROJECT_URL}/releases"))
        self.menu_help.addAction(self.action_releases)

        self.menu_help.addSeparator()
        self.action_about_qt = QAction(QIcon.fromTheme("qtcreator"), "About &Qt")
        self.action_about_qt.triggered.connect(lambda: QMessageBox.aboutQt(self))
        self.menu_help.addAction(self.action_about_qt)

        self.action_about_app = QAction(QIcon.fromTheme("help-about"), "&About S2UI Inspector")
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

    def _copy_tree_item_to_clipboard(self, tree: QTreeWidget, column: int):
        """Copy the selected item's text to the clipboard"""
        item = tree.currentItem()
        if item:
            self._copy_to_clipboard(item.text(column))

    def browse(self, open_dir: bool):
        """
        Show the file/folder dialog to select a package file.
        """
        if not open_dir:
            QMessageBox.information(self, "Open Package File", "Graphics may be referenced from other packages. These graphics are only loaded when opening a game directory.")

        browser = QFileDialog(self, "Where is The Sims 2 (and expansions) installed?" if open_dir else "Open Package File")
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
                path = browser.selectedFiles()[0]
                self.discover_files(path)
                self.load_font_styles(path)
            else:
                State.file_list = browser.selectedFiles()

            self.uiscript_dock.tree.setColumnHidden(3, not open_dir)
            self.uiscript_dock.tree.setColumnHidden(4, not open_dir)
            self.load_files()

    def clear_state(self):
        """
        Reset the inspector ready to open new files.
        """
        self.uiscript_dock.tree.clear()

        for action in self.menu_edit.actions() + self.context_menu_only_actions:
            if action.isSeparator():
                continue
            action.setEnabled(False)
        self.action_global_search.setEnabled(True)

        State.graphics = {}
        State.current_group_id = 0x0
        State.current_instance_id = 0x0
        State.game_dir = ""

        self.setWindowTitle("S2UI Inspector")
        self.search_dialog.reset()

    def discover_files(self, path: str):
        """
        Gather a file list of packages containing UI scripts in a game directory.
        """
        self.status_bar.showMessage(f"Discovering files: {path}")
        QApplication.processEvents()
        State.file_list = []
        for filename in ["TSData/Res/UI/ui.package", "TSData/Res/UI/CaSIEUI.data"]:
            State.file_list += glob.glob(f"{path}/**/{filename}", recursive=True)

        if not State.file_list:
            for filename in ["ui.package", "CaSIEUI.data"]:
                State.file_list += glob.glob(f"{path}/**/{filename}", recursive=True)

        if State.file_list:
            self.config.set_last_opened_dir(path)
            State.game_dir = path

    def load_font_styles(self, path: str):
        """
        Locate the game containing font files and load the larger FontStyle.ini.
        The base game contains this, but the University expansion is known to
        provide an updated version of the file.
        """
        ini_path = ""
        ini_size = 0

        for prefix in glob.glob(f"{path}/**/Res/UI/Fonts/", recursive=True):
            _ini_path = os.path.join(prefix, "FontStyle.ini")

            if os.path.exists(_ini_path) and os.path.getsize(_ini_path) > ini_size:
                ini_path = _ini_path
                ini_size = os.path.getsize(_ini_path)

        if not ini_path:
            return QMessageBox.warning(self, "Couldn't load fonts", "FontStyle.ini was not found in this installation. Fonts may not load properly.")

        self.fonts = s2ui.fontstyles.parse_font_styles(ini_path)

    def load_files(self):
        """
        Load all UI scripts found in game directories or single package.
        Group together identical instances of UI scripts, and where they were found.
        """
        root = self.uiscript_dock.tree.invisibleRootItem()
        if not root:
            return

        if not State.file_list:
            self.setWindowTitle("S2UI Inspector")
            QMessageBox.warning(self, "No files found", "No UI files for The Sims 2 were found in the selected folder.")
            return

        self.action_reload.setEnabled(False)
        self.status_bar.showMessage(f"Reading {len(State.file_list)} packages...")
        self.setCursor(Qt.CursorShape.WaitCursor)
        if State.game_dir:
            self.setWindowTitle(f"S2UI Inspector — {State.game_dir}")
        else:
            self.setWindowTitle(f"S2UI Inspector — {State.file_list[0]}")

        QApplication.processEvents()

        # Map identical group and instance IDs to the game(s) and package(s) that use them
        class _File:
            def __init__(self, entry: dbpf.Entry, package: str, game: str):
                self.entry = entry
                self.package = package
                self.game = game

        files: dict[tuple, dict[str, list[_File]]] = {}     # (group_id, instance_id): {checksum: [File, File, ...], ...}

        for package_path in State.file_list:
            package = dbpf.DBPF(package_path)
            package_name = os.path.basename(package_path)
            game_name = package.game_name

            # Create lookup of graphics by group and instance ID
            for entry in package.get_entries_by_type(dbpf.TYPE_IMAGE):
                State.graphics[(entry.group_id, entry.instance_id)] = entry

            # Create list of each instance of UI files
            for entry in package.get_entries_by_type(dbpf.TYPE_UI_DATA):
                key = (entry.group_id, entry.instance_id)
                if key not in files:
                    files[key] = {}

                if entry.decompressed_size > 1024 * 1024:
                    checksum = "Binary data"
                else:
                    checksum = hashlib.md5(entry.data_safe).hexdigest()

                if checksum not in files[key]:
                    files[key][checksum] = []

                file = _File(entry, package_name, game_name)
                files[key][checksum].append(file)

        self.status_bar.showMessage("Populating file tree...")
        QApplication.processEvents()

        def _get_name_label(games: list):
            return f"{len(games)} games" if len(games) > 1 else games[0]

        def _get_package_label(packages: list):
            return f"{len(packages)} packages" if len(packages) > 1 else packages[0]

        # Create tree for each unique instance of UI scripts
        for (group_id, instance_id), checksums in files.items():
            children = []
            package_names: list[str] = []
            game_names: list[str] = []
            only_one = len(checksums) == 1

            for checksum, file_list in checksums.items():
                this_package_names = sorted(set(file.package for file in file_list))
                this_game_names = sorted(set(file.game for file in file_list))
                package_names.extend(this_package_names)
                game_names.extend(this_game_names)
                entry = file_list[0].entry

                item = QTreeWidgetItem([hex(group_id), hex(instance_id), "", _get_name_label(this_game_names), _get_package_label(this_package_names)])
                item.setToolTip(3, "\n".join(this_game_names))
                item.setToolTip(4, "\n".join(this_package_names))
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                item.setData(3, Qt.ItemDataRole.UserRole, checksum)

                if entry.decompressed_size > 1024 * 1024:
                    item.setForeground(0, QColor(Qt.GlobalColor.red))
                    item.setForeground(1, QColor(Qt.GlobalColor.red))
                    item.setToolTip(0, "Cannot read file")
                    item.setToolTip(1, "Cannot read file")
                    item.setDisabled(True)
                else:
                    try:
                        data = uiscript.serialize_uiscript(entry.data.decode("utf-8"))
                        item.setData(1, Qt.ItemDataRole.UserRole, data)
                    except (ValueError, UnicodeDecodeError):
                        item.setForeground(0, QColor(Qt.GlobalColor.red))
                        item.setForeground(1, QColor(Qt.GlobalColor.red))
                        item.setToolTip(0, "Cannot parse file")
                        item.setToolTip(1, "Cannot parse file")
                        item.setDisabled(True)

                children.append(item)

            if only_one:
                self.uiscript_dock.tree.addTopLevelItems(children)
                self.preload_items.append(children[0])
                continue

            game_names = sorted(set(game_names))
            package_names = sorted(set(package_names))
            parent = QTreeWidgetItem([hex(group_id), hex(instance_id), "", _get_name_label(game_names), _get_package_label(package_names)])
            parent.setToolTip(3, "\n".join(game_names))
            parent.setToolTip(4, "\n".join(package_names))
            for child in children:
                parent.addChild(child)
                self.preload_items.append(child)
            self.uiscript_dock.tree.addTopLevelItem(parent)

        self.status_bar.showMessage(f"Loaded {len(self.preload_items)} UI scripts", 3000)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        if self.uiscript_dock.filter.is_filtered():
            self.uiscript_dock.filter.refresh_tree()

        timer = QTimer(self)
        timer.singleShot(1000, self.preload_files)

    def reload_files(self):
        """Reload all files again from disk"""
        self.clear_state()
        self.elements_dock.tree.clear()
        self.properties_dock.tree.clear()
        self.webview.setHtml(self.default_html)
        self.load_files()
        if State.game_dir:
            self.load_font_styles(State.game_dir)

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

            s2ui_element_id = get_s2ui_element_id(element)
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
        data: uiscript.UIScriptRoot = item.data(1, Qt.ItemDataRole.UserRole)

        if not data:
            # Group item, select first child instead
            item.setExpanded(True)
            child = item.child(0)
            self.uiscript_dock.tree.setCurrentItem(child)
            return

        State.current_group_id = entry.group_id
        State.current_instance_id = entry.instance_id

        self.elements_dock.tree.clear()
        self.properties_dock.tree.clear()

        # Render the UI into HTML
        html = self._uiscript_to_html(data)
        with open(get_resource("inspector.html"), "r", encoding="utf-8") as f:
            html = f.read().replace("BODY_PLACEHOLDER", html)
        html = html.replace("/*FONT_PLACEHOLDER*/", s2ui.fontstyles.get_stylesheet(self.fonts))
        self.webview.setHtml(html, baseUrl=QUrl.fromLocalFile(get_resource("")))

        # Update the elements and properties dock
        def _process_element(element: uiscript.UIScriptElement, parent: QTreeWidget|QTreeWidgetItem):
            iid = element.attributes.get("iid", "Unknown")
            caption = element.attributes.get("caption", "")
            element_id = element.attributes.get("id", "")
            area = element.attributes.get("area", "(0,0,0,0)")
            image_attr = element.attributes.get("image", "")

            assert isinstance(iid, str)
            assert isinstance(caption, str)
            assert isinstance(element_id, str)
            assert isinstance(area, str)
            assert isinstance(image_attr, str)

            xpos, ypos, width, height = area.strip("()").split(",")

            item = QTreeWidgetItem(parent, [iid, caption, element_id, f"({xpos}, {ypos})"])
            item.setData(0, Qt.ItemDataRole.UserRole, element)
            item.setData(1, Qt.ItemDataRole.UserRole, True)
            item.setData(2, Qt.ItemDataRole.UserRole, get_s2ui_element_id(element))
            item.setToolTip(1, caption)
            item.setToolTip(2, element_id)
            item.setToolTip(3, f"X: {xpos}\nY: {ypos}\nWidth: {width}\nHeight: {height}")

            if image_attr:
                png = get_image_as_png(image_attr)
                if png is None:
                    pixmap = QPixmap(16, 16)
                    pixmap.fill(Qt.GlobalColor.red)
                    item.setToolTip(0, f"Missing bitmap: {image_attr}")
                    item.setForeground(0, Qt.GlobalColor.red)
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

        for action in self.uiscript_dock.context_menu.actions() + self.properties_dock.context_menu.actions() + self.context_menu_only_actions:
            action.setEnabled(True)

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

        for action in self.elements_dock.context_menu.actions():
            action.setEnabled(True)

        self.action_element_visible.setChecked(item.data(1, Qt.ItemDataRole.UserRole))

        element: uiscript.UIScriptElement = item.data(0, Qt.ItemDataRole.UserRole)
        element_id: str = item.data(2, Qt.ItemDataRole.UserRole)
        self.webview_page.runJavaScript(f"selectElement('{element_id}')")

        self.properties_dock.tree.clear()

        def _add_property(key: str, value: str, has_duplicates: bool):
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
                    assert isinstance(image_attr, str)
                    if image_attr:
                        _group_id, _instance_id = image_attr[1:-1].split(",")
                        group_id = int(_group_id, 16)
                        instance_id = int(_instance_id, 16)
                        subprop1 = QTreeWidgetItem(prop, ["Group ID", hex(group_id)])
                        subprop2 = QTreeWidgetItem(prop, ["Instance ID", hex(instance_id)])
                        if (group_id, instance_id) not in State.graphics:
                            for i in [prop, subprop1, subprop2]:
                                for c in range(0, i.columnCount()):
                                    i.setToolTip(1, "Missing bitmap")
                                    i.setForeground(c, Qt.GlobalColor.red)
                case "font":
                    style_name = element.attributes.get("font", "")
                    assert isinstance(style_name, str)
                    font_style = self.fonts.get(style_name)
                    if font_style:
                        QTreeWidgetItem(prop, ["Font Face", font_style.font_face])
                        QTreeWidgetItem(prop, ["Font Size", str(font_style.size)])
                        QTreeWidgetItem(prop, ["Bold", "Yes" if font_style.bold else "No"])
                        QTreeWidgetItem(prop, ["Underline", "Yes" if font_style.underline else "No"])
                        QTreeWidgetItem(prop, ["Line Spacing", str(font_style.line_spacing)])
                        QTreeWidgetItem(prop, ["Antialiasing Mode", font_style.antialiasing_mode])
                        QTreeWidgetItem(prop, ["Horizontal Scaling", str(font_style.xscale)])

            if key.find("color") != -1 and len(value.split(",")) == 3: # (R, G, B)
                _color = value[1:-1].split(",")
                pixmap = QPixmap(16, 16)
                pixmap.fill(QColor.fromRgb(int(_color[0]), int(_color[1]), int(_color[2])))
                prop.setIcon(1, QIcon(pixmap))

            if has_duplicates:
                for c in range(0, prop.columnCount()):
                    prop.setForeground(c, Qt.GlobalColor.yellow)

            prop.setExpanded(True)

        for key, value in element.attributes.items():
            if isinstance(value, str):
                _add_property(key, value, False)
            elif isinstance(value, list):
                for v in value:
                    _add_property(key, v, True)

        if self.properties_dock.filter.is_filtered():
            self.properties_dock.filter.refresh_tree()

    def preload_files(self):
        """
        Continue loading files in the background to identify captions.
        """
        self.action_reload.setEnabled(False)
        while self.preload_items:
            item = self.preload_items.pop(0)
            entry: dbpf.Entry = item.data(0, Qt.ItemDataRole.UserRole)
            data: uiscript.UIScriptRoot = item.data(1, Qt.ItemDataRole.UserRole)

            if entry.decompressed_size > 1024 * 1024:
                item.setText(2, "Binary data")
                item.setDisabled(True)
                continue

            if not data:
                continue

            # Try finding elements with user-facing captions
            matches = []
            for iid in ["IGZWinText", "IGZWinTextEdit", "IGZWinBtn", "IGZWinFlatRect", "IGZWinBMP", "IGZWinGen"]:
                elements = data.get_elements_by_attribute("iid", iid)
                for element in elements:
                    caption = element.attributes.get("caption", "")
                    if isinstance(caption, str):
                        matches.append(caption)

                # Exclude captions used for technical key/value data
                # e.g. Ignore lowercase text, and things like "kCollapsedRows=1"
                matches = [match.replace("\\r\\n", " ") for match in matches if (not match.find("=") != -1 and not match.isupper()) and not match.islower() and match != ""]

                if matches:
                    break

            if matches:
                # Use first found caption as the hint
                item.setText(2, matches[0])
                item.setToolTip(2, "\n".join(matches))

                # For grouped items, update the parent
                parent = item.parent()
                if parent:
                    parent.setText(2, max(matches, key=len))
                    parent.setToolTip(2, "\n".join(matches))

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

    def toggle_element_visibility(self):
        """
        Toggle the visibility of the currently selected element.
        """
        item = self.elements_dock.tree.currentItem()
        if not item:
            return

        element_id = item.data(2, Qt.ItemDataRole.UserRole)
        visible = not item.data(1, Qt.ItemDataRole.UserRole)
        item.setData(1, Qt.ItemDataRole.UserRole, visible)
        item.setIcon(2, QIcon.fromTheme("view-hidden") if not visible else QIcon())

        if visible:
            self.webview_page.runJavaScript(f"showElement('{element_id}')")
        else:
            self.webview_page.runJavaScript(f"hideElement('{element_id}')")

        # De-emphasise the text and descendants
        for child in [item] + s2ui.widgets.iterate_children(item):
            _seen = [child.data(1, Qt.ItemDataRole.UserRole)]
            parent = child.parent()
            while parent:
                _seen.append(parent.data(1, Qt.ItemDataRole.UserRole))
                parent = parent.parent()

            for c in range(0, child.columnCount()):
                if all(_seen):
                    child.setData(c, Qt.ItemDataRole.ForegroundRole, None)
                else:
                    child.setForeground(c, Qt.GlobalColor.gray)

    def open_global_search(self, prefill_attrib=False, prefill_value=False):
        """
        Open a dialog to search for data across all UI scripts.
        Optionally, with prefilled attribute and/or value.
        """
        if not self.search_dialog.isVisible():
            self.search_dialog.show()
            self.search_dialog.raise_()
            self.search_dialog.activateWindow()

        current_item = self.properties_dock.tree.currentItem()
        if current_item:
            if prefill_attrib and prefill_value:
                self.search_dialog.search_box_attrib.setText(current_item.text(0))
                self.search_dialog.search_box_value.setText(current_item.text(1))
            elif prefill_attrib:
                self.search_dialog.search_box_attrib.setText(current_item.text(0))
                self.search_dialog.search_box_value.setText("")
            elif prefill_value:
                self.search_dialog.search_box_attrib.setText("")
                self.search_dialog.search_box_value.setText(current_item.text(1))
            self.search_dialog.search()


if __name__ == "__main__":
    setproctitle.setproctitle("s2ui-inspector")

    # CTRL+C to exit
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    window = MainInspectorWindow()
    app.exec()
