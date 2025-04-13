//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <http://www.gnu.org/licenses/>.
//
// Copyright (C) 2025 Luke Horwell <code (at) horwell (dot) me>
//

// Python Bridge
let python;
new QWebChannel(qt.webChannelTransport, function(channel) {
    python = channel.objects.python;
});

function _initialRender() {
    //
    // Render each element roughly using HTML converted from UI Scripts.
    // Many attributes origin from older Maxis games and may not be used.
    //
    const style = document.createElement("style");
    document.head.appendChild(style);

    document.querySelectorAll(".LEGACY").forEach((element) => {
        const clsid = element.getAttribute("clsid");
        const iid = element.getAttribute("iid");

        // Parse UI script attributes
        const _area = element.getAttribute("area") ? element.getAttribute("area").slice(1, -1).split(',') : [0,0,0,0]; // (startX, startY, endX, endY)
        const area = {
            x: parseInt(_area[0]),
            y: parseInt(_area[1]),
            width: parseInt(_area[2]) - parseInt(_area[0]),
            height: parseInt(_area[3]) - parseInt(_area[1]),
        };

        const _gutters = element.getAttribute("gutters") ? element.getAttribute("gutters") : [0,0,0,0]; // (left, top, right, bottom) or (left/right, top/bottom)
        const gutters = {
            left: parseInt(_gutters[0]),
            top: parseInt(_gutters[1]),
            right: parseInt(_gutters[2]),
            bottom: parseInt(_gutters[3]),
        };

        const _fillcolor = `rgb${element.getAttribute("fillcolor")}`;
        const _bkgcolor = `rgb${element.getAttribute("bkgcolor")}`;
        const background = element.getAttribute("fillcolor") ? _fillcolor : _bkgcolor;
        const forecolor = `rgb${element.getAttribute("forecolor")}`;

        const image = element.getAttribute("image");
        const edgeImage = element.getAttribute("edgeimage");
        const blttype = element.getAttribute("blttype");
        const wparam = element.getAttribute("wparam");

        const caption = element.getAttribute("caption");
        const noShowCaption = element.getAttribute("showcaption") == "no";
        const tips = element.getAttribute("tips") === "yes" || false;
        const align = element.getAttribute("align") || "left"; // left, right, center, lefttop

        // Apply layout
        element.classList.add(element.getAttribute("clsid"));

        // Area
        element.style.position = "absolute";
        element.style.top = `${area.y}px`;
        element.style.left = `${area.x}px`;
        element.style.height = `${area.height}px`;
        element.style.width = `${area.width}px`;

        // Gutters / Padding
        element.style.paddingTop = `${gutters.top}px`;
        element.style.paddingRight = `${gutters.right}px`;
        element.style.paddingBottom = `${gutters.bottom}px`;
        element.style.paddingLeft = `${gutters.left}px`;

        // Colours
        element.style.color = forecolor;
        if (iid === "IGZWinCustom")
            element.style.backgroundColor = background;

        // Caption / Text
        const captionIIDsShown = ["IGZWinText", "GZWinTextEdit", "IGZWinBtn"];
        if (caption && !noShowCaption && caption.search("=") === -1 && captionIIDsShown.includes(iid)) {
            element.innerHTML = element.getAttribute("caption").replaceAll("\\r\\n", "<br>");
            element.style.textAlign = align;
        }

        // Input
        if (iid === "IGZWinTextEdit") {
            const initvalue = element.getAttribute("initvalue") || element.getAttribute("caption") || "";
            const input = document.createElement("textarea");
            input.type = "text";
            input.style.resize = "none";
            input.value = initvalue.replaceAll("\\r\\n", "\n");
            element.style.display = "flex";
            element.appendChild(input);
        }

        // Tooltip
        if (tips)
            element.setAttribute("title", element.getAttribute("tiptext"));

        // Bitmap
        if (image) {
            python.get_image(image, edgeImage === "yes" || blttype === "edge", area.width, area.height, function(b64data) {
                if (!b64data && element.children.length === 0) {
                    element.style.backgroundColor = "red";
                    element.classList.add("missing");
                    return;
                }
                const rule = [`div[image="${image}"] {`];
                rule.push(`background-image: url(data:image/png;base64,${b64data});`);
                switch (blttype) {
                    case "tile":
                        rule.push("background-repeat: repeat;");
                        break;
                    case "normal":
                    case "edge":
                        rule.push("background-repeat: no-repeat;");
                        break;
                }
                rule.push("}");
                style.sheet.insertRule(rule.join(" "), style.sheet.cssRules.length);
            });
        }

        // Fill colour
        if (iid === "IGZWinBMP" && !image && _fillcolor) {
            element.style.backgroundColor = _fillcolor;
        }
    });
}

function _registerMouseEvents() {
    //
    // Handle events when hovering or clicking an element.
    // This ensures only the topmost element is highlighted based on current mouse position.
    //
    function _getTopMostElement(event) {
        const elements = document.elementsFromPoint(event.clientX, event.clientY).filter((el) => el.classList.contains("LEGACY") && !el.classList.contains("hidden"));
        if (elements.length > 0) {
            return elements[0].getAttribute("id");
        }
        return null;
    }

    document.addEventListener("click", function(event) {
        const elementID = _getTopMostElement(event);
        if (elementID) {
            event.stopPropagation();
            python.select_element(elementID);
        }
    });

    document.addEventListener("mousemove", function(event) {
        document.querySelectorAll(".hover").forEach((element) => {
            element.classList.remove("hover");
        });
        const elementID = _getTopMostElement(event);
        if (elementID) {
            event.stopPropagation();
            document.getElementById(elementID).classList.add("hover");
            python.hover_element(elementID);
        } else {
            python.hover_element("");
        }
    });

    document.addEventListener("contextmenu", function(event) {
        event.preventDefault();
        const elementID = _getTopMostElement(event);
        if (elementID) {
            python.select_element(elementID);
            python.right_click_element();
        }
    });
}

function selectElement(id) {
    //
    // Highlight the currently selected item from elements tree.
    //
    document.querySelectorAll(".LEGACY").forEach((element) => {
        element.classList.remove("selected");
        if (element.getAttribute("id") === id) {
            element.classList.add("selected");
        }
    });
}

function hoverElement(id) {
    //
    // Highlight the currently hovered item from elements tree.
    //
    document.querySelectorAll(".LEGACY").forEach((element) => {
        element.classList.remove("hover");
        if (element.getAttribute("id") === id) {
            element.classList.add("hover");
        }
    });
}

function showElement(id) {
    //
    // Explicitly show an element from elements tree previously hidden.
    //
    document.getElementById(id).classList.remove("hidden");
}

function hideElement(id) {
    //
    // Explicitly hide an element from elements tree.
    //
    document.getElementById(id).classList.add("hidden");
}

window.onload = function() {
    // Wait for QWebChannel to be ready
    if (typeof python === "undefined") {
        setTimeout(window.onload, 100);
        return;
    }

    _initialRender();
    _registerMouseEvents();
}
