/*
 * Ambiance « Nuit sur le Léman » — effets visuels de la landing et des maquettes (docs/05-da/DIRECTION_NUIT.md).
 *
 * - Images de marque (balises data-visuel) : fondu à l'arrivée ; si une image ne charge pas, elle est masquée et le
 *   décor CSS de secours reste visible (jamais d'icône d'image cassée).
 * - Bouton « Pause des animations » (WCAG 2.2.2) : met en pause toutes les animations, mémorisé si possible.
 * - Apparitions au défilement (IntersectionObserver), parallaxe légère, lueur qui suit le pointeur, survol 3D des
 *   cartes « verre dépoli ». Tout est coupé si le système demande de réduire les animations ou si la pause est active.
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
      function chargee() { img.classList.remove("est-indisponible"); img.classList.add("est-chargee"); }
      function indisponible() { img.classList.add("est-indisponible"); }
      img.addEventListener("load", chargee);
      img.addEventListener("error", indisponible);
      if (img.complete) {
        if (img.naturalWidth > 0) { chargee(); } else if (img.currentSrc || img.getAttribute("src")) { indisponible(); }
      }
    });
  }

  /* ---------------------------------------------------------------- pause des animations */
  function initPause(surChangement) {
    var bouton = document.getElementById("lp-animations");
    if (!bouton) { return; }
    /* Libellé constant (« Pause des animations ») : l'état est porté par aria-pressed (bouton bascule). */
    function afficher() {
      var enPause = html.getAttribute("data-animations") === "pause";
      bouton.setAttribute("aria-pressed", enPause ? "true" : "false");
    }
    bouton.hidden = false;
    afficher();
    bouton.addEventListener("click", function () {
      var pause = html.getAttribute("data-animations") !== "pause";
      if (pause) { html.setAttribute("data-animations", "pause"); } else { html.removeAttribute("data-animations"); }
      try {
        if (pause) { window.localStorage.setItem("lp-animations", "pause"); } else { window.localStorage.removeItem("lp-animations"); }
      } catch (e) {
        /* stockage indisponible : le choix vaut pour cette visite */
      }
      afficher();
      surChangement();
    });
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

  /* ---------------------------------------------------------------- parallaxe et en-tête */
  function initDefilement() {
    var entete = document.getElementById("entete");
    var couches = Array.prototype.slice.call(document.querySelectorAll("[data-parallaxe]"));
    var departs = [];
    var enAttente = false;
    function defilement() { return window.pageYOffset || document.documentElement.scrollTop || 0; }
    /* Défilement auquel la couche est « au repos » : zone centrée dans la fenêtre, ou zéro si elle est visible
       dès l'arrivée (le héro ne bouge pas tant qu'on n'a pas défilé). */
    function mesurer() {
      var y = defilement();
      var hauteur = window.innerHeight;
      departs = couches.map(function (el) {
        var zone = el.parentElement.getBoundingClientRect();
        var depart = zone.top + y + zone.height / 2 - hauteur / 2;
        return depart < hauteur ? 0 : depart;
      });
    }
    function maj() {
      enAttente = false;
      var y = defilement();
      if (entete) { entete.classList.toggle("est-defile", y > 24); }
      var actif = mouvementAutorise();
      var hauteur = window.innerHeight;
      couches.forEach(function (el, i) {
        if (!actif) { el.style.removeProperty("--decalage"); return; }
        var zone = el.parentElement.getBoundingClientRect();
        if (zone.bottom < -200 || zone.top > hauteur + 200) { return; }
        var facteur = parseFloat(el.getAttribute("data-parallaxe")) || 0;
        var decalage = Math.max(-160, Math.min(160, (y - departs[i]) * facteur));
        el.style.setProperty("--decalage", decalage.toFixed(1) + "px");
      });
    }
    function demander() {
      if (!enAttente) { enAttente = true; window.requestAnimationFrame(maj); }
    }
    window.addEventListener("scroll", demander, { passive: true });
    window.addEventListener("resize", function () { mesurer(); demander(); });
    window.addEventListener("load", function () { mesurer(); demander(); });
    mesurer();
    maj();
    return demander;
  }

  /* ---------------------------------------------------------------- lueur du pointeur */
  function initLueur() {
    var hero = document.querySelector(".lp-hero");
    if (!hero || !pointeurFin || !pointeurFin.matches) { return; }
    hero.addEventListener("pointermove", function (e) {
      if (!mouvementAutorise()) { return; }
      var r = hero.getBoundingClientRect();
      hero.style.setProperty("--px", ((e.clientX - r.left) / r.width * 100).toFixed(1) + "%");
      hero.style.setProperty("--py", ((e.clientY - r.top) / r.height * 100).toFixed(1) + "%");
      hero.classList.add("lp-hero--lueur");
    });
    hero.addEventListener("pointerleave", function () { hero.classList.remove("lp-hero--lueur"); });
  }

  /* ---------------------------------------------------------------- cartes « verre dépoli » */
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

  function init() {
    suivreImages();
    initApparitions();
    var rafraichir = initDefilement();
    initPause(rafraichir);
    initLueur();
    initHolo();
    if (reduit && reduit.addEventListener) { reduit.addEventListener("change", rafraichir); }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
