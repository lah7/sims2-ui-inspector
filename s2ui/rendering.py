"""
Module to replicate how the game renders images for the UI viewer
as best as we can.
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
import io

import PIL.Image


def render_edge_image(original_io: io.BytesIO, width: int, height: int) -> io.BytesIO:
    """
    Generate a new image replicating how the game renders an image with "edgeimage" set.

    From eye observation, the game uses a "9-slice" technique.
    ┌───┬───┬───┐
    │ 1 │ 2 │ 3 │
    ├───┼───┼───┤
    │ 4 │ 5 │ 6 │
    ├───┼───┼───┤
    │ 7 │ 8 │ 9 │
    └───┴───┴───┘
    (a) Render the corners [1,3,7,9] taking quarters from the original graphic.
    (b) Tile the remaining space along the edges [2,4,6,8] by repeating the image (possibly 4th tile from original)
          However, for simplicity, our code will just "stretch" the last pixels to fill the space.
    (c) Tile the center [5] by repeating the image (possibly 4th tile from original)
          Again, for simplicity, we'll just "stretch" the pixel from the 1th tile in our canvas.

    This is from manual observation, it may be incorrect or inaccurate.

    Good example images:
        - 0x499db772 0xa9500615 (90x186 pixels) - as used for many question dialogs
        - 0x499db772 0x14500100 (90x90 pixels) - as used for "Moving Family" progress dialog
    """
    original = PIL.Image.open(original_io).convert("RGBA")
    canvas = PIL.Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Resize original image if it has odd dimensions
    if original.width % 2 != 0:
        original = original.resize((original.width + 1, original.height))
    if original.height % 2 != 0:
        original = original.resize((original.width, original.height + 1))

    # The corners are painted using the first quarter regions of the original image
    corner_w = original.width // 2
    corner_h = original.height // 2

    # Extract regions from the original image
    # -- Corners
    top_left = original.crop((0, 0, corner_w, corner_h))
    top_right = original.crop((corner_w, 0, original.width, corner_h))
    bottom_left = original.crop((0, corner_h, corner_w, original.height))
    bottom_right = original.crop((corner_w, corner_h, original.width, original.height))

    # -- Edges
    top_edge = original.crop((corner_w, 0, corner_w + 1, corner_h))
    bottom_edge = original.crop((corner_w, corner_h, corner_w + 1, original.height))
    left_edge = original.crop((0, corner_h, corner_w, corner_h + 1))
    right_edge = original.crop((corner_w, corner_h, original.width, corner_h + 1))

    # Stretch the edges to fit the dimensions
    if width - 2 * corner_w > 0:
        top_edge = top_edge.resize((width - 2 * corner_w, corner_h))
        bottom_edge = bottom_edge.resize((width - 2 * corner_w, corner_h))
    if height - 2 * corner_h > 0:
        left_edge = left_edge.resize((corner_w, height - 2 * corner_h))
        right_edge = right_edge.resize((corner_w, height - 2 * corner_h))

    # Paste all regions onto the canvas
    # -- Corners
    canvas.paste(bottom_left, (0, height - corner_h))
    canvas.paste(bottom_right, (width - corner_w, height - corner_h))
    canvas.paste(top_left, (0, 0))
    canvas.paste(top_right, (width - corner_w, 0))

    # -- Edges
    canvas.paste(bottom_edge, (corner_w, height - corner_h))
    canvas.paste(top_edge, (corner_w, 0))
    canvas.paste(left_edge, (0, corner_h))
    canvas.paste(right_edge, (width - corner_w, corner_h))

    # -- Center
    center = original.crop((corner_w, corner_h, corner_w + 1, corner_h + 1))
    if (width - 2 * corner_w) > 0 and (height - 2 * corner_h) > 0:
        center = center.resize((width - 2 * corner_w, height - 2 * corner_h))
    canvas.paste(center, (corner_w, corner_h))

    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output
