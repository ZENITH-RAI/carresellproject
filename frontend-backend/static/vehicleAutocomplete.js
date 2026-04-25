(function () {
  "use strict";

  var CATALOG_URL = "/static/vehicle_catalog.json";
  var MAX_SUGGESTIONS = 35;

  var catalog = null;
  var catalogError = null;

  function normalize(s) {
    return String(s || "")
      .toLowerCase()
      .trim()
      .replace(/\s+/g, " ");
  }

  function scoreMatch(text, query) {
    var t = normalize(text);
    var q = normalize(query);
    if (!q) return 1;
    if (t === q) return 100;
    if (t.startsWith(q)) return 85;
    var words = t.split(" ");
    for (var i = 0; i < words.length; i++) {
      if (words[i].startsWith(q)) return 72;
    }
    if (t.indexOf(q) !== -1) return 55;
    var qi = 0;
    for (var j = 0; j < t.length && qi < q.length; j++) {
      if (t[j] === q[qi]) qi++;
    }
    if (qi === q.length) return 35;
    return 0;
  }

  function filterAndSort(items, query) {
    var scored = [];
    for (var i = 0; i < items.length; i++) {
      var s = scoreMatch(items[i], query);
      if (s > 0) scored.push({ value: items[i], score: s });
    }
    scored.sort(function (a, b) {
      if (b.score !== a.score) return b.score - a.score;
      return a.value.localeCompare(b.value);
    });
    return scored.map(function (x) {
      return x.value;
    });
  }

  function loadCatalog() {
    return fetch(CATALOG_URL)
      .then(function (r) {
        if (!r.ok) throw new Error("Could not load vehicle catalog");
        return r.json();
      })
      .then(function (data) {
        catalog = data;
        catalogError = null;
        return data;
      })
      .catch(function (e) {
        catalogError = e.message || "Load failed";
        throw e;
      });
  }

  function getBrandList() {
    if (!catalog || !catalog.brands) return [];
    return catalog.brands;
  }

  function getModelsForBrand(brand) {
    if (!catalog || !catalog.modelsByBrand) return [];
    var list = catalog.modelsByBrand[brand];
    return Array.isArray(list) ? list : [];
  }

  function attachCombo(options) {
    var input = options.input;
    var listEl = options.listEl;
    var getItems = options.getItems;
    var container = input.closest(".combo");
    if (!input || !listEl) return;

    var activeIndex = -1;

    function setOpen(open) {
      listEl.hidden = !open;
      input.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function renderItems(items) {
      listEl.innerHTML = "";
      activeIndex = -1;
      if (items === null) {
        var hint = document.createElement("li");
        hint.className = "combo__empty";
        hint.setAttribute("role", "presentation");
        hint.textContent = "Choose a brand first";
        listEl.appendChild(hint);
        return;
      }
      var slice = items.slice(0, MAX_SUGGESTIONS);
      for (var i = 0; i < slice.length; i++) {
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.id = input.id + "-opt-" + i;
        li.textContent = slice[i];
        li.dataset.value = slice[i];
        listEl.appendChild(li);
      }
      if (slice.length === 0) {
        var empty = document.createElement("li");
        empty.className = "combo__empty";
        empty.setAttribute("role", "presentation");
        empty.textContent = "No matches";
        listEl.appendChild(empty);
      }
    }

    function refresh() {
      var q = input.value;
      var items = getItems(q);
      renderItems(items);
    }

    input.addEventListener("input", function () {
      refresh();
      setOpen(true);
    });

    input.addEventListener("focus", function () {
      refresh();
      setOpen(true);
    });

    listEl.addEventListener("click", function (e) {
      var li = e.target.closest("li[role='option']");
      if (!li || !li.dataset.value) return;
      input.value = li.dataset.value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      setOpen(false);
      input.focus();
    });

    input.addEventListener("keydown", function (e) {
      var opts = listEl.querySelectorAll("li[role='option']");
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (listEl.hidden) {
          refresh();
          setOpen(true);
        }
        activeIndex = Math.min(activeIndex + 1, opts.length - 1);
        highlight(opts);
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        highlight(opts);
      }
      if (
        e.key === "Enter" &&
        !listEl.hidden &&
        activeIndex >= 0 &&
        opts[activeIndex]
      ) {
        e.preventDefault();
        opts[activeIndex].click();
      }
    });

    function highlight(opts) {
      for (var i = 0; i < opts.length; i++) {
        opts[i].classList.toggle("combo__option--active", i === activeIndex);
        if (i === activeIndex) opts[i].scrollIntoView({ block: "nearest" });
      }
    }

    document.addEventListener("click", function (e) {
      if (container && !container.contains(e.target)) setOpen(false);
    });

    return { refresh: refresh, setOpen: setOpen };
  }

  function setStatus(el, msg, isError) {
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isError ? "var(--error)" : "var(--text-muted)";
  }

  function init() {
    var brandInput = document.getElementById("brand");
    var modelInput = document.getElementById("model");
    var brandList = document.getElementById("brand-listbox");
    var modelList = document.getElementById("model-listbox");
    var catalogStatus = document.getElementById("catalog-status");

    if (!brandInput || !modelInput || !brandList || !modelList) return;

    brandInput.setAttribute("autocomplete", "off");
    modelInput.setAttribute("autocomplete", "off");

    var lastBrand = "";

    var brandCombo = attachCombo({
      input: brandInput,
      listEl: brandList,
      getItems: function (q) {
        if (!catalog) return [];
        var brands = getBrandList();
        if (!normalize(q)) return brands;
        return filterAndSort(brands, q);
      },
    });

    var modelCombo = attachCombo({
      input: modelInput,
      listEl: modelList,
      getItems: function (q) {
        if (!catalog) return [];
        var b = brandInput.value.trim();
        if (!b) return null;
        var models = getModelsForBrand(b);
        if (!normalize(q)) return models.slice(0, MAX_SUGGESTIONS);
        return filterAndSort(models, q);
      },
    });

    function syncModelAfterBrandChange() {
      var b = brandInput.value.trim();
      if (b === lastBrand) return;
      lastBrand = b;
      var models = getModelsForBrand(b);
      var mv = modelInput.value.trim();
      if (mv && models.indexOf(mv) === -1) {
        modelInput.value = "";
      }
      modelCombo.refresh();
    }

    brandInput.addEventListener("change", syncModelAfterBrandChange);
    brandInput.addEventListener("blur", function () {
      window.setTimeout(syncModelAfterBrandChange, 120);
    });

    loadCatalog()
      .then(function () {
        setStatus(
          catalogStatus,
          "Vehicle list ready — " + catalog.brandCount + " brands available.",
          false,
        );
        lastBrand = brandInput.value.trim();
        brandCombo.refresh();
        modelCombo.refresh();
      })
      .catch(function () {
        setStatus(
          catalogStatus,
          "Could not load suggestions. Use a local web server (e.g. python -m http.server) from the frontend folder, or ask your team to rebuild the vehicle list.",
          true,
        );
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
