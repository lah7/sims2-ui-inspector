"""
Module that processes the font styles that UI elements will reference.

Font styles are defined in FontStyle.ini, which is a configuration file
that specifies the font face, size, and other properties. This is found
in the base game (and University expansion pack)
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


class FontStyle:
    """
    Serialized interpretation of a line from FontStyle.ini.
    """
    def __init__(self):
        self.font_path: str = ""
        self.font_face: str = ""
        self.size: int = 0
        self.bold: bool = False
        self.underline: bool = False
        self.line_spacing: int = 0
        self.antialiasing_mode: str = ""
        self.xscale: float = 1.0


def parse_font_styles(ini_path: str) -> dict[str, FontStyle]:
    """
    Serialise a font style (.ini) file into a dictionary referencing
    the style name and its properties.

    Expected line format:
    ;    <style name> = <font face name list>, <size>, <style parameters separated by |>, <GUID>

    See FontStyle.ini, which contains comments detailing its specification.
    """
    font_styles: dict[str, FontStyle] = {}

    with open(ini_path, "r", encoding="utf-8") as f:
        reading_group = False
        for line in f.readlines():
            line = line.replace("\t", "").replace("\"", "").strip()

            if line == "[Font Styles]":
                reading_group = True
                continue

            if line.startswith("["):
                reading_group = False

            if not line or line.startswith(";"):
                continue

            if reading_group:
                style_name, values = line.split("=", 1)
                font_face, size, params, guid = values.split(",") # pylint: disable=unused-variable
                params = [p.strip() for p in params.split("|")]

                style = FontStyle()
                style.font_face = font_face.strip()
                style.size = int(size.strip())

                style.bold = "bold" in params
                style.underline = "underline" in params
                for param in params:
                    if param.startswith("aa="):
                        style.antialiasing_mode = param.split("=")[1]
                    elif param.startswith("linespacing="):
                        style.line_spacing = int(param.split("=")[1])
                    elif param.startswith("xscale="):
                        style.xscale = float(param.split("=")[1])

                font_styles[style_name.strip()] = style

    return font_styles


def get_stylesheet(font_styles: dict[str, FontStyle]) -> str:
    """
    Return the font stylesheet for the inspector web view.

    Note that the fonts are not embedded, so it relies on the user
    to have the fonts (or similar ones) installed on their system.
    """
    css = []
    fallbacks = {
        "ITC Benguiat Gothic": ["Benguiat Gothic", "Benguiat Gothic Regular", "ITC Benguiat Gothic Regular", "Varela Round"],
        "HelveticaNeueLT Std Medium": ["Helvetica Neue", "Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"],
    }

    for style_name, font in font_styles.items():
        font_families = [font.font_face] + fallbacks.get(font.font_face, [])
        font_families = ', '.join([f'"{family}"' for family in font_families])
        css.append(f".LEGACY[font='{style_name}'] {{")
        css.append(f"    font-family: {font_families}, sans-serif;")
        css.append(f"    font-size: {font.size}px;")
        css.append(f"    font-weight: {'bold' if font.bold else 'normal'};")
        css.append(f"    text-decoration: {'underline' if font.underline else 'none'};")
        if font.line_spacing:
            css.append(f"    line-height: calc(100% + {font.line_spacing}px);")
            # use height of text?
        if font.xscale != 1.0:
            css.append(f"    transform: scaleX({font.xscale});")
            css.append("    transform-origin: left;")

        # Generic antialiasing
        css.append("    text-rendering: optimizeLegibility;")
        css.append("    -webkit-font-smoothing: antialiased;")
        css.append("}")

    return "\n".join(css)
