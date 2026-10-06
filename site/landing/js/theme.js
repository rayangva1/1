/*
 * Exécuté avant l'affichage (dans <head>, sans defer) pour éviter un saut visuel :
 *  - marque la présence de JavaScript (classe lp-js sur <html>) : les apparitions au défilement et le fondu des
 *    images ne masquent un contenu que lorsque le script peut le révéler ; sans script, tout est visible ;
 *  - applique le choix « Pause des animations » mémorisé (data-animations="pause", WCAG 2.2.2).
 * L'ambiance « Nuit sur le Léman » est toujours sombre : il n'y a plus de choix clair / sombre.
 * Le stockage local peut être indisponible (navigation privée) : on l'ignore alors.
 */
(function () {
  "use strict";
  var html = document.documentElement;
  html.className += (html.className ? " " : "") + "lp-js";
  try {
    if (window.localStorage.getItem("lp-animations") === "pause") {
      html.setAttribute("data-animations", "pause");
    }
  } catch (e) {
    /* stockage indisponible : animations actives (sauf préférence système « réduire les animations ») */
  }
})();
