/* Report tabs: one part of the farmer report at a time. Without this script every part stays visible. */
(function () {
  var bar = document.querySelector("[data-tabs]");
  var rail = document.querySelector("[data-rail-tabs]");
  if (!bar) return;
  var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-tab-button]"));
  var names = [];
  buttons.forEach(function (b) { var n = b.getAttribute("data-tab-button"); if (names.indexOf(n) < 0) names.push(n); });
  var panels = Array.prototype.slice.call(document.querySelectorAll(".report [data-tab]"));
  var ALIAS = { gmina: "wiarygodnosc", zgodnosc: "wiarygodnosc" };

  function show(name) {
    buttons.forEach(function (b) {
      var on = b.getAttribute("data-tab-button") === name;
      b.setAttribute("aria-selected", on ? "true" : "false");
      b.tabIndex = on ? 0 : -1;
          });
    panels.forEach(function (el) {
      var t = el.getAttribute("data-tab");
      var on = t === name || false;
      el.hidden = !on;
    });
  }

  // hash -> tab: a tab name, an alias, or the id of an element inside a tab
  function fromHash(scroll) {
    var id = decodeURIComponent(location.hash.replace(/^#/, ""));
    var name = names.indexOf(id) >= 0 ? id : ALIAS[id];
    var target = null;
    if (!name && id) {
      target = document.getElementById(id);
      var holder = target && target.closest("[data-tab]");
      name = holder ? holder.getAttribute("data-tab") : null;
    }
    show(names.indexOf(name) >= 0 ? name : "podsumowanie");
    if (target) {
      if (target.tagName === "DETAILS") target.open = true;
      if (scroll) target.scrollIntoView();
    }
  }

  bar.hidden = false;
  if (rail) rail.hidden = false;
  buttons.forEach(function (btn, i) {
    btn.addEventListener("click", function () {
      var name = btn.getAttribute("data-tab-button");
      show(name);
      if (location.hash.replace(/^#/, "") !== name) location.hash = name;
    });
    btn.addEventListener("keydown", function (e) {
      var group = Array.prototype.slice.call(btn.parentNode.querySelectorAll("[data-tab-button]"));
      var i = group.indexOf(btn);
      var d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
      if (e.key === "Home") d = -i;
      if (e.key === "End") d = group.length - 1 - i;
      if (!d) return;
      e.preventDefault();
      var next = group[(i + d + group.length) % group.length];
      show(next.getAttribute("data-tab-button"));
      next.focus();
      location.hash = next.getAttribute("data-tab-button");
    });
  });
  window.addEventListener("hashchange", function () { fromHash(true); });
  fromHash(true);
})();
