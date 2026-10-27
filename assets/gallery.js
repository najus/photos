// photos.sujanthapa.com — v2 features promoted from the UI demo:
// darkroom toggle, story hero, cursor-following album previews,
// Lightbox Pro (ambient colour glow, thumbnail strip, EXIF panel).
(function () {
  /* ---- darkroom toggle (persisted) ---- */
  var themeBtn = document.getElementById("themeBtn");
  function syncThemeBtn() {
    if (themeBtn) themeBtn.textContent = document.documentElement.dataset.theme === "dark" ? "☀️" : "🌑";
  }
  if (themeBtn) {
    syncThemeBtn();
    themeBtn.addEventListener("click", function () {
      var dark = document.documentElement.dataset.theme !== "dark";
      if (dark) document.documentElement.dataset.theme = "dark";
      else delete document.documentElement.dataset.theme;
      try { localStorage.setItem("photos-theme", dark ? "dark" : "light"); } catch (e) {}
      syncThemeBtn();
    });
  }

  /* ---- story hero (home only) ---- */
  var storyEl = document.getElementById("story");
  if (storyEl && window.STORY && window.STORY.length) {
    var img = document.getElementById("storyImg"), segs = document.getElementById("storySegs");
    var title = document.getElementById("storyTitle"), meta = document.getElementById("storyMeta"), count = document.getElementById("storyCount");
    var idx = 0, timer = null, paused = false, slides = window.STORY;
    slides.forEach(function () { segs.appendChild(document.createElement("i")); });
    var showStory = function (i) {
      idx = (i + slides.length) % slides.length;
      var p = slides[idx];
      img.style.animation = "none"; void img.offsetWidth; img.style.animation = "";
      img.src = p.large; img.srcset = p.srcset || ""; img.alt = p.title;
      title.textContent = p.title; meta.textContent = p.meta || "";
      count.textContent = (idx + 1) + " / " + slides.length;
      Array.prototype.forEach.call(segs.children, function (s, k) {
        s.className = k < idx ? "done" : (k === idx ? "playing" : "");
        if (k === idx) { s.style.animation = "none"; void s.offsetWidth; s.style.animation = ""; }
      });
      clearTimeout(timer);
      timer = setTimeout(function () { if (!paused) showStory(idx + 1); }, 6000);
    };
    storyEl.addEventListener("pointerdown", function () { paused = true; storyEl.classList.add("paused"); });
    ["pointerup", "pointerleave"].forEach(function (ev) {
      storyEl.addEventListener(ev, function () { if (paused) { paused = false; storyEl.classList.remove("paused"); showStory(idx + 1); } });
    });
    storyEl.addEventListener("click", function () { showStory(idx + 1); });
    showStory(0);
  }

  /* ---- editorial index: cursor-following cover preview (home only) ---- */
  var prev = document.getElementById("cursorPreview");
  if (prev) {
    var pimg = prev.querySelector("img");
    document.querySelectorAll(".index-row").forEach(function (row) {
      row.addEventListener("mouseenter", function () { pimg.src = row.getAttribute("data-cover"); prev.classList.add("show"); });
      row.addEventListener("mouseleave", function () { prev.classList.remove("show"); });
    });
    document.addEventListener("mousemove", function (e) {
      prev.style.left = Math.min(e.clientX + 24, innerWidth - 310) + "px";
      prev.style.top = Math.max(e.clientY - 95, 8) + "px";
    });
  }

  /* ---- Lightbox Pro ---- */
  var items = Array.prototype.slice.call(document.querySelectorAll(".lb-item"));
  if (!items.length) return;
  var box = document.getElementById("lightbox");
  var limg = box.querySelector("figure img");
  var ltitle = box.querySelector(".lb-title");
  var lexif = box.querySelector(".lb-exif");
  var lcount = box.querySelector(".lb-count");
  var lglow = box.querySelector(".lb-glow");
  var lstrip = box.querySelector(".lb-strip");
  var cur = 0;

  items.forEach(function (a) {
    var t = document.createElement("img");
    var inner = a.querySelector("img");
    t.src = inner ? inner.src : "";
    t.alt = a.getAttribute("data-title") || "";
    lstrip.appendChild(t);
  });
  var thumbs = Array.prototype.slice.call(lstrip.children);
  thumbs.forEach(function (t, k) { t.addEventListener("click", function () { show(k); }); });

  function show(i) {
    cur = (i + items.length) % items.length;
    var a = items[cur];
    limg.src = a.getAttribute("data-large");
    limg.alt = a.getAttribute("data-title") || "";
    ltitle.textContent = a.getAttribute("data-title") || "";
    var ex = a.getAttribute("data-exif"), al = a.getAttribute("data-album");
    lexif.textContent = [al, ex].filter(Boolean).join(" · ");
    var col = a.getAttribute("data-color");
    lglow.style.background = col ? "radial-gradient(circle at 50% 42%, " + col + " 0%, transparent 65%)" : "none";
    lcount.textContent = (cur + 1) + " / " + items.length;
    thumbs.forEach(function (t, k) { t.classList.toggle("on", k === cur); });
    if (thumbs[cur]) thumbs[cur].scrollIntoView({ inline: "center", block: "nearest" });
  }
  function open(i) { box.hidden = false; document.body.style.overflow = "hidden"; show(i); }
  function hide() { box.hidden = true; limg.src = ""; document.body.style.overflow = ""; }

  items.forEach(function (a, i) {
    a.addEventListener("click", function (e) {
      if (e.metaKey || e.ctrlKey || e.shiftKey) return; // let new-tab open the photo page
      e.preventDefault();
      open(i);
    });
  });
  box.querySelector(".lb-close").addEventListener("click", hide);
  box.querySelector(".lb-prev").addEventListener("click", function () { show(cur - 1); });
  box.querySelector(".lb-next").addEventListener("click", function () { show(cur + 1); });
  box.addEventListener("click", function (e) { if (e.target === box) hide(); });
  document.addEventListener("keydown", function (e) {
    if (box.hidden) return;
    if (e.key === "Escape") hide();
    if (e.key === "ArrowLeft") show(cur - 1);
    if (e.key === "ArrowRight") show(cur + 1);
  });
  var tx = null;
  box.addEventListener("touchstart", function (e) { tx = e.touches[0].clientX; }, { passive: true });
  box.addEventListener("touchend", function (e) {
    if (tx === null) return;
    var dx = e.changedTouches[0].clientX - tx;
    if (Math.abs(dx) > 44) show(cur + (dx < 0 ? 1 : -1));
    tx = null;
  }, { passive: true });
})();
