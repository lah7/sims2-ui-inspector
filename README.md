
# UI Inspector for The Sims 2

**S2UI Inspector** is a homegrown tool to visually inspect and preview
The Sims 2 user interface elements. Written in Python and PyQt6.

![Project Logo](data/icon.svg)


## What's This?

The Sims 2 UI is made up of "UI Script" files inside packages like `ui.package`.
These are modified XML files that define the layout and behaviour of the game's
user interface.

This tool should make it easier to figure out how the UI works, as well as for
modders who wish to visually test their changes without starting the game.

At the moment, it only reads, and there may be some bugs rendering elements.
Future versions may allow editing and saving changes!

This tool spun off from the [Sims 2 4K UI Patcher](https://github.com/lah7/sims2-4k-ui-patch) project.


## Download

The tool is still in development. No releases yet!
However, you can run it locally. See next section for instructions.


## Development

### Prerequisites

* [Python 3.12 (or later)](https://www.python.org/downloads/)
* [Git](https://git-scm.com/)

### Initial Setup

    git clone https://github.com/lah7/sims2-ui-inspector.git
    git clone https://github.com/lah7/sims2-4k-ui-patch.git

This program uses the `sims2patcher` modules from [lah7/sims2-4k-ui-patch](https://github.com/lah7/sims2-4k-ui-patch). Copy the `sims2patcher` folder from `sims2-4k-ui-patch` to `sims2-ui-inspector`.

If you prefer to copy using a command line, on Linux/macOS:

    cp -r sims2-4k-ui-patch/sims2patcher sims2-ui-inspector/

Or for Windows:

    xcopy /E sims2-4k-ui-patch\sims2patcher sims2-ui-inspector\

#### Windows

Create your virtual environment, activate it, and install the dependencies:

    python -m venv venv
    venv\Scripts\activate
    pip install --upgrade pip
    pip install -r requirements.txt

#### Linux/macOS

    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt

### Running

    python ./s2ui_inspector.py


## What about other Maxis games?

This tool was designed for The Sims 2's UI format. While it _might_ work for
other Maxis games such as SimCity 4, this isn't tested nor supported at this time.


## License

[GNU General Public License v3](LICENSE) (GPLv3)
