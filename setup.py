"""
For creating an application build using cx_Freeze.
For maintainer use only.

It is not needed to run the patcher from the repository.
"""
from cx_Freeze import Executable, setup

build_exe_options = {
    "build_exe": "dist",
    "excludes": ["unittest"],
    "includes": ["sims2patcher"],
    "include_files": [
        ("data/icon.ico", "data/icon.ico"),
    ],
    "optimize": "2",
}

setup(
    name="s2ui_inspector",
    version="0.1.0",
    description="UI Inspector for The Sims 2",
    options={"build_exe": build_exe_options},
    executables=[Executable("s2ui_inspector.py", base="gui", icon="data/icon")],
)
