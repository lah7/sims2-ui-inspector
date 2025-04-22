
# UI Inspector for The Sims 2

**S2UI Inspector** is a homegrown tool to visually inspect and preview
The Sims 2 user interface elements. Written in Python and PyQt6.

![Project Logo](data/icon.svg)


## What's This?

The Sims 2 UI is made up of "UI Script" files inside packages like `ui.package`.
These modified XML files define the layout and parameters of the game's
user interface.

This tool should make it easier to explore the UI, figure out how things work,
as well as to enable modders to visually test their changes outside of the game.

At the moment, it only reads, and there could be some bugs with how elements
are interpreted. Future versions may allow editing and saving changes!

This tool spun off from the [Sims 2 4K UI Patcher](https://github.com/lah7/sims2-4k-ui-patch) project.

![Screenshot of v0.2.0](https://github.com/user-attachments/assets/123c99f7-baa1-4323-bdca-6393aa122d21)


## Download

## Windows

1. Download the [latest release].
2. Extract the folder and run the program. No need to install!

## macOS

We don't have a build yet. See [Development](#development) for a guide to run
directly from the repository.

## Linux

While we do offer builds to download under the [latest release], running from
from the repository will be more efficient disk space wise and provide better
theme integration.

Open the terminal and run these commands.

**For Arch-based distros,** install these dependencies:

    sudo pacman -S --asdeps python-pyqt6 python-pyqt6-webengine python-pillow python-requests python-setproctitle git

**For Ubuntu-based distros,** install these dependencies:

    sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine python3-pil python3-requests python3-setproctitle git

Ubuntu 24.04 LTS (or newer) is recommended. Older versions may not be supported
due to distributing older Python versions.

**Then,** change directory (cd) into a folder to store the code.
We will also need to download modules from another repository for this program to work.

    git clone --recurse-submodules https://github.com/lah7/sims2-ui-inspector.git

Ready to start!

    python3 ./s2ui_inspector.py

To update both repositories for the latest changes:

    cd sims2-ui-inspector
    git pull --recurse-submodules --rebase origin master

[latest release]: https://github.com/lah7/sims2-ui-inspector/releases/latest

## Development

[See above for Linux instructions.](#Linux) For Windows/macOS:

**Prerequisites**

* Install [Python 3.12 (or later)](https://www.python.org/downloads/)
* Install [Git](https://git-scm.com/)

**Initial Setup**

    git clone --recurse-submodules https://github.com/lah7/sims2-ui-inspector.git


**Windows**

Create your virtual environment, activate it, and install the dependencies:

    python -m venv venv
    venv\Scripts\activate
    pip install --upgrade pip
    pip install -r requirements.txt

**macOS/Linux**

    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt

**Running**

    python ./s2ui_inspector.py

**Updating**

    git pull --rebase --recurse-submodules origin master


## What about other Maxis games?

This tool was designed for The Sims 2's UI format. While it _might_ work for
other Maxis games such as SimCity 4, this isn't tested or supported at this time.


## License

[GNU General Public License v3](LICENSE) (GPLv3)
