/* A click on the report photo outside the outline asks /api/dzialka for the parcel under that point, draws its
   outline (dashed white) and offers a link to its report with the same date and crop. No libraries.
   pixel -> (lon, lat): the photo is about a kilometre wide, so the affine map through its three corners
   (data-corners-4326: top-left, top-right, bottom-left) is within centimetres of the projection; the same
   arithmetic is app.mapview.px_to_lonlat. The photo and the overlay share one scaled box (.map-pan), so a click is
   first mapped from the screen to photo pixels. A pause of 250 ms over a neighbouring parcel draws its outline dashed. */
(function () {
  "use strict";
  var SVG_NS = "http://www.w3.org/2000/svg";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function pl(ha) { return Number(ha).toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function numbers(text, sep) { return text.split(sep).map(Number); }

  function init(root) {
    if (root.dataset.nbReady) return;
    root.dataset.nbReady = "1";
    var d = root.dataset, svg = root.querySelector("svg"), card = document.querySelector("[data-nb-card]");
    var group = svg && svg.querySelector(".mo-neighbours"), outline = svg && svg.querySelector(".mo-outline");
    if (!svg || !group || !outline || !card) return;
    var width = Number(d.width), height = Number(d.height);
    var c = root.getAttribute("data-corners-4326").split(" ").map(function (p) { return numbers(p, ","); });
    var e1 = [c[1][0] - c[0][0], c[1][1] - c[0][1]], e2 = [c[2][0] - c[0][0], c[2][1] - c[0][1]];
    var det = e1[0] * e2[1] - e1[1] * e2[0];
    var own = outline.getAttribute("points").trim().split(/\s+/).map(function (p) { return numbers(p, ","); });
    var request = 0, controller = null;

    function toLonLat(col, row) {
      var u = col / width, v = row / height;
      return { lon: c[0][0] + u * e1[0] + v * e2[0], lat: c[0][1] + u * e1[1] + v * e2[1] };
    }
    function toPixel(lon, lat) {
      var dx = lon - c[0][0], dy = lat - c[0][1];
      return [(dx * e2[1] - dy * e2[0]) / det * width, (e1[0] * dy - e1[1] * dx) / det * height];
    }
    var pan = root.querySelector(".map-pan") || root;
    function photoPixel(ev) { // screen -> photo pixel: the photo's box (.map-pan) is scaled by one transform
      var box = pan.getBoundingClientRect();
      return [(ev.clientX - box.left) * width / box.width, (ev.clientY - box.top) * height / box.height];
    }
    function insideOwn(p) { // even-odd rule on the outline's pixels
      var inside = false;
      for (var i = 0, j = own.length - 1; i < own.length; j = i++) {
        var a = own[i], b = own[j];
        if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
      }
      return inside;
    }

    function draw(rings) {
      group.textContent = "";
      if (!rings) return;
      var path = "";
      rings.forEach(function (ring) {
        ring.forEach(function (p, i) {
          var q = toPixel(p[0], p[1]);
          path += (i ? "L" : "M") + q[0].toFixed(1) + " " + q[1].toFixed(1);
        });
        path += "Z";
      });
      ["mo-neighbour-casing", "mo-neighbour"].forEach(function (cls) {
        var p = document.createElementNS(SVG_NS, "path");
        p.setAttribute("class", cls); p.setAttribute("fill-rule", "evenodd"); p.setAttribute("d", path);
        group.appendChild(p);
      });
    }
    function close() {
      request++;
      if (controller) controller.abort();
      draw(null);
      card.hidden = true; card.textContent = ""; card.removeAttribute("data-state");
    }
    function show(state, build) {
      card.textContent = ""; card.dataset.state = state; card.hidden = false;
      build(card);
    }
    function closeButton() {
      var b = el("button", "btn--ghost", "Zamknij");
      b.type = "button";
      b.addEventListener("click", close);
      return b;
    }
    function found(a) {
      draw(a.obrys_4326);
      show("found", function (b) {
        b.appendChild(el("b", "nb-title", "Sąsiednia działka " + a.numer + " · obręb " + a.obreb + " · " + pl(a.pow_ha) + " ha"));
        var row = el("div", "nb-actions"), link = el("a", "", "Otwórz raport tej działki");
        link.href = "/raport?dzialka=" + encodeURIComponent(a.dzialka) + "&data=" + encodeURIComponent(d.day) +
          "&uprawa=" + encodeURIComponent(d.crop);
        row.appendChild(link); row.appendChild(closeButton()); b.appendChild(row);
      });
    }
    function fail(message) {
      draw(null);
      show("error", function (b) {
        var p = el("p", "nb-error", message);
        p.setAttribute("role", "alert");
        b.appendChild(p);
        var row = el("div", "nb-actions");
        row.appendChild(closeButton()); b.appendChild(row);
      });
    }

    root.addEventListener("click", function (ev) {
      if (ev.button !== 0) return;
      var px = photoPixel(ev);
      if (px[0] < 0 || px[1] < 0 || px[0] > width || px[1] > height || insideOwn(px)) return;
      var p = toLonLat(px[0], px[1]), mine = ++request;
      if (controller) controller.abort();
      controller = new AbortController();
      draw(null);
      show("loading", function (b) { b.appendChild(el("span", "nb-wait", "Szukam działki…")); });
      fetch("/api/dzialka?lon=" + p.lon.toFixed(7) + "&lat=" + p.lat.toFixed(7), { signal: controller.signal })
        .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
        .then(function (r) {
          if (mine !== request) return;
          if (!r.ok) fail((r.body.bledy && r.body.bledy[0] && r.body.bledy[0].message) || "Nie udało się znaleźć działki w tym miejscu.");
          else if (r.body.dzialka === d.parcel) close();
          else found(r.body);
        })
        .catch(function (e) {
          if (e && e.name === "AbortError") return;
          if (mine === request) fail("Nie mamy odpowiedzi serwera. Spróbuj jeszcze raz.");
        });
    });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !card.hidden && !document.querySelector(".map.is-zoomed-open")) close(); });

    // hover: after a pause of 250 ms the parcel under the pointer is outlined (dashed); no tooltip, no covering of pins
    var hoverGroup = document.createElementNS(SVG_NS, "g"), hoverTimer = null, hoverReq = 0, hoverCtl = null, hoverKey = "";
    hoverGroup.setAttribute("class", "mo-hovers");
    group.parentNode.insertBefore(hoverGroup, group.nextSibling);
    function clearHover() { hoverGroup.textContent = ""; hoverKey = ""; }
    function drawHover(rings) {
      clearHover();
      var path = "";
      rings.forEach(function (ring) {
        ring.forEach(function (p, i) { var q = toPixel(p[0], p[1]); path += (i ? "L" : "M") + q[0].toFixed(1) + " " + q[1].toFixed(1); });
        path += "Z";
      });
      ["mo-hover-casing", "mo-hover"].forEach(function (cls) {
        var e = document.createElementNS(SVG_NS, "path");
        e.setAttribute("class", cls); e.setAttribute("fill-rule", "evenodd"); e.setAttribute("d", path);
        hoverGroup.appendChild(e);
      });
    }
    root.addEventListener("pointermove", function (ev) {
      if (ev.pointerType !== "mouse" || root.classList.contains("is-dragging")) return;
      clearTimeout(hoverTimer);
      var px = photoPixel(ev);
      if (px[0] < 0 || px[1] < 0 || px[0] > width || px[1] > height || insideOwn(px)) { if (hoverKey) clearHover(); return; }
      hoverTimer = setTimeout(function () {
        var p = toLonLat(px[0], px[1]), mine = ++hoverReq;
        if (hoverCtl) hoverCtl.abort();
        hoverCtl = new AbortController();
        fetch("/api/dzialka?lon=" + p.lon.toFixed(7) + "&lat=" + p.lat.toFixed(7), { signal: hoverCtl.signal })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (a) {
            if (mine !== hoverReq || !a || a.dzialka === d.parcel) { if (mine === hoverReq) clearHover(); return; }
            if (a.dzialka !== hoverKey) { drawHover(a.obrys_4326); hoverKey = a.dzialka; }
          })
          .catch(function () { /* hover is optional */ });
      }, 250);
    });
    root.addEventListener("pointerleave", function () { clearTimeout(hoverTimer); hoverReq++; clearHover(); });
    root.addEventListener("click", function () { clearTimeout(hoverTimer); clearHover(); }, true);
  }

  var root = document.querySelector(".map[data-neighbour]");
  if (root) init(root);
})();
