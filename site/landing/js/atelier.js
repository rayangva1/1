/*
 * Ambiance « Atelier » — effets de la landing, des pages secondaires et des maquettes (docs/05-da/DIRECTION_ATELIER.md).
 *
 * - Le fil orange (§6) : une ligne continue, tracée en SVG dans .lp-fil, qui sort du filet photographié du héro,
 *   descend dans la marge gauche, rejoint le filet photographié de chaque figure [data-fil-ancre] (points mesurés,
 *   écrits dans data-fil par site/outils/visuels.py depuis site/config/visuels.json), s'efface derrière les figures
 *   [data-fil-masque] et se pose sous le renard endormi du pied de page. Il se dessine au défilement ; en mouvement
 *   réduit ou en pause, il est entier et immobile. Il ne porte aucune information (décor, aria-hidden).
 * - Images de marque : si une image ne charge pas, elle est masquée (jamais d'icône cassée) et le décor de secours
 *   (silhouette du renard) reste visible.
 * - Boutons « Pause des animations » (WCAG 2.2.2, en-tête et pied de page), choix mémorisé si possible.
 * - Apparitions au défilement (IntersectionObserver), en-tête au défilement, question fréquente ouverte par un lien.
 *
 * Aucun appel réseau, aucune donnée collectée. Sans JavaScript, la page reste complète et une ligne CSS remplace le fil.
 */
