/*
 * Ambiance « Atelier » — effets de la landing, des pages secondaires et des maquettes (docs/05-da/DIRECTION_ATELIER.md).
 *
 * - Le fil orange (§6) : une ligne continue, tracée en SVG dans .lp-fil. Elle sort du filet photographié du héro,
 *   descend sous le contenu, glisse en S jusqu'à la marge gauche, entre dans le filet photographié de chaque figure
 *   [data-fil-ancre] et en ressort (points, épaisseur et teintes mesurés, écrits dans data-fil, data-fil-ep et
 *   data-fil-couleurs par site/outils/visuels.py depuis site/config/visuels.json) : le raccord est effilé, de
 *   l'épaisseur et de la teinte du filet photographié jusqu'au trait de 2 px. Elle passe sous les illustrations
 *   pleine largeur (et sous les figures [data-fil-masque]), ressort de la corde du Léman (data-fil-ancre="corde"), se
 *   branche sur le tiret de chaque numéro de chapitre [data-fil-chapitre] posé contre la marge et sur le filet des
 *   photos [data-fil-ancre="branche"], puis se pose sous le renard endormi du pied de page. Sous 700 px, pas de fil
 *   dans la marge : chaque filet se prolonge et s'effile. Il se dessine au défilement ; en mouvement réduit ou en
 *   pause, il est entier et immobile. Il ne porte aucune information (décor, aria-hidden).
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
    var traits = [];          // [{el, longueur, echantillons: [{l, y}], effiles: [{el, de, a}]}]
    var chapitres = [];       // [{el, y}] : numéros dont le tiret se dessine quand le fil les atteint
    var premierTrace = true;
    var enAttente = false;
    var calculEnAttente = null;
    var identifiant = 0;
    /* Longueurs des raccords effilés (px) : au départ d'un filet photographié, à l'arrivée, sur mobile. */
    var EFFILE_DEPART = 96, EFFILE_ARRIVEE = 64, PROLONGEMENT = 64;

    function point(x, y) { return { x: x, y: y }; }
    function ajouter(a, d, k) { return point(a.x + d.x * k, a.y + d.y * k); }

    function boiteDoc(el) {
      var r = el.getBoundingClientRect();
      var origine = document.body.getBoundingClientRect();
      return { x: r.left - origine.left, y: r.top - origine.top, w: r.width, h: r.height };
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

    /* Fraction d'une variable CSS (« 6% » → 0.06) lue sur un élément ; 0 si absente. */
    function fraction(el, nom) {
      var v = parseFloat(window.getComputedStyle(el).getPropertyValue(nom));
      return isNaN(v) ? 0 : v / 100;
    }

    /* Le cadre est-il fondu (masque) ? Fondu gauche (fraction de la largeur) et haut (fraction de la hauteur). */
    function fondus(figure) {
      var s = window.getComputedStyle(figure);
      var masque = s.maskImage || s.webkitMaskImage || "none";
      if (masque === "none") { return { gauche: 0, haut: 0 }; }
      var gauche = /90deg/.test(masque) ? fraction(figure, "--lp-fondu") : 0;
      return { gauche: gauche, haut: fraction(figure, "--lp-fondu-haut") };
    }

    /* Filet photographié d'une figure, projeté dans la page (object-fit: cover et object-position compris), avec son
       épaisseur projetée (px) et ses couleurs mesurées (entrée, sortie). */
    function filetDe(figure) {
      var img = figure.querySelector("img[data-visuel]");
      if (!img || img.classList.contains("est-indisponible")) { return null; }
      var src = sourceActive(img);
      var f = String(src.getAttribute("data-fil") || "").trim().split(/\s+/).map(Number);
      var nw = Number(src.getAttribute("width")), nh = Number(src.getAttribute("height"));
      if (f.length !== 4 || f.some(isNaN) || !nw || !nh) { return null; }
      var b = boiteDoc(img.closest(".lp-media") || img);
      if (b.w < 2 || b.h < 2) { return null; }
      var style = window.getComputedStyle(img);
      var pos = (style.objectPosition || "50% 50%").split(/\s+/);
      var s = style.objectFit === "contain" ? Math.min(b.w / nw, b.h / nh) : Math.max(b.w / nw, b.h / nh);
      var dw = nw * s, dh = nh * s;
      var ox = b.x + (b.w - dw) * pourcent(pos[0]), oy = b.y + (b.h - dh) * pourcent(pos[1]);
      var ep = Number(src.getAttribute("data-fil-ep")) * dh;
      var couleurs = String(src.getAttribute("data-fil-couleurs") || "").trim().split(/\s+/);
      return {
        boite: b,
        a: point(ox + f[0] * dw, oy + f[1] * dh),
        z: point(ox + f[2] * dw, oy + f[3] * dh),
        ep: isNaN(ep) ? 2 : Math.max(2, ep),
        couleurs: couleurs.length === 2 ? couleurs : []
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

    function f1(v) { return v.toFixed(1); }
    function pt(p) { return f1(p.x) + " " + f1(p.y); }

    /* Abscisse du fil : milieu de la marge gauche (même règle que --lp-fil-x dans css/landing.css). */
    function abscisse() {
      var cadre = document.querySelector(".lp-cadre");
      if (!cadre) { return 12; }
      var b = boiteDoc(cadre);
      var marge = parseFloat(window.getComputedStyle(cadre).paddingLeft) || 20;
      return Math.max(4, Math.round(b.x + marge - marge / 2));
    }

    /* Bas du contenu de la section d'une figure (sans sa marge intérieure basse) et marge haute de la section suivante :
       le fil descend sous le contenu puis rejoint la marge dans l'espace libre entre deux chapitres. */
    function espaceSous(figure) {
      var selecteur = figure.getAttribute("data-fil-retour");
      var section = (selecteur && figure.closest(selecteur)) || figure.closest("section, footer") || figure;
      var bs = boiteDoc(section);
      var s = window.getComputedStyle(section);
      var bas = bs.y + bs.h - (parseFloat(s.paddingBottom) || 0);
      var suivante = section.nextElementSibling;
      while (suivante && suivante.offsetHeight === 0) { suivante = suivante.nextElementSibling; }
      if (!suivante && section.parentElement && section.parentElement.tagName === "MAIN") { suivante = document.querySelector("footer"); }
      var haut = suivante ? parseFloat(window.getComputedStyle(suivante).paddingTop) || 0 : 0;
      return { bas: bas, libre: (bs.y + bs.h) - bas + haut };
    }

    /* Figures que le fil traverse, dans l'ordre de la page. */
    function ancres(gx) {
      var liste = [];
      Array.prototype.forEach.call(document.querySelectorAll("[data-fil-ancre]"), function (figure) {
        var role = figure.getAttribute("data-fil-ancre") || "";
        if (role === "branche") { return; }
        var f = filetDe(figure);
        if (!f) { return; }
        var b = f.boite, dir = unitaire(f.a, f.z);
        var a = { role: role, figure: figure, boite: b, dir: dir, ep: f.ep, couleurs: f.couleurs, plonge: b.x <= gx + 2 && b.x + b.w >= gx };
        if (role === "corde") {
          /* Le fil passe sous l'illustration et ressort du bout de la corde photographiée. */
          if (f.z.x < b.x || f.z.x > b.x + b.w || f.z.y < b.y || f.z.y > b.y + b.h) { return; }
          a.plonge = true;
          a.entree = point(gx, b.y);
          a.sortie = f.z;
        } else {
          var seg = decouper(f.a, f.z, b);
          if (!seg) { return; }
          var entree = seg.a;
          if (a.plonge) {
            /* Illustration pleine largeur : le fil passe dessous et rejoint le filet là où il croise la marge. */
            var t = (gx - f.a.x) / ((f.z.x - f.a.x) || 1);
            if (t >= 0 && t <= 1) { entree = point(f.a.x + t * (f.z.x - f.a.x), f.a.y + t * (f.z.y - f.a.y)); }
          } else {
            /* Cadre fondu à gauche : le fil dessiné recouvre la partie fondue du filet. */
            var fondu = fondus(figure).gauche * b.w;
            if (fondu > 0 && dir.x > 0.2) { entree = ajouter(seg.a, dir, fondu / dir.x); }
          }
          a.entree = entree;
          a.sortie = seg.z;
        }
        var espace = espaceSous(figure);
        a.bas = espace.bas;
        a.libre = espace.libre;
        liste.push(a);
      });
      return liste;
    }

    /* Blocs de contenu (textes, liens, formulaires, figures) : le fil ne les traverse jamais. */
    function obstacles() {
      var selecteur = "main h1, main h2, main h3, main p, main li, main dt, main dd, main a, main form, main figure, main summary, main .lp-encadre";
      return Array.prototype.map.call(document.querySelectorAll(selecteur), function (el) {
        return { el: el, b: boiteDoc(el) };
      }).filter(function (o) { return o.b.w > 0 && o.b.h > 0; });
    }

    /* Abscisse libre la plus proche de x pour une descente verticale entre y0 et y1 (à 32 px au moins de tout bloc). */
    function abscisseLibre(x, y0, y1, obs, gx, largeur, figure) {
      var bloques = obs.filter(function (o) {
        return o.b.y < y1 && o.b.y + o.b.h > y0 && !(figure && (o.el === figure || figure.contains(o.el)));
      }).map(function (o) { return [o.b.x - 32, o.b.x + o.b.w + 32]; });
      var candidats = [x];
      bloques.forEach(function (iv) { candidats.push(iv[0], iv[1]); });
      var libres = candidats.filter(function (c) {
        return c > gx + 16 && c < largeur - 8 && !bloques.some(function (iv) { return c > iv[0] + 0.5 && c < iv[1] - 0.5; });
      });
      libres.sort(function (a, b) { return Math.abs(a - x) - Math.abs(b - x); });
      return libres.length ? libres[0] : x;
    }

    /* Tronçon entre deux figures : il prolonge le filet de sortie, tourne vers le bas sans crochet, descend sous le
       contenu (dans un couloir libre), glisse en S jusqu'à la marge, la longe puis entre dans le filet suivant (ou passe
       sous l'image). */
    function troncon(de, vers, gx, obs, largeur) {
      var e = de.sortie, d = de.dir;
      var p1 = ajouter(e, d, 24);
      var r = 56;
      var q = point(p1.x + d.x * r * 0.6, p1.y + r * (0.7 + Math.max(0, d.y)));
      var y1 = Math.max(q.y, de.bas + 16);
      q.x = abscisseLibre(q.x, q.y, y1, obs, gx, largeur, de.figure);
      if (q.x < p1.x) {
        /* Couloir resserré (ex. entre deux colonnes) : le fil tourne aussitôt, sans s'avancer vers le bloc voisin. */
        p1 = ajouter(e, d, 6);
      }
      var c = "M" + pt(e) + " L" + pt(p1) + " C" + pt(ajouter(p1, d, q.x < p1.x ? 12 : r * 0.5)) + " " + f1(q.x) + " " + f1(q.y - r * 0.45) + " " + pt(q);
      if (y1 > q.y + 0.5) { c += " L" + f1(q.x) + " " + f1(y1); }
      var hs = Math.max(72, Math.min(240, (de.libre - 16) - 32));
      var y2 = y1 + hs;
      c += " C" + f1(q.x) + " " + f1(y1 + hs * 0.55) + " " + f1(gx) + " " + f1(y2 - hs * 0.55) + " " + f1(gx) + " " + f1(y2);
      var b = vers.entree;
      if (vers.plonge) {
        c += " L" + f1(gx) + " " + f1(Math.max(y2, b.y));
        if (Math.abs(b.x - gx) > 0.5) { c += " L" + pt(b); }
        return c;
      }
      var d2 = vers.dir;
      var k = (b.x - gx) / Math.max(0.2, d2.x);
      var coin = point(gx, b.y - d2.y * k);
      var rc = Math.max(4, Math.min(40, k * 0.6, coin.y - y2));
      c += " L" + f1(gx) + " " + f1(coin.y - rc) + " Q" + pt(coin) + " " + pt(ajouter(coin, d2, rc)) + " L" + pt(b);
      return c;
    }

    /* Branche : depuis la marge, le fil rejoint le tiret d'un numéro de chapitre ou le filet d'une photo. */
    function branche(cible, d, gx) {
      var k = (cible.x - gx) / Math.max(0.2, d.x);
      var coin = point(gx, cible.y - d.y * k);
      var rc = Math.max(4, Math.min(24, k * 0.6));
      return "M" + f1(gx) + " " + f1(coin.y - rc - 8) + " L" + f1(gx) + " " + f1(coin.y - rc) + " Q" + pt(coin) + " " + pt(ajouter(coin, d, rc)) + " L" + pt(cible);
    }

    function creer(nom, attributs) {
      var el = document.createElementNS(svg.namespaceURI, nom);
      Object.keys(attributs).forEach(function (k) { el.setAttribute(k, attributs[k]); });
      return el;
    }

    /* Polygone effilé le long d'un chemin : largeur l0 en s0, l1 en s1, dégradé de couleur (teinte du filet photographié
       vers l'orange du fil). */
    function effile(chemin, s0, s1, l0, l1, couleur, versFilet, defs) {
      var n = 16, gauche = [], droite = [];
      for (var i = 0; i <= n; i++) {
        var s = s0 + (s1 - s0) * i / n;
        var p = chemin.getPointAtLength(s);
        var pa = chemin.getPointAtLength(Math.max(0, s - 1)), pb = chemin.getPointAtLength(Math.min(chemin.getTotalLength(), s + 1));
        var t = unitaire(pa, pb), nx = -t.y, ny = t.x;
        var u = i / n, lisse = u * u * (3 - 2 * u);
        var w = (l0 + (l1 - l0) * lisse) / 2;
        gauche.push(point(p.x + nx * w, p.y + ny * w));
        droite.push(point(p.x - nx * w, p.y - ny * w));
      }
      var d = "M" + gauche.map(pt).join(" L") + " L" + droite.reverse().map(pt).join(" L") + " Z";
      var id = "lp-fil-degrade-" + (identifiant++);
      var a = chemin.getPointAtLength(s0), z = chemin.getPointAtLength(s1);
      var degrade = creer("linearGradient", { id: id, gradientUnits: "userSpaceOnUse", x1: f1(a.x), y1: f1(a.y), x2: f1(z.x), y2: f1(z.y) });
      var arret = creer("stop", { offset: versFilet ? "1" : "0", "stop-color": couleur || "currentColor" });
      var fin = creer("stop", { offset: versFilet ? "0" : "1", "class": "lp-fil__fin" });
      if (versFilet) { degrade.appendChild(fin); degrade.appendChild(arret); } else { degrade.appendChild(arret); degrade.appendChild(fin); }
      if (!couleur) { arret.setAttribute("class", "lp-fil__fin"); }
      defs.appendChild(degrade);
      return creer("path", { "class": "lp-fil__effile", d: d, fill: "url(#" + id + ")" });
    }

    function echantillonner(el) {
      var longueur = el.getTotalLength();
      var n = Math.max(24, Math.min(400, Math.round(longueur / 24)));
      var echantillons = [];
      var ymax = -Infinity;
      for (var k = 0; k <= n; k++) {
        var l = longueur * k / n, y = el.getPointAtLength(l).y;
        ymax = Math.max(ymax, y);   // niveau de lecture monotone (le fil ne remonte jamais)
        echantillons.push({ l: l, y: ymax });
      }
      return { longueur: longueur, echantillons: echantillons };
    }

    /* Masque d'un tronçon : il passe sous les illustrations pleine largeur (sauf celle d'où il part). */
    function masquePour(figures, largeur, hauteur, defs) {
      if (!figures.length) { return null; }
      var id = "lp-fil-masque-" + (identifiant++);
      var masque = creer("mask", { id: id, maskUnits: "userSpaceOnUse", x: 0, y: 0, width: largeur, height: hauteur });
      masque.appendChild(creer("rect", { x: 0, y: 0, width: largeur, height: hauteur, fill: "white" }));
      figures.forEach(function (fig) {
        var b = boiteDoc(fig);
        var retrait = fondus(fig).haut * b.h * 0.5;   // le fil disparaît au milieu du fondu du haut, pas avant
        masque.appendChild(creer("rect", { x: f1(b.x), y: f1(b.y + retrait), width: f1(b.w), height: f1(b.h - retrait), fill: "black" }));
      });
      defs.appendChild(masque);
      return "url(#" + id + ")";
    }

    function calculer() {
      calculEnAttente = null;
      if (!svg) { return; }
      var largeur = document.body.clientWidth, hauteur = document.body.scrollHeight;
      while (svg.firstChild) { svg.removeChild(svg.firstChild); }
      traits = [];
      chapitres = [];
      svg.setAttribute("viewBox", "0 0 " + largeur + " " + hauteur);
      svg.setAttribute("width", largeur);
      svg.setAttribute("height", hauteur);
      var gx = abscisse();
      var liste = ancres(gx);
      if (liste.length < 2) { html.classList.remove("lp-fil-pret"); return; }
      var defs = creer("defs", {});
      svg.appendChild(defs);
      var groupe = creer("g", {});
      svg.appendChild(groupe);
      var etroit = largeur < 700;
      var cadre = document.querySelector(".lp-cadre");
      var gaucheContenu = cadre ? boiteDoc(cadre).x + (parseFloat(window.getComputedStyle(cadre).paddingLeft) || 0) : gx;

      Array.prototype.forEach.call(document.querySelectorAll("[data-fil-chapitre]"), function (numero) {
        var chiffre = numero.querySelector(".lp-numero__chiffre") || numero;
        var b = boiteDoc(chiffre);
        chapitres.push({ el: numero, y: b.y + b.h / 2, x: b.x });
      });

      if (etroit) {
        /* Mobile : pas de fil dans la marge (trop proche du texte) ; chaque filet se prolonge et s'effile. */
        liste.forEach(function (a) {
          if (a.role === "corde" || a.sortie.x > largeur - 8) { return; }
          var fin = ajouter(a.sortie, a.dir, PROLONGEMENT);
          var guide = creer("path", { d: "M" + pt(a.sortie) + " L" + pt(fin), fill: "none" });
          groupe.appendChild(guide);
          var poly = effile(guide, 0, PROLONGEMENT, a.ep, 0, a.couleurs[1], false, defs);
          groupe.removeChild(guide);
          groupe.appendChild(poly);
          traits.push({ el: poly, longueur: 0, echantillons: [{ l: 0, y: a.sortie.y }], effiles: [], seul: true });
        });
        html.classList.add("lp-fil-pret");
        premierTrace = false;
        dessiner(true);
        return;
      }

      var masquables = Array.prototype.slice.call(document.querySelectorAll("[data-fil-masque]"));
      var obs = obstacles();
      /* Le fil passe sous les illustrations pleine largeur : pas de branche vers un numéro posé dessus. */
      var dessous = liste.filter(function (a) { return a.plonge; }).map(function (a) { return a.boite; });
      for (var i = 0; i < liste.length - 1; i++) {
        var de = liste[i], vers = liste[i + 1];
        var caches = masquables.filter(function (fig) { var b = boiteDoc(fig); return fig !== de.figure && b.x <= gx && b.x + b.w >= gx; });
        if (vers.plonge && vers.figure !== de.figure) { caches.push(vers.figure); }
        var el = creer("path", { "class": "lp-fil__trait", d: troncon(de, vers, gx, obs, largeur) });
        var sousGroupe = creer("g", {});
        var masque = masquePour(caches, largeur, hauteur, defs);
        if (masque) { sousGroupe.setAttribute("mask", masque); }
        sousGroupe.appendChild(el);
        groupe.appendChild(sousGroupe);
        var mesure = echantillonner(el);
        var trait = { el: el, longueur: mesure.longueur, echantillons: mesure.echantillons, effiles: [] };
        var lDepart = Math.min(EFFILE_DEPART, mesure.longueur / 3);
        if (de.ep > 2.5) {
          var depart = effile(el, 0, lDepart, de.ep, 2, de.couleurs[1], false, defs);
          sousGroupe.appendChild(depart);
          trait.effiles.push({ el: depart, de: 0 });
        }
        if (!vers.plonge && vers.ep > 2.5) {
          var lArrivee = Math.min(EFFILE_ARRIVEE, mesure.longueur / 3);
          var arrivee = effile(el, mesure.longueur - lArrivee, mesure.longueur, 2, vers.ep, vers.couleurs[0], true, defs);
          sousGroupe.appendChild(arrivee);
          trait.effiles.push({ el: arrivee, de: mesure.longueur - 2 });
        }
        traits.push(trait);
      }

      /* Branches : tiret de chaque numéro posé contre la marge, filet des photos [data-fil-ancre="branche"]. */
      chapitres.forEach(function (c) {
        if (c.x > gaucheContenu + 4 || c.x - gx < 8) { return; }
        if (dessous.some(function (b) { return c.y >= b.y && c.y <= b.y + b.h; })) { return; }
        var el = creer("path", { "class": "lp-fil__trait lp-fil__branche", d: branche(point(c.x + 1, c.y), point(1, 0), gx) });
        groupe.appendChild(el);
        var mesure = echantillonner(el);
        traits.push({ el: el, longueur: mesure.longueur, echantillons: mesure.echantillons, effiles: [] });
      });
      Array.prototype.forEach.call(document.querySelectorAll('[data-fil-ancre="branche"]'), function (figure) {
        var f = filetDe(figure);
        if (!f || f.boite.x - gx < 8) { return; }
        var seg = decouper(f.a, f.z, f.boite);
        if (!seg) { return; }
        var d = unitaire(f.a, f.z);
        var el = creer("path", { "class": "lp-fil__trait lp-fil__branche", d: branche(seg.a, d, gx) });
        groupe.appendChild(el);
        var mesure = echantillonner(el);
        var trait = { el: el, longueur: mesure.longueur, echantillons: mesure.echantillons, effiles: [] };
        if (f.ep > 2.5) {
          var l = Math.min(EFFILE_ARRIVEE, mesure.longueur * 0.8);
          var poly = effile(el, mesure.longueur - l, mesure.longueur, 2, f.ep, f.couleurs[0], true, defs);
          groupe.appendChild(poly);
          trait.effiles.push({ el: poly, de: mesure.longueur - 2 });
        }
        traits.push(trait);
      });

      html.classList.add("lp-fil-pret");
      if (premierTrace && mouvementAutorise()) {
        /* Premier tracé : le fil part caché puis se dessine jusqu'au niveau de lecture. */
        premierTrace = false;
        conteneur.classList.remove("lp-fil--anime");
        traits.forEach(function (t) {
          t.el.style.strokeDasharray = t.longueur.toFixed(1) + " " + (t.longueur + 4).toFixed(1);
          t.el.style.strokeDashoffset = t.longueur.toFixed(1);
          t.el.classList.add("est-cache");
          t.effiles.forEach(function (e) { e.el.classList.add("est-cache"); });
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
      if (!conteneur) { return; }
      var anime = mouvementAutorise();
      conteneur.classList.toggle("lp-fil--anime", anime && !initial);
      var yCible = (window.pageYOffset || 0) + (window.innerHeight || html.clientHeight) * 0.85;
      chapitres.forEach(function (c) { c.el.classList.toggle("est-relie", !anime || yCible >= c.y); });
      traits.forEach(function (t) {
        if (t.seul) {
          t.el.classList.toggle("est-cache", anime && yCible < t.echantillons[0].y);
          return;
        }
        if (!anime) {
          t.el.style.strokeDasharray = "none";
          t.el.style.strokeDashoffset = "0";
          t.el.classList.remove("est-cache");
          t.effiles.forEach(function (e) { e.el.classList.remove("est-cache"); });
          return;
        }
        var l = longueurA(t, yCible);
        t.el.style.strokeDasharray = t.longueur.toFixed(1) + " " + (t.longueur + 4).toFixed(1);
        t.el.style.strokeDashoffset = (t.longueur - l).toFixed(1);
        t.el.classList.toggle("est-cache", l < 1);
        t.effiles.forEach(function (e) { e.el.classList.toggle("est-cache", l < Math.max(1, e.de)); });
      });
      if (initial && anime) {
        /* Tracé recalculé (fenêtre, polices) posé sans transition, puis le fil suit la lecture en douceur. */
        window.requestAnimationFrame(function () { conteneur.classList.add("lp-fil--anime"); });
      }
    }

    function planifierDessin() {
      if (!enAttente && (traits.length || chapitres.length)) { enAttente = true; window.requestAnimationFrame(function () { dessiner(false); }); }
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
