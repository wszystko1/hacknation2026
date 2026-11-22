/* The report map: frames the whole outline (margin 8%), keeps pins and slope arrows at a fixed screen size,
   and opens the same map as a full-screen overlay with a 1x-3x slider, dragging, Esc, "Zamknij", +/-.
   The photo and the SVG live in one box (.map-pan) that is scaled by one transform, so they never drift apart.
   Also: a loading overlay after a click that fetches a parcel ("Oceń działkę", "To ta działka", a neighbour's link). No libraries. */
(function () {
  "use strict";
  var MARGIN = 0.08, MAX_FIT = 4;

  /* ---------------- loading overlay (also used on the start screen) ---------------- */
  var busy = null, busyTimer = null;
  function showBusy(retry) {
    if (!busy) {
      busy = document.createElement("div");
      busy.className = "busy";
      busy.setAttribute("role", "status");
      busy.setAttribute("aria-live", "polite");
      busy.innerHTML = '<div class="busy-box"><span class="busy-text"></span></div>';
      document.body.appendChild(busy);
    }
    var box = busy.firstChild, text = box.querySelector(".busy-text");
    box.className = "busy-box";
    text.textContent = "Pobieranie danych działki … i liczenie oceny (do ok. 20 s)";
    var old = box.querySelector("button"); if (old) old.remove();
    busy.hidden = false;
    clearTimeout(busyTimer);
    busyTimer = setTimeout(function () {
      box.className = "busy-box is-late";
      text.textContent = "Trwa dłużej niż zwykle. Dane państwowe mogą odpowiadać wolno.";
      var b = document.createElement("button"); b.type = "button"; b.textContent = "Spróbuj jeszcze raz";
      b.addEventListener("click", function () { busy.hidden = true; retry(); });
      box.appendChild(b);
    }, 30000);
  }
  window.addEventListener("pageshow", function () { if (busy) busy.hidden = true; clearTimeout(busyTimer); });
  var START = /^(Oceń działkę|To ta działka)$/;
  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (!(f instanceof HTMLFormElement) || ev.defaultPrevented) return;
    if (f.matches(".pick, .pick form, [data-busy-form]") || f.querySelector(".pick button, button.btn--primary")) {
      if (busy && !busy.hidden) { ev.preventDefault(); return; }
      setTimeout(function () { showBusy(function () { f.submit(); }); }, 0);
    }
  }, true);
  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("a, button") : null;
    if (!t) return;
    if (busy && !busy.hidden) { ev.preventDefault(); return; }
    if (t.tagName === "A" && /^\/raport\?/.test(t.getAttribute("href") || "") && t.closest("[data-nb-card]")) {
      var href = t.href;
      setTimeout(function () { showBusy(function () { location.href = href; }); }, 0);
    } else if (t.tagName === "BUTTON" && START.test(t.textContent.trim()) && !t.closest("form.pick, .pick")) {
      showBusy(function () { t.click(); });
    }
  }, true);

  /* ---------------- map framing and zoom ---------------- */
  var map = document.querySelector(".map[data-neighbour]");
  if (!map) return;
  var pan = map.querySelector(".map-pan"), svg = map.querySelector("svg");
  if (!pan || !svg) return;
  var W = Number(map.dataset.width), H = Number(map.dataset.height);
  var bb = map.dataset.outlineBbox.split(",").map(Number); // x0, y0, x1, y1 of the outline
  var strip = map.querySelector(".map-strip"), col = map.closest(".mapcol");
  var openBtn = map.querySelector("[data-zoom-open]"), closeBtn = map.querySelector("[data-zoom-close]");
  var range = map.querySelector("#map-zoom-range"), value = map.querySelector("[data-zoom-value]");
  var tools = map.querySelector(".map-zoom-tools"), zlegend = map.querySelector(".map-zoom-legend"), chip = map.querySelector(".map-chip");
  var st = { s: 1, tx: 0, ty: 0, k: 1, open: false }, fixed = svg.querySelectorAll("[data-fixed]");
  map.classList.add("is-fit");
  pan.style.width = W + "px"; pan.style.height = H + "px";
  fixed.forEach(function (g) { g.dataset.base = g.getAttribute("transform") || ""; });

  function fmt(k) { return k.toFixed(1).replace(".", ",") + "×"; }
  function fitScale() {
    var box = map.getBoundingClientRect(), reserve = strip ? strip.offsetHeight : 0;
    var availH = Math.max(box.height - reserve, 80);
    var ow = Math.max(bb[2] - bb[0], 1), oh = Math.max(bb[3] - bb[1], 1);
    var s = Math.min(box.width * (1 - 2 * MARGIN) / ow, availH * (1 - 2 * MARGIN) / oh);
    return { s: Math.min(s, MAX_FIT), w: box.width, h: availH };
  }
  function apply() {
    var f = fitScale(), s = f.s * st.k;
    var cx = (bb[0] + bb[2]) / 2, cy = (bb[1] + bb[3]) / 2;
    if (!st.moved) { st.tx = f.w / 2 - cx * s; st.ty = f.h / 2 - cy * s; }
    else { st.tx = st.px - cx * s; st.ty = st.py - cy * s; }
    st.s = s;
    pan.style.transform = "translate(" + st.tx.toFixed(2) + "px," + st.ty.toFixed(2) + "px) scale(" + s.toFixed(5) + ")";
    fixed.forEach(function (g) { g.setAttribute("transform", g.dataset.base + " scale(" + (1 / s).toFixed(5) + ")"); });
    map.classList.toggle("is-zoomed", st.k > 1.001);
  }
  function setZoom(k, keepCentre) {
    k = Math.min(3, Math.max(1, Math.round(k * 10) / 10));
    if (k === st.k) return;
    var box = map.getBoundingClientRect(), f = fitScale();
    if (st.moved || keepCentre) { // keep the screen centre of the visible area where it is
      var mx = box.width / 2, my = f.h / 2;
      var ix = (mx - st.tx) / st.s, iy = (my - st.ty) / st.s;
      st.k = k; var s = f.s * k;
      st.moved = true; st.px = mx - ix * s + ((bb[0] + bb[2]) / 2) * s; st.py = my - iy * s + ((bb[1] + bb[3]) / 2) * s;
    } else { st.k = k; }
    if (range) range.value = k;
    if (value) value.textContent = fmt(k);
    apply();
  }
  function open() {
    if (st.open) return;
    st.open = true; st.k = 1; st.moved = false;
    map.classList.add("is-zoomed-open");
    if (col) col.classList.add("has-zoom");
    [tools, zlegend, closeBtn].forEach(function (e) { if (e) e.hidden = false; });
    if (range) range.value = 1; if (value) value.textContent = fmt(1);
    document.body.style.overflow = "hidden";
    apply();
    if (closeBtn) closeBtn.focus();
  }
  function close() {
    if (!st.open) return;
    st.open = false; st.k = 1; st.moved = false;
    map.classList.remove("is-zoomed-open", "is-dragging");
    if (col) col.classList.remove("has-zoom");
    [tools, zlegend, closeBtn].forEach(function (e) { if (e) e.hidden = true; });
    document.body.style.overflow = "";
    apply();
    if (openBtn) openBtn.focus();
  }
  if (openBtn) openBtn.addEventListener("click", function (ev) { ev.stopPropagation(); open(); });
  if (closeBtn) closeBtn.addEventListener("click", function (ev) { ev.stopPropagation(); close(); });
  if (range) range.addEventListener("input", function () { setZoom(Number(range.value), true); });
  document.addEventListener("keydown", function (ev) {
    if (!st.open) return;
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); close(); }
    else if (ev.key === "+" || ev.key === "=") { ev.preventDefault(); setZoom(st.k + 0.2, true); }
    else if (ev.key === "-" || ev.key === "_") { ev.preventDefault(); setZoom(st.k - 0.2, true); }
  }, true);
  // a click on the dark margin of the overlay (outside the photo) closes it; a drag does not
  var drag = null;
  map.addEventListener("pointerdown", function (ev) {
    if (!st.open || ev.target.closest(".map-strip") || ev.button !== 0) return;
    drag = { x: ev.clientX, y: ev.clientY, tx: st.tx, ty: st.ty, moved: false };
    try { map.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
  });
  map.addEventListener("pointermove", function (ev) {
    if (!drag) return;
    var dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true; map.classList.add("is-dragging");
    var cx = (bb[0] + bb[2]) / 2, cy = (bb[1] + bb[3]) / 2;
    st.moved = true; st.px = drag.tx + dx + cx * st.s; st.py = drag.ty + dy + cy * st.s;
    apply();
  });
  function end(ev) {
    if (!drag) return;
    var wasDrag = drag.moved; drag = null; map.classList.remove("is-dragging");
    if (wasDrag) { window.__mapDragged = true; setTimeout(function () { window.__mapDragged = false; }, 0); return; }
    if (st.open && ev.type === "pointerup") {
      var r = pan.getBoundingClientRect();
      if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) close();
    }
  }
  map.addEventListener("pointerup", end);
  map.addEventListener("pointercancel", end);
  map.addEventListener("click", function (ev) { if (window.__mapDragged) { ev.stopImmediatePropagation(); } }, true);
  window.addEventListener("resize", function () { st.moved = false; apply(); });
  apply();
  // fonts and layout settle after load; refit once more
  window.addEventListener("load", function () { apply(); });
  window.__mapFit = { state: st, apply: apply };
})();
