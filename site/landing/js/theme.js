/*
 * Applique le thème choisi (clair / sombre) avant l'affichage, pour éviter un flash.
 * Sans choix enregistré, le thème suit le réglage du système (prefers-color-scheme).
 * Le stockage local peut être indisponible (navigation privée) : on l'ignore alors.
 */
(function () {
  "use strict";
  try {
    var choix = window.localStorage.getItem("lp-theme");
    if (choix === "light" || choix === "dark") {
      document.documentElement.setAttribute("data-theme", choix);
    }
  } catch (e) {
    /* stockage indisponible : thème automatique */
  }
})();
