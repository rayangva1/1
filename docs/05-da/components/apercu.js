/*
 * Barre d'aperçu des pages de démonstration DA : direction (A/B) et mode (auto/clair/sombre).
 * Paramètres d'URL acceptés : ?da=a|b&theme=light|dark. Aucun suivi, aucun appel réseau.
 * Ne pas inclure ce script dans la boutique : la direction retenue y sera fixée une fois pour toutes.
 */
(function () {
  "use strict";
  var root = document.documentElement;

  function setAttr(name, value) {
    if (value) { root.setAttribute(name, value); } else { root.removeAttribute(name); }
  }

  try {
    var params = new URLSearchParams(window.location.search);
    var da = params.get("da");
    var theme = params.get("theme");
    if (da === "a" || da === "b") { setAttr("data-da", da); }
    if (theme === "light" || theme === "dark") { setAttr("data-theme", theme); }
  } catch (e) { /* URL non lisible : on garde les valeurs du document */ }

  function sync() {
    var currentDa = root.getAttribute("data-da") || "a";
    var currentTheme = root.getAttribute("data-theme") || "auto";
    document.querySelectorAll("[data-set-da]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-set-da") === currentDa));
    });
    document.querySelectorAll("[data-set-theme]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-set-theme") === currentTheme));
    });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-set-da],[data-set-theme]");
    if (!button) { return; }
    if (button.hasAttribute("data-set-da")) { setAttr("data-da", button.getAttribute("data-set-da")); }
    if (button.hasAttribute("data-set-theme")) {
      var value = button.getAttribute("data-set-theme");
      setAttr("data-theme", value === "auto" ? "" : value);
    }
    try {
      var url = new URL(window.location.href);
      url.searchParams.set("da", root.getAttribute("data-da") || "a");
      if (root.getAttribute("data-theme")) { url.searchParams.set("theme", root.getAttribute("data-theme")); }
      else { url.searchParams.delete("theme"); }
      window.history.replaceState(null, "", url.toString());
    } catch (e) { /* file:// ou navigateur restrictif : l'aperçu fonctionne quand même */ }
    sync();
    document.dispatchEvent(new CustomEvent("da:change"));
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();
