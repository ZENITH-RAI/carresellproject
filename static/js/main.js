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

  function applyAuthState() {
    var signedIn = window.localStorage.getItem("autovalueSignedIn") === "true";
    document.querySelectorAll("[data-guest-link]").forEach(function (link) {
      link.hidden = signedIn;
    });
  }

  applyAuthState();

  var authForm = document.querySelector("[data-auth-form]");
  var emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function clearFormErrors(formEl) {
    formEl.querySelectorAll(".field--error").forEach(function (field) {
      field.classList.remove("field--error");
    });
    formEl.querySelectorAll(".field__error").forEach(function (errorEl) {
      errorEl.textContent = "";
    });
  }

  function setFormError(formEl, name, message) {
    var field = formEl.querySelector('[data-field="' + name + '"]');
    if (!field) return;
    field.classList.add("field--error");
    var errorEl = field.querySelector(".field__error");
    if (errorEl) errorEl.textContent = message;
  }

  function getAuthField(formEl, name) {
    return formEl.elements[name] ? formEl.elements[name].value.trim() : "";
  }

  function validateAuthForm(formEl) {
    var mode = formEl.dataset.authForm;
    var ok = true;
    var email = getAuthField(formEl, "email");
    var password = getAuthField(formEl, "password");

    clearFormErrors(formEl);

    if (mode === "signup" && !getAuthField(formEl, "name")) {
      setFormError(formEl, "name", "Enter your full name");
      ok = false;
    }

    if (!emailPattern.test(email)) {
      setFormError(formEl, "email", "Enter a valid email address");
      ok = false;
    }

    if (password.length < 6) {
      setFormError(formEl, "password", "Use at least 6 characters");
      ok = false;
    }

    if (mode === "signup") {
      var confirmPassword = getAuthField(formEl, "confirm_password");
      if (confirmPassword !== password) {
        setFormError(formEl, "confirm_password", "Passwords do not match");
        ok = false;
      }
    }

    return ok;
  }

  if (authForm) {
    authForm.addEventListener("input", function () {
      validateAuthForm(authForm);
    });

    authForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!validateAuthForm(authForm)) return;

      window.localStorage.setItem("autovalueSignedIn", "true");
      window.localStorage.setItem(
        "autovalueUserEmail",
        getAuthField(authForm, "email"),
      );
      window.location.href = "/";
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
    if (!validate()) {
      e.preventDefault();
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
  });
})();
