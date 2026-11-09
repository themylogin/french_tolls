let LatLngBounds;
let Map;
let AdvancedMarkerElement;
let Polyline;
let map;
let from = null;
let to = null;
let fastPath = null;
let optimalPath = null;
let superOptimalPath = null;
let superOptimalStopMarkers = [];
let googlePath = null;
let googleWaypointMarkers = [];
let startMarker = null;
let endMarker = null;
// The journey of the routes on screen. `from` and `to` go null as soon as the
// visitor types in a field, and the dialog must still plan these routes.
let journey = null;
let lastAnswer = null;
let refuelRoute = null;
let refuelController = null;
// The values of the last valid Calculate. Use sends these, so an edit of a field
// after Calculate does not change the plan.
let refuelRequest = null;
let refuelChosen = [];
let refuelStations = [];
let finishedPlan = null;
let planPath = null;
let planMarkers = [];

const Z_FAST = 1;
const Z_GOOGLE = 2;
const Z_PLAN = 3;
const Z_SUPER_OPTIMAL = 4;
const Z_OPTIMAL = 5;

const COLOR_OPTIMAL = "#188038";
const COLOR_FAST = "#0f53ff";
const COLOR_SUPER_OPTIMAL = "#d93025";
const COLOR_PLAN = "#000000";


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

