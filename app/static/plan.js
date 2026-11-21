// "W planie" switches: count the planned actions, mark the timeline, keep the plan in the URL and the PDF link.
(function () {
  function update() {
    var on = [];
    document.querySelectorAll("[data-plan-switch]").forEach(function (box) {
      var row = box.closest("li");
      if (row) row.classList.toggle("is-planned", box.checked);
      if (box.checked) on.push(box.value);
    });
    document.querySelectorAll("[data-plan-count]").forEach(function (el) { el.textContent = String(on.length); });
    document.querySelectorAll("[data-plan-item]").forEach(function (li) {
      li.classList.toggle("is-planned", on.indexOf(li.getAttribute("data-plan-item")) >= 0);
    });
    var url = new URL(window.location.href);
    if (on.length) url.searchParams.set("plan", on.join(",")); else url.searchParams.delete("plan");
    window.history.replaceState(null, "", url.toString());
    var pdf = document.getElementById("pdf");
    if (pdf) {
      var p = new URL(pdf.getAttribute("data-base"), window.location.origin);
      if (on.length) p.searchParams.set("plan", on.join(",")); else p.searchParams.delete("plan");
      pdf.setAttribute("href", p.pathname + p.search);
    }
  }
  document.addEventListener("click", function (e) {
    if (e.target && e.target.id === "drukuj") window.print();
  });
  document.addEventListener("change", function (e) {
    if (e.target && e.target.matches("[data-plan-switch]")) update();
  });
})();
