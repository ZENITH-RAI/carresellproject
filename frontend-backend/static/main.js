(function () {
  "use strict";

  // ── Mobile nav toggle ──────────────────────────────────────────────────────
  var nav_button = document.querySelector(".nav-toggle");
  var nav_menu   = document.querySelector(".nav");

  if (nav_button && nav_menu) {
    nav_button.addEventListener("click", function () {
      var is_open = nav_menu.classList.toggle("is-open");
      nav_button.setAttribute("aria-expanded", is_open ? "true" : "false");
    });

    nav_menu.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (window.matchMedia("(max-width: 768px)").matches) {
          nav_menu.classList.remove("is-open");
          nav_button.setAttribute("aria-expanded", "false");
        }
      });
    });
  }

  // ── Stop here if there is no estimate form on this page ───────────────────
  var the_form = document.getElementById("estimate-form");
  if (!the_form) return;

  var submit_button = the_form.querySelector('[type="submit"]');
  var result_card   = document.querySelector(".result-card");
  var price_display = document.querySelector("[data-result-price]");

  // ── Small popup message ────────────────────────────────────────────────────
  function show_toast(message) {
    var old = document.querySelector(".toast");
    if (old) old.remove();

    var toast = document.createElement("div");
    toast.className = "toast toast--success";
    toast.setAttribute("role", "status");
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(function () { toast.classList.add("is-visible"); });
    setTimeout(function () {
      toast.classList.remove("is-visible");
      setTimeout(function () { toast.remove(); }, 400);
    }, 4200);
  }

  // ── Field error helpers ────────────────────────────────────────────────────
  function clear_all_errors() {
    the_form.querySelectorAll(".field--error").forEach(function (f) {
      f.classList.remove("field--error");
    });
    the_form.querySelectorAll(".field__error").forEach(function (span) {
      span.textContent = "";
    });
  }

  function mark_error(field_name, message) {
    var wrapper = the_form.querySelector('[data-field="' + field_name + '"]');
    if (!wrapper) return;
    wrapper.classList.add("field--error");
    var span = wrapper.querySelector(".field__error");
    if (span) span.textContent = message || "Invalid value";
  }

  // ── Validate all fields before sending ────────────────────────────────────
  function validate_form() {
    clear_all_errors();
    var ok = true;

    if (!the_form.brand.value.trim())                                              { mark_error("brand",        "Enter a brand");                    ok = false; }
    if (!the_form.model.value.trim())                                              { mark_error("model",        "Enter a model");                    ok = false; }
    var year = parseInt(the_form.year.value, 10);
    if (isNaN(year) || year < 1980 || year > 2030)                                { mark_error("year",         "Use a year between 1980 and 2030"); ok = false; }
    if (isNaN(parseFloat(the_form.km_driven.value)) || +the_form.km_driven.value < 0) { mark_error("km_driven", "Enter kilometers driven");         ok = false; }
    if (!the_form.fuel.value)                                                      { mark_error("fuel",         "Select a fuel type");               ok = false; }
    if (!the_form.transmission.value)                                              { mark_error("transmission", "Select a transmission type");        ok = false; }
    if (!the_form.seller_type.value)                                               { mark_error("seller_type",  "Select a seller type");             ok = false; }
    if (!the_form.owner.value)                                                     { mark_error("owner",        "Select an owner type");             ok = false; }
    if (isNaN(parseFloat(the_form.mileage.value)) || +the_form.mileage.value <= 0){ mark_error("mileage",      "Enter valid mileage (kmpl)");       ok = false; }
    if (isNaN(parseFloat(the_form.engine.value))  || +the_form.engine.value <= 0) { mark_error("engine",       "Enter engine size (CC)");           ok = false; }
    if (isNaN(parseFloat(the_form.max_power.value))|| +the_form.max_power.value <= 0){ mark_error("max_power", "Enter max power (bhp)");            ok = false; }
    var seats = parseInt(the_form.seats.value, 10);
    if (isNaN(seats) || seats < 2 || seats > 12)                                  { mark_error("seats",        "Enter seats (2–12)");               ok = false; }

    return ok;
  }

  // ── Form submit ────────────────────────────────────────────────────────────
  the_form.addEventListener("submit", function (event) {
    event.preventDefault();  // stop the page from refreshing

    if (!validate_form()) {
      show_toast("Please fix the highlighted fields.");
      return;
    }

    // Show loading state
    if (submit_button) submit_button.disabled = true;
    if (result_card)   result_card.classList.add("is-loading");
    if (price_display) price_display.innerHTML = '<span class="spinner" aria-hidden="true"></span>';

    // Collect all form values into one object
    var car_data = {
      brand:        the_form.brand.value.trim(),
      model:        the_form.model.value.trim(),
      year:         the_form.year.value,
      km_driven:    the_form.km_driven.value,
      fuel:         the_form.fuel.value,
      transmission: the_form.transmission.value,
      seller_type:  the_form.seller_type.value,
      owner:        the_form.owner.value,
      mileage:      the_form.mileage.value,
      engine:       the_form.engine.value,
      max_power:    the_form.max_power.value,
      seats:        the_form.seats.value
    };

    // Send to Flask and wait for the price
    fetch("/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(car_data)
    })
      .then(function (response) { return response.json(); })
      .then(function (result) {
        if (result_card) result_card.classList.remove("is-loading");
        if (submit_button) submit_button.disabled = false;

        if (result.error) {
          if (price_display) price_display.textContent = "—";
          show_toast("Error: " + result.error);
        } else {
          // Show the price Flask sent back
          if (price_display) price_display.textContent = result.price;
          show_toast("Estimate ready!");
        }
      })
      .catch(function () {
        if (result_card)   result_card.classList.remove("is-loading");
        if (submit_button) submit_button.disabled = false;
        if (price_display) price_display.textContent = "—";
        show_toast("Could not reach the server. Is Flask running?");
      });
  });

})();
