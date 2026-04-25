(function () {
  "use strict";

  var AUTOCOMPLETE_URL = "/autocomplete";
  var MAX_SUGGESTIONS = 35;
  var REQUEST_DEBOUNCE_MS = 140;
  var responseCache = new Map();

  function normalize(s) {
    return String(s || "")
      .toLowerCase()
      .trim()
      .replace(/\s+/g, " ");
  }

  function debounce(fn, waitMs) {
    var timer = null;
    return function () {
      var args = arguments;
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        fn.apply(null, args);
      }, waitMs);
    };
  }

  function fetchAutocomplete(query, brand) {
    var q = String(query || "");
    var b = String(brand || "");
    var key = normalize(q) + "::" + normalize(b);

    if (responseCache.has(key)) {
      return Promise.resolve(responseCache.get(key));
    }

    var params = new URLSearchParams();
    params.set("q", q);
    if (b) {
      params.set("brand", b);
    }

    return fetch(AUTOCOMPLETE_URL + "?" + params.toString())
      .then(function (r) {
        if (!r.ok) {
          throw new Error("Autocomplete request failed");
        }
        return r.json();
      })
      .then(function (payload) {
        responseCache.set(key, payload);
        return payload;
      });
  }

  function setStatus(el, msg, isError) {
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isError ? "var(--error)" : "var(--text-muted)";
  }

  function attachCombo(options) {
    var input = options.input;
    var listEl = options.listEl;
    var getItems = options.getItems;
    var onSelect = options.onSelect || function () {};
    var setStatusMessage = options.setStatusMessage || function () {};
    var emptyMessage = options.emptyMessage || "No matches";
    var nullMessage = options.nullMessage || "Choose a brand first";
    var container = input.closest(".combo");
    if (!input || !listEl) return;

    var activeIndex = -1;
    var currentItems = [];
    var requestToken = 0;

    function setOpen(open) {
      listEl.hidden = !open;
      input.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function renderItems(items) {
      listEl.innerHTML = "";
      activeIndex = -1;
      currentItems = items;

      if (items === null) {
        var hint = document.createElement("li");
        hint.className = "combo__empty";
        hint.setAttribute("role", "presentation");
        hint.textContent = nullMessage;
        listEl.appendChild(hint);
        return;
      }

      var slice = items.slice(0, MAX_SUGGESTIONS);
      for (var i = 0; i < slice.length; i++) {
        var li = document.createElement("li");
        var item = slice[i];
        li.setAttribute("role", "option");
        li.id = input.id + "-opt-" + i;
        li.dataset.index = String(i);
        li.dataset.value = item.value;
        li.dataset.source = item.source || "";

        var row = document.createElement("span");
        row.className = "combo__row";

        var value = document.createElement("span");
        value.textContent = item.value;
        row.appendChild(value);

        li.appendChild(row);
        listEl.appendChild(li);
      }

      if (slice.length === 0) {
        var empty = document.createElement("li");
        empty.className = "combo__empty";
        empty.setAttribute("role", "presentation");
        empty.textContent = emptyMessage;
        listEl.appendChild(empty);
      }
    }

    function refreshNow() {
      var thisToken = ++requestToken;
      var q = input.value;

      Promise.resolve(getItems(q))
        .then(function (items) {
          if (thisToken !== requestToken) {
            return;
          }
          if (items === null) {
            renderItems(null);
            return;
          }
          renderItems(Array.isArray(items) ? items : []);
        })
        .catch(function () {
          if (thisToken !== requestToken) {
            return;
          }
          setStatusMessage("Could not load autocomplete suggestions.", true);
          renderItems([]);
        });
    }

    var refreshDebounced = debounce(refreshNow, REQUEST_DEBOUNCE_MS);

    input.addEventListener("input", function () {
      refreshDebounced();
      setOpen(true);
    });

    input.addEventListener("focus", function () {
      refreshNow();
      setOpen(true);
    });

    listEl.addEventListener("click", function (e) {
      var li = e.target.closest("li[role='option']");
      if (!li || !li.dataset.value) return;
      input.value = li.dataset.value;
      var item = currentItems[Number(li.dataset.index)] || null;
      onSelect(item);
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
          refreshNow();
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

    return { refresh: refreshNow, setOpen: setOpen };
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

    function setAutocompleteStatus(message) {
      setStatus(catalogStatus, message, false);
    }

    function mapBrandSuggestions(payload) {
      var seen = new Set();
      var result = [];
      var suggestions = Array.isArray(payload.suggestions)
        ? payload.suggestions
        : [];

      for (var i = 0; i < suggestions.length; i++) {
        var row = suggestions[i];
        var brand = String(row.brand || "").trim();
        if (!brand) {
          continue;
        }
        var key = normalize(brand);
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        result.push({
          value: brand,
          source: row.source || payload.source || "",
        });
      }
      return result;
    }

    function mapModelSuggestions(payload) {
      var suggestions = Array.isArray(payload.suggestions)
        ? payload.suggestions
        : [];
      var mapped = [];

      for (var i = 0; i < suggestions.length; i++) {
        var row = suggestions[i];
        var model = String(row.model || "").trim();
        if (!model) {
          continue;
        }
        mapped.push({
          value: model,
          source: row.source || payload.source || "",
          brand: row.brand || "",
          model: model,
        });
      }

      return mapped;
    }

    var brandCombo = attachCombo({
      input: brandInput,
      listEl: brandList,
      emptyMessage: "No brand matches",
      setStatusMessage: function (msg, isError) {
        setStatus(catalogStatus, msg, isError);
      },
      getItems: function (q) {
        return fetchAutocomplete(q, "").then(function (payload) {
          setAutocompleteStatus("Brand suggestions ready.");
          return mapBrandSuggestions(payload);
        });
      },
      onSelect: function (item) {
        if (!item) return;
        brandInput.dataset.suggestionSource = item.source || "";
        setAutocompleteStatus("Brand selected.");
      },
    });

    var modelCombo = attachCombo({
      input: modelInput,
      listEl: modelList,
      setStatusMessage: function (msg, isError) {
        setStatus(catalogStatus, msg, isError);
      },
      getItems: function (q) {
        var b = brandInput.value.trim();
        if (!b) return null;
        return fetchAutocomplete(q, b).then(function (payload) {
          setAutocompleteStatus("Model suggestions for " + b + " ready.");
          return mapModelSuggestions(payload);
        });
      },
      onSelect: function (item) {
        if (!item) return;
        modelInput.dataset.suggestionSource = item.source || "";
        setAutocompleteStatus("Model selected.");
      },
    });

    function syncModelAfterBrandChange() {
      var b = brandInput.value.trim();
      if (b === lastBrand) return;
      lastBrand = b;
      var mv = modelInput.value.trim();
      if (mv) {
        modelInput.value = "";
        modelInput.dataset.suggestionSource = "";
      }

      if (!b) {
        setStatus(catalogStatus, "Choose a brand first.", false);
      } else {
        setStatus(catalogStatus, "Type a model to get suggestions.", false);
      }

      modelCombo.refresh();
    }

    brandInput.addEventListener("change", syncModelAfterBrandChange);
    brandInput.addEventListener("blur", function () {
      window.setTimeout(syncModelAfterBrandChange, 120);
    });

    setStatus(catalogStatus, "Type to search vehicle brands.", false);
    lastBrand = brandInput.value.trim();
    brandCombo.refresh();
    modelCombo.refresh();

    if (brandInput.value.trim()) {
      setAutocompleteStatus("Brand value set.");
    }

    if (modelInput.value.trim()) {
      setAutocompleteStatus("Model value set.");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
