// Album-grid lightbox: click a thumbnail to view large in place.
// Photo titles still link through to their own /photos/<slug>/ page
// via the caption / normal navigation when JS is off — the anchor's
// href is the photo page; we only intercept plain left-clicks here.
(function () {
  var items = Array.prototype.slice.call(document.querySelectorAll(".lb-item"));
  if (!items.length) return;
  var box = document.getElementById("lightbox");
  var img = box.querySelector("img");
  var cap = box.querySelector("figcaption");
  var idx = 0;

  function show(i) {
    idx = (i + items.length) % items.length;
    var a = items[idx];
    img.src = a.getAttribute("data-large");
    img.alt = a.getAttribute("data-title") || "";
    cap.textContent = a.getAttribute("data-title") || "";
    box.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function hide() {
    box.hidden = true;
    img.src = "";
    document.body.style.overflow = "";
  }
  items.forEach(function (a, i) {
    a.addEventListener("click", function (e) {
      // Let cmd/ctrl/shift clicks open the photo page in a new tab as usual.
      if (e.metaKey || e.ctrlKey || e.shiftKey) return;
      e.preventDefault();
      show(i);
    });
  });
  box.querySelector(".lb-close").addEventListener("click", hide);
  box.querySelector(".lb-prev").addEventListener("click", function () { show(idx - 1); });
  box.querySelector(".lb-next").addEventListener("click", function () { show(idx + 1); });
  box.addEventListener("click", function (e) { if (e.target === box) hide(); });
  document.addEventListener("keydown", function (e) {
    if (box.hidden) return;
    if (e.key === "Escape") hide();
    if (e.key === "ArrowLeft") show(idx - 1);
    if (e.key === "ArrowRight") show(idx + 1);
  });
})();
