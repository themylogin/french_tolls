let LatLngBounds;
let Map;
let AdvancedMarkerElement;
let Polyline;
let map;
let from = null;
let to = null;
let fastPath = null;
let optimalPath = null;
let googlePath = null;
let googleWaypointMarkers = [];
let startMarker = null;
let endMarker = null;


function encodeHTML(str) {
    return str.replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#039;");
}

function nodeLatLon(n) {
    return { lat: n[1], lng: n[0] };
}

function waypointDot(color) {
    const dot = document.createElement("div");
    dot.style.width = "12px";
    dot.style.height = "12px";
    dot.style.borderRadius = "50%";
    dot.style.background = color;
    dot.style.border = "2px solid white";
    dot.style.boxShadow = "0 0 3px rgba(0,0,0,0.5)";
    return dot;
}

function markerIcon(url) {
    const img = document.createElement("img");
    img.src = url;
    img.width = 32;
    img.height = 32;
    return img;
}

function showPath(route, color, weight, zIndex) {
    const pathCoordinates = route.nodes.map(nodeLatLon);

    let polyline = new Polyline({
        path: pathCoordinates,
        geodesic: true,
        strokeColor: color,
        strokeOpacity: 1.0,
        strokeWeight: weight === undefined ? 8 : weight,
        zIndex: zIndex === undefined ? 1 : zIndex,
    });
    polyline.setMap(map);
    return polyline;
}

// What to show in a passage's cost cell.
function peageCost(peage) {
    if (peage.cost === null || peage.cost === undefined) {
        return '<span class="unpriced">× €</span>';
    }

    return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })
        .format(peage.cost);
}

function showRoute(title, color, route) {
    let html = ['<div class="route">'];

    html.push('<div class="info">');

    html.push('<div class="time">');
    if (route.duration >= 3600) {
        html.push(Math.floor(route.duration / 3600).toString() + "h ");
    }
    html.push(Math.floor(route.duration % 3600 / 60).toString() + "min");
    html.push('</div>');

    if (route.cost) {
        html.push('<div class="price">');
        html.push(new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(route.cost));
        html.push('</div>');
    }

    html.push('<div class="distance">');
    html.push(new Intl.NumberFormat('fr-FR').format(Math.round(route.distance / 1000)) + " km");
    html.push('</div>');

    html.push('</div>');

    html.push('<div class="title" style="color: ' + color + ';">' + title + '</div>');

    html.push('<div style="clear: both;"></div>');

    if (route.peages) {
        html.push('<table>');
        for (var i = 0; i < route.peages.length; i++) {
            html.push('<tr>');
            html.push('<td class="small gray"><div>' + route.peages[i].name + '</div></td>');
            html.push('<td class="small gray">' + peageCost(route.peages[i]) + '</td>');
            html.push('</tr>');
        }
        html.push('</table>');
    }

    html.push('</div>');
    return html.join("");
}

// Draw what Google actually drove, from the key the answer carried.
function drawGoogleRoute(google) {
    if (!google || !google.nodes || !google.nodes.length) {
        return;
    }

    googlePath = showPath(google, "#ff8c00", 16, 2);

    const added = (google.added || []).map(w => w.join(","));
    googleWaypointMarkers = (google.waypoints || []).map(w => {
        const isAdded = added.includes(w.join(","));
        return new AdvancedMarkerElement({
            position: nodeLatLon(w),
            map: map,
            content: waypointDot(isAdded ? "#8e24aa" : "#ff8c00"),
        });
    });
}

