/* Legend rows are layer switches: a checkbox shows or hides the SVG group with the same data-layer. */
(function () {
  var svg = document.querySelector(".map svg");
  if (!svg) return;
  document.querySelectorAll("[data-layer-toggle]").forEach(function (box) {
    var key = box.getAttribute("data-layer-toggle");
    var groups = svg.querySelectorAll('[data-layer="' + key + '"]');
    if (!groups.length) { box.disabled = true; return; }
    var saved = null;
    try { saved = sessionStorage.getItem("layer-" + key); } catch (e) { /* storage may be blocked */ }
    if (saved === "off") box.checked = false;
    function apply() {
      groups.forEach(function (g) { g.classList.toggle("layer-off", !box.checked); });
      try { sessionStorage.setItem("layer-" + key, box.checked ? "on" : "off"); } catch (e) { /* ignore */ }
    }
    box.addEventListener("change", apply);
    apply();
  });
})();
