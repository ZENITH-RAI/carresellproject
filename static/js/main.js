(function () {
  "use strict";

  var navToggle = document.querySelector(".nav-toggle");
  var nav = document.querySelector(".nav");

  if (navToggle && nav) {
    navToggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (window.matchMedia("(max-width: 768px)").matches) {
          nav.classList.remove("is-open");
          navToggle.setAttribute("aria-expanded", "false");
        }
      });
    });
  }

  var form = document.getElementById("estimate-form");
  if (!form) return;

  var submitBtn = form.querySelector('[type="submit"]');
  var resultCard = document.querySelector(".result-card");
  var priceEl = document.querySelector("[data-result-price]");

  function showToast(message) {
    var existing = document.querySelector(".toast");
    if (existing) existing.remove();

    var t = document.createElement("div");
    t.className = "toast toast--success";
    t.setAttribute("role", "status");
    t.textContent = message;
    document.body.appendChild(t);
    requestAnimationFrame(function () {
      t.classList.add("is-visible");
    });
    setTimeout(function () {
      t.classList.remove("is-visible");
      setTimeout(function () {
        t.remove();
      }, 400);
    }, 4200);
  }

  function clearFieldErrors() {
    form.querySelectorAll(".field--error").forEach(function (f) {
      f.classList.remove("field--error");
    });
    form.querySelectorAll(".field__error").forEach(function (e) {
      e.textContent = "";
    });
  }

  function setFieldError(name, msg) {
    var wrap = form.querySelector('[data-field="' + name + '"]');
    if (!wrap) return;
    wrap.classList.add("field--error");
    var err = wrap.querySelector(".field__error");
    if (err) err.textContent = msg || "Invalid value";
  }

  function validate() {
    clearFieldErrors();
    var ok = true;

    var brand = form.brand.value.trim();
    var model = form.model.value.trim();
    var year = parseInt(form.year.value, 10);
    var km = parseFloat(form.km_driven.value);
    var mileage = parseFloat(form.mileage.value);
    var engine = parseFloat(form.engine.value);
    var maxPower = parseFloat(form.max_power.value);
    var seats = parseInt(form.seats.value, 10);

    if (!brand) {
      setFieldError("brand", "Enter a brand");
      ok = false;
    }
    if (!model) {
      setFieldError("model", "Enter a model");
      ok = false;
    }
    if (isNaN(year) || year < 1980 || year > 2030) {
      setFieldError("year", "Use a year between 1980 and 2030");
      ok = false;
    }
    if (isNaN(km) || km < 0) {
      setFieldError("km_driven", "Enter kilometers driven");
      ok = false;
    }
    if (isNaN(mileage) || mileage <= 0) {
      setFieldError("mileage", "Enter valid mileage (kmpl)");
      ok = false;
    }
    if (isNaN(engine) || engine <= 0) {
      setFieldError("engine", "Enter engine size (CC)");
      ok = false;
    }
    if (isNaN(maxPower) || maxPower <= 0) {
      setFieldError("max_power", "Enter max power (bhp)");
      ok = false;
    }
    if (isNaN(seats) || seats < 2 || seats > 12) {
      setFieldError("seats", "Enter seats (2–12)");
      ok = false;
    }

    return ok;
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!validate()) {
      showToast("Please fix the highlighted fields.");
      return;
    }

    if (submitBtn) submitBtn.disabled = true;
    if (resultCard) {
      resultCard.classList.add("is-loading");
      if (priceEl) {
        priceEl.innerHTML = '<span class="spinner" aria-hidden="true"></span>';
      }
    }

    window.setTimeout(function () {
      if (resultCard) resultCard.classList.remove("is-loading");
      if (priceEl) {
        priceEl.textContent = "—";
      }
      if (submitBtn) submitBtn.disabled = false;
      showToast(
        "Form submitted. Connect the pricing service to show a live estimate here.",
      );
    }, 650);
  });
})();