function calculate() {
    const calculateButton = document.getElementById("calculate");
    const calculating = document.getElementById("calculating");
    calculateButton.style.display = "none";
    calculating.style.display = "block";

    if (fastPath) {
        fastPath.setMap(null);
    }
    if (googlePath) {
        googlePath.setMap(null);
        googlePath = null;
    }
    googleWaypointMarkers.forEach(m => { m.map = null; });
    googleWaypointMarkers = [];
    if (optimalPath) {
        optimalPath.setMap(null);
    }
    if (startMarker) {
        startMarker.map = null;
    }
    if (endMarker) {
        endMarker.map = null;
    }
    document.getElementById("routes").innerHTML = "";
    document.getElementById("error").style.display = "none";

    fetch('/api/calculate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'from': from["lonlat"],
            'to': to["lonlat"]
        }),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error();
        }
        return response.json();
    })
    .then(data => {
        startMarker = new AdvancedMarkerElement({
            position: nodeLatLon(data.fast.nodes[0]),
            map: map,
            content: markerIcon("https://maps.google.com/mapfiles/ms/icons/green-dot.png"),
        });
        endMarker = new AdvancedMarkerElement({
            position: nodeLatLon(data.fast.nodes[data.fast.nodes.length - 1]),
            map: map,
            content: markerIcon("https://maps.google.com/mapfiles/ms/icons/red-dot.png"),
        });
        fastPath = showPath(data.fast, "#0f53ff", 8, 1);
        optimalPath = showPath(data.optimal, "#188038", 8, 3);

        const bounds = new google.maps.LatLngBounds();
        data.fast.nodes.map(nodeLatLon).forEach(coord => {
            bounds.extend(coord);
        });
        data.optimal.nodes.map(nodeLatLon).forEach(coord => {
            bounds.extend(coord);
        });
        map.fitBounds(bounds);

        const from_name = from["name"].replace(", France", "");
        const to_name = to["name"].replace(", France", "");
        document.getElementById("routes").innerHTML = (
            showRoute("Optimal route", "#188038", data.optimal) +
            showRoute("Fastest route", "#0f53ff", data.fast)
        );

        drawGoogleRoute(data.google);

        calculateButton.style.display = "block";
        calculating.style.display = "none";
    })
    .catch(error => {
        console.log(error);
        calculateButton.style.display = "block";
        calculating.style.display = "none";
        document.getElementById("error").style.display = "block";
    });
}

const AUTOCOMPLETE_ENDPOINT = "/api/autocomplete";
const AUTOCOMPLETE_DEBOUNCE = 500;
const AUTOCOMPLETE_MIN_LENGTH = 3;

const AUTOCOMPLETE_PIN = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#5f6368">' +
    '<path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5' +
    'a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z"/></svg>');

function injectAutocompleteStyles() {
    if (document.getElementById("pac-styles")) {
        return;
    }

    const style = document.createElement("style");
    style.id = "pac-styles";
    style.textContent = [
        ".pac-wrap { position: relative; }",
        ".pac-container { position: absolute; top: 100%; left: 0; right: 0; z-index: 1100;",
        "  margin-top: 2px; background: #fff; border-radius: 8px; overflow: hidden;",
        "  box-shadow: 0 2px 6px rgba(0, 0, 0, .3); display: none;",
        "  font-family: Roboto, Arial, sans-serif; text-align: left; }",
        ".pac-container.pac-open { display: block; }",
        ".pac-item { display: flex; align-items: flex-start; gap: 12px; padding: 8px 16px; cursor: pointer; }",
        ".pac-item:hover, .pac-item.pac-item-selected { background-color: #f5f5f5; }",
        ".pac-icon { flex: 0 0 20px; width: 20px; height: 20px; opacity: .75;",
        "  background: url(\"" + AUTOCOMPLETE_PIN + "\") no-repeat center / contain; }",
        ".pac-text { min-width: 0; }",
        ".pac-item-query { font-size: 14px; line-height: 20px; color: #202124;",
        "  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
        ".pac-matched { font-weight: 700; }",
        ".pac-secondary { font-size: 12px; line-height: 16px; color: #5f6368;",
        "  white-space: normal; overflow-wrap: anywhere; }",
        ".pac-attribution { padding: 4px 16px 6px; font-size: 10px; line-height: 12px;",
        "  color: #9aa0a6; text-align: right; }",
    ].join("\n");
    document.head.appendChild(style);
}