function showRoute(title, color, route, routeName) {
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

    const planned = finishedPlan !== null && finishedPlan.route === routeName;
    const link = planned ? finishedPlan.google_url : route.google_url;

    html.push('<div class="title" style="color: ' + color + ';">' + title);
    if (routeName && link) {
        html.push(
            '<a class="maps-link" href="' + encodeHTML(link) + '"' +
            ' target="_blank" rel="noopener" title="Open in Google Maps">' +
            '<img src="https://www.google.com/images/branding/product/1x/maps_32dp.png"' +
            ' alt="Google Maps" width="16" height="16"></a>');
    }
    if (routeName && finishedPlan === null) {
        html.push(
            '<a class="refuel-link" href="#" data-route="' + routeName + '"' +
            ' title="Find a gas station"><i class="bi bi-fuel-pump"></i></a>');
    } else if (planned) {
        html.push('<span class="refuel-done"><i class="bi bi-fuel-pump"></i></span>');
    }
    html.push('</div>');

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

// Draw the split route beneath the optimal one, and mark where it stops.
function drawSplitRoute(route) {
    if (!route || !route.nodes || !route.nodes.length) {
        return;
    }

    superOptimalPath = showPath(route, COLOR_SUPER_OPTIMAL, 8, Z_SUPER_OPTIMAL);

    superOptimalStopMarkers = (route.stops || []).map(stop =>
        new AdvancedMarkerElement({
            position: { lat: stop.latlon[0], lng: stop.latlon[1] },
            map: map,
            content: waypointDot(COLOR_SUPER_OPTIMAL),
        }));
}

// Draw what Google actually drove, from the key the answer carried.
function drawGoogleRoute(google) {
    if (!google || !google.nodes || !google.nodes.length) {
        return;
    }

    googlePath = showPath(google, "#ff8c00", 16, Z_GOOGLE);

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

function renderRoutes() {
    // The split route is listed first where there is one: it is the cheapest
    // thing on offer, and the panel under it says what it costs.
    const split = lastAnswer.super_optimal
        ? showRoute("Superoptimal route", COLOR_SUPER_OPTIMAL, lastAnswer.super_optimal, "super_optimal")
        : "";
    document.getElementById("routes").innerHTML = (
        split +
        showRoute("Optimal route", COLOR_OPTIMAL, lastAnswer.optimal, "optimal") +
        showRoute("Fastest route", COLOR_FAST, lastAnswer.fast, null)
    );
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
    if (superOptimalPath) {
        superOptimalPath.setMap(null);
        superOptimalPath = null;
    }
    superOptimalStopMarkers.forEach(m => { m.map = null; });
    superOptimalStopMarkers = [];
    if (planPath) {
        planPath.setMap(null);
        planPath = null;
    }
    planMarkers.forEach(m => { m.map = null; });
    planMarkers = [];
    finishedPlan = null;
    if (startMarker) {
        startMarker.map = null;
    }
    if (endMarker) {
        endMarker.map = null;
    }
    document.getElementById("routes").innerHTML = "";
    document.getElementById("error").style.display = "none";

    journey = null;
    lastAnswer = null;
    const requested = { from: from["lonlat"], to: to["lonlat"] };

    fetch('/api/calculate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'from': requested.from,
            'to': requested.to
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
        fastPath = showPath(data.fast, COLOR_FAST, 8, Z_FAST);
        // Red first so it is under the green even before the z-index is read.
        drawSplitRoute(data.super_optimal);
        optimalPath = showPath(data.optimal, COLOR_OPTIMAL, 8, Z_OPTIMAL);

        const bounds = new google.maps.LatLngBounds();
        data.fast.nodes.map(nodeLatLon).forEach(coord => {
            bounds.extend(coord);
        });
        data.optimal.nodes.map(nodeLatLon).forEach(coord => {
            bounds.extend(coord);
        });
        map.fitBounds(bounds);

        lastAnswer = data;
        renderRoutes();
        journey = requested;

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

const CONSUMPTION_LIMITS = "The consumption must be a number more than 0 and less than 30, for example 6.5.";

function refuelField(name) {
    return document.getElementById("refuel-" + name);
}

function parseTankVolume(text) {
    const match = /^\s*(\d{1,18})\s*$/.exec(text);
    if (!match) {
        return null;
    }
    const volume = parseInt(match[1], 10);
    return volume >= 30 ? volume : null;
}

function parseDecimal(text) {
    const match = /^\s*(\d+)(?:[.,](\d+))?\s*$/.exec(text);
    if (!match) {
        return null;
    }
    return parseFloat(match[1] + "." + (match[2] || "0"));
}

function parseConsumption(text) {
    const consumption = parseDecimal(text);
    return consumption !== null && consumption > 0 && consumption < 30 ? consumption : null;
}

function loadStoredCar() {
    try {
        const stored = JSON.parse(localStorage.getItem("car"));
        if (stored && typeof stored === "object") {
            return stored;
        }
    } catch (error) {
        console.log(error);
    }
    return {};
}

function storeCar(car) {
    try {
        localStorage.setItem("car", JSON.stringify(car));
    } catch (error) {
        console.log(error);
    }
}

function storedText(value) {
    return typeof value === "number" && isFinite(value) ? String(value) : "";
}

function fieldFeedback(field) {
    return field.closest(".row").querySelector(".invalid-feedback");
}

// The message spans the whole row, under the label and the field. It is then no
// sibling of the field, so Bootstrap's `.is-invalid ~ .invalid-feedback` does not
// show it, and `d-block` does.
function markField(name, message) {
    const field = refuelField(name);
    field.classList.add("is-invalid");
    fieldFeedback(field).textContent = message;
    fieldFeedback(field).classList.add("d-block");
}

function clearFieldMark(name) {
    const field = refuelField(name);
    field.classList.remove("is-invalid");
    fieldFeedback(field).classList.remove("d-block");
}

function clearFieldMarks() {
    ["tank-volume", "consume-80", "consume-130", "reserve", "reserve-km", "fuel", "range"].forEach(clearFieldMark);
}

// The fuel and the range are two answers to one question: text in one disables the other.
function excludeFuelOrRange() {
    const fuelTyped = refuelField("fuel").value.trim() !== "";
    const rangeTyped = refuelField("range").value.trim() !== "";
    refuelField("range").disabled = fuelTyped;
    refuelField("fuel").disabled = rangeTyped;
    if (fuelTyped) {
        clearFieldMark("range");
    }
    if (rangeTyped) {
        clearFieldMark("fuel");
    }
}

// The checks of `car.parse_car` and of the endpoint, so a visitor sees the
// reason here rather than an error from the server.
function readRefuelForm() {
    clearFieldMarks();

    const tankVolume = parseTankVolume(refuelField("tank-volume").value);
    const fuelType = document.querySelector('input[name="refuel-fuel-type"]:checked').value;
    const consume80 = parseConsumption(refuelField("consume-80").value);
    const consume130 = parseConsumption(refuelField("consume-130").value);
    const reserve = parseDecimal(refuelField("reserve").value);
    const reserveKm = parseDecimal(refuelField("reserve-km").value);
    const fuelText = refuelField("fuel").value.trim();
    const rangeText = refuelField("range").value.trim();
    const fuel = parseDecimal(fuelText);
    const range = parseDecimal(rangeText);

    let valid = true;
    if (tankVolume === null) {
        markField("tank-volume", "The tank volume must be a whole number of 30 or more.");
        valid = false;
    }
    if (consume80 === null) {
        markField("consume-80", CONSUMPTION_LIMITS);
        valid = false;
    }
    if (consume130 === null) {
        markField("consume-130", CONSUMPTION_LIMITS);
        valid = false;
    } else if (consume80 !== null && consume130 < consume80) {
        markField("consume-130",
                  "The consumption at 130 km/h must be equal to or more than the consumption at 80 km/h.");
        valid = false;
    }
    if (reserve === null || (tankVolume !== null && reserve >= tankVolume)) {
        markField("reserve", "The reserve must be a number of 0 or more and less than the tank volume.");
        valid = false;
    }
    if (reserveKm === null || reserveKm > 500) {
        markField("reserve-km", "The range reserve must be a number from 0 to 500 km.");
        valid = false;
    }
    if (!fuelText && !rangeText) {
        markField("fuel", "Enter the fuel in the tank or the range.");
        markField("range", "Enter the fuel in the tank or the range.");
        valid = false;
    } else if (fuelText && (fuel === null || (tankVolume !== null && fuel > tankVolume))) {
        markField("fuel", "The fuel in the tank must be a number from 0 to the tank volume.");
        valid = false;
    } else if (rangeText && (range === null || range > 3000)) {
        markField("range", "The range must be a number from 0 to 3000 km.");
        valid = false;
    }

    if (!valid) {
        return null;
    }
    let start = { range: range };
    if (fuelText) {
        start = { fuel: fuel };
    }
    return {
        car: {
            fuel_type: fuelType,
            tank_volume: tankVolume,
            consume_80: consume80,
            consume_130: consume130,
            reserve: reserve,
            reserve_km: reserveKm,
        },
        start: start,
    };
}

function showRefuelBusy(busy) {
    refuelField("answer").classList.toggle("busy", busy);
    refuelField("calculate").disabled = busy;
    refuelField("result").querySelectorAll(".refuel-use").forEach(button => { button.disabled = busy; });
}

function showRefuelMessage(text, kind) {
    refuelField("result").innerHTML = '<div class="alert alert-' + kind + '">' + encodeHTML(text) + '</div>';
}

function tollText(difference) {
    if (Math.abs(difference) < 0.005) {
        return "";
    }
    const amount = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(Math.abs(difference));
    return (difference > 0 ? "+" : "-") + amount;
}

function detourText(seconds) {
    const minutes = Math.round(seconds / 60);
    return (minutes >= 0 ? "+" : "") + minutes + " min";
}

function showRefuelAnswer(answer) {
    if (!answer.stop_needed && refuelChosen.length) {
        finishPlan(answer);
        return;
    }
    if (!answer.stop_needed && "range_left" in answer) {
        showRefuelMessage("No need to refuel: you'll arrive with " + Math.floor(answer.range_left) + " km of range.",
                          "info");
        return;
    }
    if (!answer.stop_needed) {
        showRefuelMessage("No need to refuel: you'll arrive with " + Math.floor(answer.fuel_left) + " L.", "info");
        return;
    }
    if (!answer.stations.length && "range" in refuelRequest.start && !refuelChosen.length) {
        showRefuelMessage("No gas station sells this fuel within 50 km of the point where the range reaches " +
                          refuelRequest.car.reserve_km + " km.", "info");
        return;
    }
    if (!answer.stations.length) {
        showRefuelMessage("No gas station sells this fuel within 50 km of the point where the tank reaches " +
                          refuelRequest.car.reserve + " L.", "info");
        return;
    }

    const kilometres = new Intl.NumberFormat('fr-FR');
    const price = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
    const rows = answer.stations.map((station, index) => (
        '<tr>' +
        '<td><a href="' + encodeHTML(station.google_url) + '" target="_blank" rel="noopener">' +
        encodeHTML(station.name || "Unnamed station") + '</a>' +
        (station.badge ? ' <b>' + encodeHTML(station.badge) + '</b>' : '') + '</td>' +
        '<td>' + kilometres.format(Math.round(station.distance_from_previous / 1000)) + ' km</td>' +
        '<td>' + price.format(station.price) + ' €/L</td>' +
        '<td>' + detourText(station.detour_duration) + '</td>' +
        '<td>' + tollText(station.toll_difference) + '</td>' +
        '<td><button type="button" class="btn btn-success btn-sm refuel-use" data-index="' + index + '">' +
        'Use</button></td>' +
        '</tr>'
    ));
    refuelStations = answer.stations;
    refuelField("result").innerHTML = '<table class="stations">' + rows.join("") + '</table>';
}

function finishPlan(answer) {
    finishedPlan = { route: refuelRoute, google_url: answer.route.google_url };
    planPath = showPath(answer.route, COLOR_PLAN, 8, Z_PLAN);
    planMarkers = refuelChosen.map(station => new AdvancedMarkerElement({
        position: { lat: station.latitude, lng: station.longitude },
        map: map,
        content: waypointDot(COLOR_PLAN),
    }));
    renderRoutes();
    bootstrap.Modal.getOrCreateInstance(refuelField("dialog")).hide();
}

function openRefuelDialog(routeName) {
    refuelRoute = routeName;

    const car = loadStoredCar();
    refuelField("tank-volume").value = storedText(car.tank_volume);
    const fuelType = ["diesel", "95", "98"].includes(car.fuel_type) ? car.fuel_type : "95";
    refuelField("fuel-type-" + fuelType).checked = true;
    refuelField("consume-80").value = storedText(car.consume_80);
    refuelField("consume-130").value = storedText(car.consume_130);
    refuelField("reserve").value = storedText(car.reserve) || "5";
    refuelField("reserve-km").value = storedText(car.reserve_km) || "50";
    refuelField("fuel").value = "";
    refuelField("range").value = "";
    excludeFuelOrRange();

    clearFieldMarks();
    refuelField("result").innerHTML = "";
    showRefuelBusy(false);

    bootstrap.Modal.getOrCreateInstance(refuelField("dialog")).show();
}

function calculateRefuel() {
    if (refuelController) {
        return;
    }

    const values = readRefuelForm();
    if (!values) {
        return;
    }
    storeCar(values.car);
    refuelRequest = values;
    refuelChosen = [];

    refuelField("result").innerHTML = "";
    sendRefuel();
}

function useStation(index) {
    if (refuelController) {
        return;
    }

    refuelChosen.push(refuelStations[index]);
    sendRefuel();
}

function sendRefuel() {
    showRefuelBusy(true);
    const controller = new AbortController();
    refuelController = controller;

    fetch('/api/refuel', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'from': journey.from,
            'to': journey.to,
            'route': refuelRoute,
            'car': refuelRequest.car,
            ...refuelRequest.start,
            'chosen': refuelChosen.map(station => ({ latitude: station.latitude, longitude: station.longitude }))
        }),
        signal: controller.signal,
    })
    .then(response => {
        if (!response.ok) {
            throw new Error("refuel failed: " + response.status);
        }
        return response.json();
    })
    .then(showRefuelAnswer)
    .catch(error => {
        if (error.name === "AbortError") {
            return;
        }
        console.log(error);
        showRefuelMessage("Error finding gas stations. I am very sorry for that 😞", "danger");
    })
    .finally(() => {
        if (refuelController === controller) {
            refuelController = null;
            showRefuelBusy(false);
        }
    });
}

function closeRefuelDialog() {
    if (refuelController) {
        refuelController.abort();
        refuelController = null;
    }
    refuelChosen = [];
    showRefuelBusy(false);
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

    document.getElementById("routes").addEventListener("click", (event) => {
        const link = event.target.closest(".refuel-link");
        if (!link) {
            return;
        }
        event.preventDefault();
        openRefuelDialog(link.dataset.route);
    });
    refuelField("form").addEventListener("submit", (event) => event.preventDefault());
    refuelField("result").addEventListener("click", (event) => {
        const button = event.target.closest(".refuel-use");
        if (button) {
            useStation(parseInt(button.dataset.index, 10));
        }
    });
    refuelField("fuel").addEventListener("input", excludeFuelOrRange);
    refuelField("range").addEventListener("input", excludeFuelOrRange);
    refuelField("calculate").addEventListener("click", calculateRefuel);
    refuelField("dialog").addEventListener("hide.bs.modal", closeRefuelDialog);

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
