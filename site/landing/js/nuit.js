/*
 * Ambiance « Nuit sur le Léman » — effets visuels de la landing et des maquettes (docs/05-da/DIRECTION_NUIT.md).
 *
 * - Images de marque (balises data-visuel) : fondu à l'arrivée ; la scène qui les porte reçoit la classe a-visuel
 *   (le décor CSS/SVG de secours n'est alors plus peint : pas de seconde lune ni d'étoiles par-dessus la peinture).
 *   Si une image ne charge pas, elle est masquée et le décor de secours reste visible (jamais d'icône cassée).
 * - Boutons « Pause des animations » (WCAG 2.2.2, en-tête et pied de page) : mettent en pause toutes les
 *   animations, choix mémorisé si possible.
 * - Apparitions au défilement (IntersectionObserver), en-tête opaque après défilement, survol 3D des panneaux
 *   « verre », rail des formats accessible au clavier, question fréquente ouverte quand un lien y mène.
 *   Les effets liés au défilement (héro, teintes des chapitres) sont en CSS (animation-timeline).
 *   Tout mouvement est coupé si le système demande de réduire les animations ou si la pause est active.
 *
 * Aucun appel réseau, aucune donnée collectée. Sans JavaScript, la page reste complète (rien n'est masqué).
 */
(function () {
  "use strict";

  var html = document.documentElement;
  var reduit = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  var pointeurFin = window.matchMedia ? window.matchMedia("(hover: hover) and (pointer: fine)") : null;

  function mouvementAutorise() {
    return !(reduit && reduit.matches) && html.getAttribute("data-animations") !== "pause";
  }

  /* ---------------------------------------------------------------- images de marque */
  function suivreImages() {
    Array.prototype.forEach.call(document.querySelectorAll("img[data-visuel]"), function (img) {
      var scene = img.closest(".nt-scene");
      function chargee() {
        img.classList.remove("est-indisponible");
        img.classList.add("est-chargee");
        if (scene) { scene.classList.add("a-visuel"); }
      }
      function indisponible() {
        img.classList.add("est-indisponible");
        if (scene) { scene.classList.remove("a-visuel"); }
      }
      img.addEventListener("load", chargee);
      img.addEventListener("error", indisponible);
      if (img.complete) {
        if (img.naturalWidth > 0) { chargee(); } else if (img.currentSrc || img.getAttribute("src")) { indisponible(); }
      }
    });
  }

  /* ---------------------------------------------------------------- pause des animations */
  function initPause() {
    var boutons = Array.prototype.slice.call(document.querySelectorAll("[data-pause-animations]"));
    if (!boutons.length) { return; }
    /* Libellé constant (« Pause des animations ») : l'état est porté par aria-pressed (bouton bascule). */
    function afficher() {
      var enPause = html.getAttribute("data-animations") === "pause";
      boutons.forEach(function (b) { b.setAttribute("aria-pressed", enPause ? "true" : "false"); });
    }
    boutons.forEach(function (bouton) {
      bouton.hidden = false;
      bouton.addEventListener("click", function () {
        var pause = html.getAttribute("data-animations") !== "pause";
        if (pause) { html.setAttribute("data-animations", "pause"); } else { html.removeAttribute("data-animations"); }
        try {
          if (pause) { window.localStorage.setItem("lp-animations", "pause"); } else { window.localStorage.removeItem("lp-animations"); }
        } catch (e) {
          /* stockage indisponible : le choix vaut pour cette visite */
        }
        afficher();
      });
    });
    afficher();
  }

  /* ---------------------------------------------------------------- apparitions */
  function initApparitions() {
    var elements = Array.prototype.slice.call(document.querySelectorAll("[data-apparition]"));
    if (!elements.length) { return; }
    function toutMontrer() { elements.forEach(function (el) { el.classList.add("est-visible"); }); }
    if (!("IntersectionObserver" in window)) { toutMontrer(); return; }
    var hauteur = window.innerHeight || document.documentElement.clientHeight;
    elements.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.top < hauteur && r.bottom > 0) { el.classList.add("est-visible"); }
    });
    var observateur = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (entree) {
        if (entree.isIntersecting) {
          entree.target.classList.add("est-visible");
          observateur.unobserve(entree.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    elements.forEach(function (el) { if (!el.classList.contains("est-visible")) { observateur.observe(el); } });
    html.classList.add("lp-apparitions");
    /* Filet de sécurité : rien ne reste masqué (impression, capture, onglet en arrière-plan). */
    window.addEventListener("beforeprint", toutMontrer);
    setTimeout(function () {
      if (document.visibilityState === "hidden") { toutMontrer(); }
    }, 4000);
  }

  /* ---------------------------------------------------------------- en-tête */
  function initEntete() {
    var entete = document.getElementById("entete");
    if (!entete) { return; }
    var enAttente = false;
    function maj() {
      enAttente = false;
      entete.classList.toggle("est-defile", (window.pageYOffset || document.documentElement.scrollTop || 0) > 24);
    }
    window.addEventListener("scroll", function () {
      if (!enAttente) { enAttente = true; window.requestAnimationFrame(maj); }
    }, { passive: true });
    maj();
  }

  /* ---------------------------------------------------------------- panneaux « verre » */
  function initHolo() {
    if (!pointeurFin || !pointeurFin.matches) { return; }
    Array.prototype.forEach.call(document.querySelectorAll(".nt-holo"), function (carte) {
      carte.addEventListener("pointermove", function (e) {
        if (!mouvementAutorise()) { return; }
        var r = carte.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width;
        var y = (e.clientY - r.top) / r.height;
        carte.style.setProperty("--ry", ((x - 0.5) * 10).toFixed(2) + "deg");
        carte.style.setProperty("--rx", ((0.5 - y) * 8).toFixed(2) + "deg");
        carte.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
        carte.style.setProperty("--my", (y * 100).toFixed(1) + "%");
        carte.classList.add("est-survolee");
      });
      carte.addEventListener("pointerleave", function () {
        carte.classList.remove("est-survolee");
        ["--rx", "--ry", "--mx", "--my"].forEach(function (v) { carte.style.removeProperty(v); });
      });
    });
  }

  /* ---------------------------------------------------------------- rail des formats (mobile) */
  function initRails() {
    var rails = Array.prototype.slice.call(document.querySelectorAll("[data-rail]"));
    if (!rails.length) { return; }
    /* Un rail qui défile horizontalement doit pouvoir recevoir le focus (flèches du clavier). */
    function maj() {
      rails.forEach(function (rail) {
        if (rail.scrollWidth > rail.clientWidth + 1) {
          rail.setAttribute("tabindex", "0");
          rail.setAttribute("role", "region");
        } else {
          rail.removeAttribute("tabindex");
          rail.removeAttribute("role");
        }
      });
    }
    window.addEventListener("resize", maj);
    maj();
  }

  /* ---------------------------------------------------------------- questions fréquentes */
  function initQuestions() {
    function ouvrir(hash) {
      if (!hash || hash.length < 2) { return; }
      var cible = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (cible && cible.tagName === "DETAILS") { cible.open = true; }
    }
    document.addEventListener("click", function (e) {
      var lien = e.target.closest ? e.target.closest('a[href^="#"]') : null;
      if (lien) { ouvrir(lien.getAttribute("href")); }
    });
    window.addEventListener("hashchange", function () { ouvrir(window.location.hash); });
    ouvrir(window.location.hash);
  }

  function init() {
    suivreImages();
    initApparitions();
    initEntete();
    initPause();
    initHolo();
    initRails();
    initQuestions();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