function foldText(text) {
    return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function highlightMatch(text, query) {
    const folded = foldText(text);
    const needles = foldText(query).trim().split(/\s+/).filter(Boolean);

    for (let i = 0; i < needles.length; i++) {
        const index = folded.indexOf(needles[i]);
        if (index >= 0) {
            const length = needles[i].length;
            return encodeHTML(text.substring(0, index)) +
                   '<span class="pac-matched">' + encodeHTML(text.substr(index, length)) + '</span>' +
                   encodeHTML(text.substring(index + length));
        }
    }

    return encodeHTML(text);
}

function createAutocomplete(inputId, onPlace) {
    injectAutocompleteStyles();

    const input = document.getElementById(inputId);
    input.setAttribute("autocomplete", "off");

    const wrap = document.createElement("div");
    wrap.className = "pac-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    const container = document.createElement("div");
    container.className = "pac-container";
    wrap.appendChild(container);

    let predictions = [];
    let selectedIndex = -1;
    let debounceTimer = null;
    let controller = null;
    let lastQuery = null;

    function close() {
        container.classList.remove("pac-open");
        selectedIndex = -1;
    }

    function render(query) {
        if (!predictions.length) {
            container.innerHTML = "";
            close();
            return;
        }

        const html = predictions.map((prediction, i) => (
            '<div class="pac-item' + (i === selectedIndex ? ' pac-item-selected' : '') + '" data-index="' + i + '">' +
            '<div class="pac-icon"></div>' +
            '<div class="pac-text">' +
            '<div class="pac-item-query">' + highlightMatch(prediction.main_text, query) + '</div>' +
            (prediction.secondary_text
                ? '<div class="pac-secondary">' + encodeHTML(prediction.secondary_text) + '</div>'
                : '') +
            '</div>' +
            '</div>'
        ));
        html.push('<div class="pac-attribution">Search by LocationIQ</div>');

        container.innerHTML = html.join("");
        container.classList.add("pac-open");
    }

    function select(index) {
        const prediction = predictions[index];
        if (!prediction) {
            return;
        }

        input.value = prediction.name;
        lastQuery = prediction.name;
        predictions = [];
        close();

        onPlace({
            "name": prediction.name,
            "lonlat": prediction.lonlat
        });
        input.classList.remove("is-invalid");
    }

    function fetchPredictions(query) {
        if (controller) {
            controller.abort();
        }
        controller = new AbortController();

        fetch(AUTOCOMPLETE_ENDPOINT + "?q=" + encodeURIComponent(query), { signal: controller.signal })
            .then(response => {
                if (!response.ok) {
                    throw new Error("autocomplete failed");
                }
                return response.json();
            })
            .then(data => {
                predictions = Array.isArray(data) ? data : [];
                selectedIndex = -1;
                render(query);
            })
            .catch(error => {
                if (error.name === "AbortError") {
                    return;
                }
                console.log(error);
                predictions = [];
                close();
            });
    }

    input.addEventListener("input", () => {
        const query = input.value.trim();
        if (query === lastQuery) {
            return;
        }
        lastQuery = query;

        onPlace(null);

        clearTimeout(debounceTimer);
        if (query.length < AUTOCOMPLETE_MIN_LENGTH) {
            if (controller) {
                controller.abort();
                controller = null;
            }
            predictions = [];
            close();
            return;
        }

        debounceTimer = setTimeout(() => fetchPredictions(query), AUTOCOMPLETE_DEBOUNCE);
    });

    input.addEventListener("keydown", (event) => {
        if (!container.classList.contains("pac-open")) {
            return;
        }

        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            const delta = event.key === "ArrowDown" ? 1 : -1;
            const slots = predictions.length + 1;
            selectedIndex = (selectedIndex + 1 + delta + slots) % slots - 1;
            render(input.value.trim());
        } else if (event.key === "Enter") {
            if (selectedIndex >= 0) {
                event.preventDefault();
                select(selectedIndex);
            }
        } else if (event.key === "Escape") {
            close();
        }
    });

    container.addEventListener("mousedown", (event) => {
        const item = event.target.closest(".pac-item");
        if (!item) {
            return;
        }
        event.preventDefault();
        select(parseInt(item.dataset.index, 10));
    });

    input.addEventListener("blur", () => setTimeout(close, 0));

    input.addEventListener("focus", () => {
        if (predictions.length) {
            render(input.value.trim());
        }
    });

    return input;
}

async function initMap() {
    const position = { lat: 47, lng: 3 };
    const maps = await google.maps.importLibrary("maps");
    LatLngBounds = maps.LatLngBounds;
    Map = maps.Map;
    Polyline = maps.Polyline;
    const marker = await google.maps.importLibrary("marker");
    AdvancedMarkerElement = marker.AdvancedMarkerElement;

    map = new Map(document.getElementById("map"), {
        zoom: 6,
        center: position,
        mapId: "259422e959f1c47544c2b76c",
    });

    const from_autocomplete = createAutocomplete("from", (place) => {
        from = place;
    });
    const to_autocomplete = createAutocomplete("to", (place) => {
        to = place;
    });

    document.getElementById("collapse-control").addEventListener("click", () => {
        document.body.classList.toggle("collapsed");
    });

    document.getElementById("calculate").addEventListener("click", () => {
        if (!from)
        {
            document.getElementById("from").classList.add("is-invalid");
            return;
        }
        if (!to)
        {
            document.getElementById("to").classList.add("is-invalid");
            return;
        }

        document.location.hash = encodeURI(JSON.stringify({"from": from, "to": to}));

        calculate();
    });

    if (document.location.hash.toString().length > 1)
    {
        const decoded = JSON.parse(decodeURIComponent(document.location.hash.toString().substring(1)));
        if (decoded)
        {
            from = decoded.from;
            to = decoded.to;

            from_autocomplete.value = from.name;
            to_autocomplete.value = to.name;
            calculate();
        }
    }
}

initMap();