(function () {
  "use strict";

  var html = document.documentElement;
  var reduit = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

  function mouvementAutorise() {
    return !(reduit && reduit.matches) && html.getAttribute("data-animations") !== "pause";
  }

  /* ---------------------------------------------------------------- images de marque */
  function suivreImages(apresChargement) {
    Array.prototype.forEach.call(document.querySelectorAll("img[data-visuel]"), function (img) {
      var cadre = img.closest(".lp-media");
      function chargee() {
        img.classList.remove("est-indisponible");
        if (cadre) { cadre.classList.add("a-visuel"); }
        apresChargement();
      }
      function indisponible() {
        img.classList.add("est-indisponible");
        if (cadre) { cadre.classList.remove("a-visuel"); }
      }
      img.addEventListener("load", chargee);
      img.addEventListener("error", indisponible);
      if (img.complete) {
        if (img.naturalWidth > 0) { chargee(); } else if (img.currentSrc || img.getAttribute("src")) { indisponible(); }
      }
    });
  }

  /* ---------------------------------------------------------------- pause des animations */
  function initPause(changement) {
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
        changement();
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
    var hauteur = window.innerHeight || html.clientHeight;
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
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.1 });
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
      entete.classList.toggle("est-defile", (window.pageYOffset || html.scrollTop || 0) > 8);
    }
    window.addEventListener("scroll", function () {
      if (!enAttente) { enAttente = true; window.requestAnimationFrame(maj); }
    }, { passive: true });
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

  /* ================================================================ le fil orange */
  var Fil = (function () {
    var conteneur = document.querySelector(".lp-fil");
    var svg = conteneur ? conteneur.querySelector("svg") : null;
    var traits = [];          // [{el, longueur, echantillons: [{l, y}]}]
    var premierTrace = true;
    var enAttente = false;
    var calculEnAttente = null;

    function point(x, y) { return { x: x, y: y }; }

    function boiteDoc(el) {
      var r = el.getBoundingClientRect();
      var sx = window.pageXOffset || 0, sy = window.pageYOffset || 0;
      var origine = document.body.getBoundingClientRect();
      return { x: r.left - origine.left, y: r.top + sy - (origine.top + sy), w: r.width, h: r.height, sx: sx };
    }

    /* Source active d'une image (dans <picture>, la première <source> dont la requête média correspond). */
    function sourceActive(img) {
      var pic = img.parentNode && img.parentNode.tagName === "PICTURE" ? img.parentNode : null;
      if (pic) {
        var sources = pic.querySelectorAll("source");
        for (var i = 0; i < sources.length; i++) {
          var media = sources[i].getAttribute("media");
          if (!media || window.matchMedia(media).matches) { return sources[i]; }
        }
      }
      return img;
    }

    function pourcent(valeur) {
      var v = String(valeur || "50%").trim();
      if (/%$/.test(v)) { return parseFloat(v) / 100; }
      if (v === "left" || v === "top") { return 0; }
      if (v === "right" || v === "bottom") { return 1; }
      return 0.5;
    }

    /* Filet photographié d'une figure, projeté dans la page (object-fit: cover et object-position compris). */
    function filetDe(figure) {
      var img = figure.querySelector("img[data-visuel]");
      if (!img || img.classList.contains("est-indisponible")) { return null; }
      var src = sourceActive(img);
      var f = String(src.getAttribute("data-fil") || "").trim().split(/\s+/).map(Number);
      var nw = Number(src.getAttribute("width")), nh = Number(src.getAttribute("height"));
      if (f.length !== 4 || f.some(isNaN) || !nw || !nh) { return null; }
      /* Boîte du cadre (l'image peut être légèrement agrandie pendant son apparition, le cadre ne bouge pas). */
      var b = boiteDoc(img.closest(".lp-media") || img);
      if (b.w < 2 || b.h < 2) { return null; }
      var style = window.getComputedStyle(img);
      var pos = (style.objectPosition || "50% 50%").split(/\s+/);
      var s = style.objectFit === "contain" ? Math.min(b.w / nw, b.h / nh) : Math.max(b.w / nw, b.h / nh);
      var dw = nw * s, dh = nh * s;
      var ox = b.x + (b.w - dw) * pourcent(pos[0]), oy = b.y + (b.h - dh) * pourcent(pos[1]);
      return {
        boite: b,
        a: point(ox + f[0] * dw, oy + f[1] * dh),
        z: point(ox + f[2] * dw, oy + f[3] * dh)
      };
    }

    /* Segment [a, z] limité à la boîte (Liang-Barsky) ; null s'il n'y passe pas. */
    function decouper(a, z, b) {
      var t0 = 0, t1 = 1, dx = z.x - a.x, dy = z.y - a.y;
      var p = [-dx, dx, -dy, dy], q = [a.x - b.x, b.x + b.w - a.x, a.y - b.y, b.y + b.h - a.y];
      for (var i = 0; i < 4; i++) {
        if (p[i] === 0) { if (q[i] < 0) { return null; } continue; }
        var r = q[i] / p[i];
        if (p[i] < 0) { if (r > t1) { return null; } if (r > t0) { t0 = r; } } else { if (r < t0) { return null; } if (r < t1) { t1 = r; } }
      }
      return { a: point(a.x + t0 * dx, a.y + t0 * dy), z: point(a.x + t1 * dx, a.y + t1 * dy) };
    }

    function unitaire(a, z) {
      var dx = z.x - a.x, dy = z.y - a.y, n = Math.sqrt(dx * dx + dy * dy) || 1;
      return point(dx / n, dy / n);
    }

    /* Polyligne aux angles arrondis (rayon borné par la moitié des segments voisins). */
    function chemin(points, rayon) {
      var d = "M" + points[0].x.toFixed(1) + " " + points[0].y.toFixed(1);
      for (var i = 1; i < points.length - 1; i++) {
        var p = points[i - 1], c = points[i], n = points[i + 1];
        var l1 = Math.hypot(c.x - p.x, c.y - p.y), l2 = Math.hypot(n.x - c.x, n.y - c.y);
        var r = Math.min(rayon, l1 / 2, l2 / 2);
        if (r < 0.5) { d += " L" + c.x.toFixed(1) + " " + c.y.toFixed(1); continue; }
        var a = point(c.x - (c.x - p.x) / l1 * r, c.y - (c.y - p.y) / l1 * r);
        var b = point(c.x + (n.x - c.x) / l2 * r, c.y + (n.y - c.y) / l2 * r);
        d += " L" + a.x.toFixed(1) + " " + a.y.toFixed(1) + " Q" + c.x.toFixed(1) + " " + c.y.toFixed(1) + " " + b.x.toFixed(1) + " " + b.y.toFixed(1);
      }
      var fin = points[points.length - 1];
      return d + " L" + fin.x.toFixed(1) + " " + fin.y.toFixed(1);
    }

    /* Abscisse du fil : milieu de la marge gauche (même règle que --lp-fil-x dans css/landing.css). */
    function abscisse() {
      var cadre = document.querySelector(".lp-cadre");
      if (!cadre) { return 12; }
      var b = boiteDoc(cadre);
      var marge = parseFloat(window.getComputedStyle(cadre).paddingLeft) || 20;
      return Math.max(4, Math.round(b.x + marge - marge / 2));
    }

    function ancres(gx) {
      var liste = [];
      Array.prototype.forEach.call(document.querySelectorAll("[data-fil-ancre]"), function (figure) {
        var filet = filetDe(figure);
        if (!filet) { return; }
        var seg = decouper(filet.a, filet.z, filet.boite);
        if (!seg) { return; }
        var dir = unitaire(filet.a, filet.z);
        var b = filet.boite;
        var entree = seg.a;
        if (b.x <= gx + 2) {
          /* Figure qui déborde sous le fil : il rejoint le filet un peu après l'abscisse du fil. */
          var t = (gx + 24 - filet.a.x) / ((filet.z.x - filet.a.x) || 1);
          if (t >= 0 && t <= 1) { entree = point(filet.a.x + t * (filet.z.x - filet.a.x), filet.a.y + t * (filet.z.y - filet.a.y)); }
        }
        var retourY = b.y + b.h + 36;
        var selecteur = figure.getAttribute("data-fil-retour");
        if (selecteur && window.getComputedStyle(figure).getPropertyValue("--lp-fil-retour").trim() !== "0") {
          var cible = figure.closest(selecteur) || document.querySelector(selecteur);
          if (cible) {
            var bc = boiteDoc(cible);
            var bas = bc.y + bc.h - Math.min(64, parseFloat(window.getComputedStyle(cible).paddingBottom) / 2 || 48);
            if (bas > retourY) { retourY = bas; }
          }
        }
        liste.push({ role: figure.getAttribute("data-fil-ancre") || "", entree: entree, sortie: seg.z, dir: dir, retourY: retourY, boite: b });
      });
      return liste;
    }

    function troncon(de, vers, gx, rayon) {
      var e = de.sortie, d = de.dir;
      var pts = [e];
      var p1 = point(e.x + d.x * 24, e.y + d.y * 24);
      pts.push(p1);
      var yR = Math.max(de.retourY, p1.y + rayon);
      pts.push(point(p1.x + Math.max(0, d.x) * 8, yR));
      pts.push(point(gx, yR));
      var b = vers.entree, d2 = vers.dir;
      var ecart = b.x - gx;
      var yApproche = d2.x > 0.2 ? b.y - ecart * (d2.y / d2.x) : b.y - rayon;
      if (yApproche < yR + rayon) { yApproche = Math.min(b.y, yR + rayon); }
      pts.push(point(gx, yApproche));
      pts.push(b);
      return chemin(pts, rayon);
    }

    function creer(nom, attributs) {
      var el = document.createElementNS(svg.namespaceURI, nom);
      Object.keys(attributs).forEach(function (k) { el.setAttribute(k, attributs[k]); });
      return el;
    }

    function calculer() {
      calculEnAttente = null;
      if (!svg) { return; }
      var largeur = document.body.clientWidth, hauteur = document.body.scrollHeight;
      while (svg.firstChild) { svg.removeChild(svg.firstChild); }
      traits = [];
      svg.setAttribute("viewBox", "0 0 " + largeur + " " + hauteur);
      svg.setAttribute("width", largeur);
      svg.setAttribute("height", hauteur);
      var gx = abscisse();
      var liste = ancres(gx);
      if (liste.length < 2) { html.classList.remove("lp-fil-pret"); return; }
      var rayon = largeur < 600 ? 16 : 32;
      /* Il s'efface derrière les figures sans filet qui croisent sa course (ex. le Léman plein cadre). */
      var defs = creer("defs", {});
      var masque = creer("mask", { id: "lp-fil-masque", maskUnits: "userSpaceOnUse", x: 0, y: 0, width: largeur, height: hauteur });
      masque.appendChild(creer("rect", { x: 0, y: 0, width: largeur, height: hauteur, fill: "white" }));
      Array.prototype.forEach.call(document.querySelectorAll("[data-fil-masque]"), function (fig) {
        var b = boiteDoc(fig);
        if (b.w > 0 && b.x <= gx && b.x + b.w >= gx) {
          masque.appendChild(creer("rect", { x: b.x, y: b.y, width: b.w, height: b.h, fill: "black" }));
        }
      });
      defs.appendChild(masque);
      svg.appendChild(defs);
      var groupe = creer("g", { mask: "url(#lp-fil-masque)" });
      svg.appendChild(groupe);
      for (var i = 0; i < liste.length - 1; i++) {
        var el = creer("path", { "class": "lp-fil__trait", d: troncon(liste[i], liste[i + 1], gx, rayon) });
        groupe.appendChild(el);
        var longueur = el.getTotalLength();
        var n = Math.max(24, Math.min(400, Math.round(longueur / 24)));
        var echantillons = [];
        for (var k = 0; k <= n; k++) {
          var l = longueur * k / n, pt = el.getPointAtLength(l);
          echantillons.push({ l: l, y: pt.y });
        }
        traits.push({ el: el, longueur: longueur, echantillons: echantillons });
      }
      html.classList.add("lp-fil-pret");
      if (premierTrace && mouvementAutorise()) {
        /* Premier tracé : le fil part caché puis se dessine jusqu'au niveau de lecture. */
        premierTrace = false;
        conteneur.classList.remove("lp-fil--anime");
        traits.forEach(function (t) {
          t.el.style.strokeDasharray = t.longueur.toFixed(1) + " " + (t.longueur + 4).toFixed(1);
          t.el.style.strokeDashoffset = t.longueur.toFixed(1);
          t.el.classList.add("est-cache");
        });
        window.requestAnimationFrame(function () {
          window.requestAnimationFrame(function () { dessiner(false); });
        });
        return;
      }
      premierTrace = false;
      dessiner(true);
    }

    /* Longueur dessinée : jusqu'au point du trait situé au niveau de lecture (85 % de la fenêtre). */
    function longueurA(trait, yCible) {
      var e = trait.echantillons;
      if (yCible <= e[0].y) { return 0; }
      var bas = 0, haut = e.length - 1;
      if (yCible >= e[haut].y) { return trait.longueur; }
      while (haut - bas > 1) {
        var m = (bas + haut) >> 1;
        if (e[m].y <= yCible) { bas = m; } else { haut = m; }
      }
      var a = e[bas], b = e[haut];
      return b.y === a.y ? b.l : a.l + (b.l - a.l) * (yCible - a.y) / (b.y - a.y);
    }

    function dessiner(initial) {
      enAttente = false;
      var anime = mouvementAutorise();
      conteneur.classList.toggle("lp-fil--anime", anime && !initial);
      var yCible = (window.pageYOffset || 0) + (window.innerHeight || html.clientHeight) * 0.85;
      traits.forEach(function (t) {
        if (!anime) {
          t.el.style.strokeDasharray = "none";
          t.el.style.strokeDashoffset = "0";
          t.el.classList.remove("est-cache");
          return;
        }
        var l = longueurA(t, yCible);
        t.el.style.strokeDasharray = t.longueur.toFixed(1) + " " + (t.longueur + 4).toFixed(1);
        t.el.style.strokeDashoffset = (t.longueur - l).toFixed(1);
        t.el.classList.toggle("est-cache", l < 1);
      });
      if (initial && anime) {
        /* Tracé recalculé (fenêtre, polices) posé sans transition, puis le fil suit la lecture en douceur. */
        window.requestAnimationFrame(function () { conteneur.classList.add("lp-fil--anime"); });
      }
    }

    function planifierDessin() {
      if (!enAttente && traits.length) { enAttente = true; window.requestAnimationFrame(function () { dessiner(false); }); }
    }

    function planifierCalcul() {
      if (calculEnAttente) { window.clearTimeout(calculEnAttente); }
      calculEnAttente = window.setTimeout(calculer, 120);
    }

    function init() {
      if (!svg || !document.body.classList) { return; }
      calculer();
      window.addEventListener("scroll", planifierDessin, { passive: true });
      window.addEventListener("resize", planifierCalcul);
      window.addEventListener("load", planifierCalcul);
      if (document.fonts && document.fonts.ready) { document.fonts.ready.then(planifierCalcul); }
      if ("ResizeObserver" in window) {
        var hauteurConnue = 0;
        new ResizeObserver(function () {
          var h = document.body.scrollHeight;
          if (Math.abs(h - hauteurConnue) > 1) { hauteurConnue = h; planifierCalcul(); }
        }).observe(document.body);
      }
      if (reduit && reduit.addEventListener) { reduit.addEventListener("change", function () { dessiner(true); }); }
    }

    return { init: init, recalculer: planifierCalcul, redessiner: function () { dessiner(true); } };
  })();

  function init() {
    suivreImages(Fil.recalculer);
    initApparitions();
    initEntete();
    initPause(Fil.redessiner);
    initQuestions();
    Fil.init();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
