/* Map for pointing at a parcel on the start screen. No libraries: 256 px tiles from our own server
   (/mapa/kafel), drag to pan, +/- buttons and the wheel to zoom, a click asks /api/dzialka for the parcel
   under the point and draws its outline. Web Mercator: world pixel = 256 * 2^z * (lon + 180) / 360. */
(function () {
  "use strict";
  var TILE = 256, MIN_Z = 9, MAX_Z = 19, ORTHO_FROM = 9, DRAG_PX = 5, WHEEL_GAP_MS = 100, KEY_PAN_PX = 120;
  var START = { lon: 19.15, lat: 52.05, z: 9 }; // the middle of Poland, where the photo has no empty corners
  var BOUNDS = { w: 14.0, e: 24.3, s: 48.9, n: 55.0 }; // the map centre stays inside this frame (no empty photo outside the country)
  var SVG_NS = "http://www.w3.org/2000/svg";

  function size(z) { return TILE * Math.pow(2, z); }
  function toWorld(lon, lat, z) {
    var s = size(z);
    return { x: (lon + 180) / 360 * s, y: (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * s };
  }
  function toLonLat(x, y, z) {
    var s = size(z);
    return { lon: x / s * 360 - 180, lat: Math.atan(Math.sinh(Math.PI * (1 - 2 * y / s))) * 180 / Math.PI };
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function pl(ha) { return Number(ha).toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

  function PickMap(root) {
    var self = this, tilesBox = root.querySelector(".pm-tiles"), shape = root.querySelector(".pm-shape");
    var stateBox = root.querySelector(".pm-state"), field = document.getElementById("f-dzialka");
    var casing = document.createElementNS(SVG_NS, "path"), line = document.createElementNS(SVG_NS, "path");
    casing.setAttribute("class", "mo-casing"); line.setAttribute("class", "mo-outline");
    casing.setAttribute("fill-rule", "evenodd"); line.setAttribute("fill-rule", "evenodd");
    shape.appendChild(casing); shape.appendChild(line);
    var c = toWorld(START.lon, START.lat, START.z);
    var z = START.z, cx = c.x, cy = c.y, w = 1, h = 1;
    var tiles = {}, rings = null, request = 0, lastWheel = 0, frame = 0, controller = null;

    function origin() { return { x: Math.round(cx - w / 2), y: Math.round(cy - h / 2) }; }

    function render() {
      frame = 0;
      w = root.clientWidth; h = root.clientHeight;
      var o = origin(), n = Math.pow(2, z), wanted = {};
      var x0 = Math.max(0, Math.floor(o.x / TILE)), x1 = Math.min(n - 1, Math.floor((o.x + w) / TILE));
      var y0 = Math.max(0, Math.floor(o.y / TILE)), y1 = Math.min(n - 1, Math.floor((o.y + h) / TILE));
      for (var x = x0; x <= x1; x++) {
        for (var y = y0; y <= y1; y++) {
          var key = z + "/" + x + "/" + y;
          wanted[key] = true;
          if (!tiles[key]) {
            var img = new Image(TILE, TILE);
            img.alt = ""; img.draggable = false; img.className = "pm-tile";
            img.src = "/mapa/kafel/" + (z >= ORTHO_FROM ? "orto" : "podklad") + "/" + key + ".jpg";
            tilesBox.appendChild(img);
            tiles[key] = img;
          }
          tiles[key].style.transform = "translate(" + (x * TILE - o.x) + "px," + (y * TILE - o.y) + "px)";
        }
      }
      Object.keys(tiles).forEach(function (key) {
        if (!wanted[key]) { tilesBox.removeChild(tiles[key]); delete tiles[key]; }
      });
      shape.setAttribute("viewBox", "0 0 " + w + " " + h);
      var d = "";
      (rings || []).forEach(function (ring) {
        ring.forEach(function (p, i) {
          var q = toWorld(p[0], p[1], z);
          d += (i ? "L" : "M") + (q.x - o.x).toFixed(1) + " " + (q.y - o.y).toFixed(1);
        });
        d += "Z";
      });
      casing.setAttribute("d", d); line.setAttribute("d", d);
      var m = toLonLat(cx, cy, z);
      root.dataset.zoom = z; root.dataset.lon = m.lon.toFixed(6); root.dataset.lat = m.lat.toFixed(6);
    }
    function redraw() { if (!frame) frame = requestAnimationFrame(render); }

    function clamp() {
      var a = toWorld(BOUNDS.w, BOUNDS.n, z), b = toWorld(BOUNDS.e, BOUNDS.s, z);
      cx = Math.min(b.x, Math.max(a.x, cx)); cy = Math.min(b.y, Math.max(a.y, cy));
    }
    function zoomBy(step, px, py) { // keeps the point under (px, py) in place
      var nz = Math.min(MAX_Z, Math.max(MIN_Z, z + step));
      if (nz === z) return;
      var f = Math.pow(2, nz - z), dx = px - w / 2, dy = py - h / 2;
      cx = (cx + dx) * f - dx; cy = (cy + dy) * f - dy; z = nz;
      clamp(); render();
    }
    function pan(dx, dy) {
      cx -= dx; cy -= dy; clamp();
      redraw();
    }

    function setState(kind, build) {
      stateBox.textContent = "";
      stateBox.dataset.state = kind;
      build(stateBox);
    }
    function hint() { setState("empty", function (b) { b.appendChild(el("p", "pm-hint", "Przybliż i kliknij pole albo wpisz numer")); }); }
    function clear() { rings = null; request++; if (controller) controller.abort(); hint(); render(); }
    function fail(message) {
      rings = null; render();
      setState("error", function (b) { var p = el("p", "pm-error", message); p.setAttribute("role", "alert"); b.appendChild(p); });
    }
    function found(a) {
      rings = a.obrys_4326; render();
      setState("found", function (b) {
        var card = el("div", "pm-card");
        card.appendChild(el("b", "pm-title", "Działka " + a.numer + " · obręb " + a.obreb + " · " + pl(a.pow_ha) + " ha"));
        var row = el("div", "pm-actions"), yes = el("button", "", "To ta działka"), no = el("button", "btn--ghost", "Wskaż inną");
        yes.type = "button"; no.type = "button";
        yes.addEventListener("click", function () {
          if (field) { field.value = a.dzialka; field.dispatchEvent(new Event("input", { bubbles: true })); }
          var next = document.getElementById("f-data");
          if (next) next.focus();
        });
        no.addEventListener("click", function () { clear(); root.focus(); });
        row.appendChild(yes); row.appendChild(no); card.appendChild(row); b.appendChild(card);
      });
    }

    function pickAt(px, py) {
      var o = origin(), p = toLonLat(o.x + px, o.y + py, z), mine = ++request;
      if (controller) controller.abort();
      controller = new AbortController();
      rings = null; render();
      setState("loading", function (b) { var p2 = el("p", "pm-card", "Szukam działki…"); b.appendChild(p2); });
      fetch("/api/dzialka?lon=" + p.lon.toFixed(7) + "&lat=" + p.lat.toFixed(7), { signal: controller.signal })
        .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
        .then(function (r) {
          if (mine !== request) return;
          if (r.ok) found(r.body);
          else fail((r.body.bledy && r.body.bledy[0] && r.body.bledy[0].message) || "Nie udało się znaleźć działki. Wpisz jej numer.");
        })
        .catch(function (e) {
          if (e && e.name === "AbortError") return;
          if (mine === request) fail("Nie mamy odpowiedzi serwera. Wpisz numer działki.");
        });
    }

    // drag to pan; a press that moves less than DRAG_PX is a click
    root.addEventListener("pointerdown", function (e) {
      if (e.button !== 0 || e.target.closest(".pm-ui")) return;
      var sx = e.clientX, sy = e.clientY, lx = sx, ly = sy, moved = false;
      root.classList.add("is-grabbing");
      function move(ev) {
        if (!moved && Math.hypot(ev.clientX - sx, ev.clientY - sy) >= DRAG_PX) moved = true;
        if (moved) pan(ev.clientX - lx, ev.clientY - ly);
        lx = ev.clientX; ly = ev.clientY;
      }
      function up(ev) {
        window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
        window.removeEventListener("pointercancel", up);
        root.classList.remove("is-grabbing");
        if (!moved && ev.type === "pointerup") { var r = root.getBoundingClientRect(); pickAt(ev.clientX - r.left, ev.clientY - r.top); }
      }
      window.addEventListener("pointermove", move); window.addEventListener("pointerup", up); window.addEventListener("pointercancel", up);
    });
    root.addEventListener("wheel", function (e) {
      e.preventDefault();
      var now = Date.now();
      if (now - lastWheel < WHEEL_GAP_MS) return; // one step per notch, not per trackpad event
      lastWheel = now;
      var r = root.getBoundingClientRect();
      zoomBy(e.deltaY < 0 ? 1 : -1, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    root.querySelectorAll("[data-zoom]").forEach(function (b) {
      b.addEventListener("click", function () { zoomBy(Number(b.dataset.zoom), w / 2, h / 2); });
    });
    root.addEventListener("keydown", function (e) {
      if (e.target !== root) return;
      var moves = { ArrowLeft: [KEY_PAN_PX, 0], ArrowRight: [-KEY_PAN_PX, 0], ArrowUp: [0, KEY_PAN_PX], ArrowDown: [0, -KEY_PAN_PX] };
      if (moves[e.key]) pan(moves[e.key][0], moves[e.key][1]);
      else if (e.key === "+" || e.key === "=") zoomBy(1, w / 2, h / 2);
      else if (e.key === "-") zoomBy(-1, w / 2, h / 2);
      else if (e.key === "Enter") pickAt(w / 2, h / 2);
      else return;
      e.preventDefault();
    });
    window.addEventListener("resize", redraw);
    self.render = render;
    hint(); render();
  }

  function init() {
    document.querySelectorAll("[data-pickmap]:not([data-ready])").forEach(function (root) {
      root.setAttribute("data-ready", "1");
      new PickMap(root);
    });
  }
  init();
  if (!window.__pickmapListening) {
    window.__pickmapListening = true;
    document.addEventListener("DOMContentLoaded", init);
    document.addEventListener("htmx:load", init); // the form replaces the page body: start again on the new map
  }
})();
