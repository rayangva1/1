/*
 * Landing — bascule de thème et formulaire d'inscription aux alertes.
 *
 * Contrat d'envoi : POST application/x-www-form-urlencoded vers LANDING_CONFIG.webhookUrl
 * (requête « simple », sans pré-vérification CORS). Champs : voir site/landing/inscription.schema.json.
 * Le double opt-in (email de confirmation) est fait par le workflow n8n, jamais par la page.
 * Aucune donnée n'est stockée par la page ; aucun service tiers n'est appelé.
 *
 * Les fonctions pures sont exposées dans LandingCore (testées sans navigateur, site/tests).
 */
(function (racine) {
  "use strict";

  var FORMATS = ["displays", "etb", "bundles-tripacks", "coffrets", "accessoires", "nouveautes"];
  var BUDGETS = ["moins-30", "30-60", "60-120", "120-250", "plus-250"];
  var POUR_QUI = ["collection", "jeu", "cadeau"];
  var CANTONS = [
    "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU", "NE", "NW",
    "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH", "hors-suisse"
  ];
  var EMAIL_MAX = 254;
  var PRENOM_MAX = 60;
  var EMAIL_RE = /^[^\s@<>()[\]",;:\\]+@[^\s@<>()[\]",;:\\]+\.[^\s@<>()[\]",;:\\]{2,}$/;
  var UTM_RE = /^[a-z0-9._-]{1,60}$/;

  var MESSAGES = {
    emailVide: "Indiquez votre adresse email.",
    emailInvalide: "Cette adresse email ne semble pas valide (exemple\u00a0: prenom@exemple.ch).",
    consentement: "Cochez la case pour confirmer que vous acceptez de recevoir ces emails.",
    desactive: "Les inscriptions ne sont pas encore ouvertes\u00a0: le formulaire sera activé à la mise en ligne de la page.",
    desactiveApercu: " Aperçu\u00a0: adresse d'envoi (webhookUrl) non configurée dans js/config.js.",
    envoi: "Envoi en cours…",
    succesTitre: "Merci, vérifiez votre boîte mail",
    succes: "Nous venons de vous envoyer un email de confirmation. Cliquez sur son lien pour activer vos alertes\u00a0: sans confirmation, nous ne vous écrirons pas.",
    succesSpam: "Rien reçu d'ici quelques minutes\u202f? Regardez dans les courriers indésirables.",
    erreur: "L'inscription n'a pas pu être envoyée. Vérifiez votre connexion et réessayez dans quelques minutes.",
    erreurContact: " Vous pouvez aussi nous écrire à "
  };

  /** Vrai si l'URL est une adresse https complète, sans espace ni champ {{…}} non remplacé. */
  function webhookValide(url) {
    if (typeof url !== "string") { return false; }
    if (url.indexOf("{{") !== -1 || url.indexOf("}}") !== -1) { return false; }
    return /^https:\/\/[A-Za-z0-9.-]+(:\d+)?\/[^\s<>"']*$/.test(url);
  }

  /** Contrôle simple de forme (le contrôle réel est le clic de confirmation). */
  function emailValide(valeur) {
    var v = String(valeur || "").trim();
    return v.length > 0 && v.length <= EMAIL_MAX && EMAIL_RE.test(v);
  }

  /** Valeur UTM nettoyée : minuscules, [a-z0-9._-], 60 caractères au plus ; sinon chaîne vide. */
  function nettoyerUtm(valeur) {
    if (typeof valeur !== "string") { return ""; }
    var v = valeur.trim().toLowerCase();
    return UTM_RE.test(v) ? v : "";
  }

  /** Lit utm_source, utm_medium et utm_campaign d'une chaîne de requête (« ?utm_source=… »). */
  function lireUtm(recherche) {
    var params = new URLSearchParams(recherche || "");
    return {
      utm_source: nettoyerUtm(params.get("utm_source")),
      utm_medium: nettoyerUtm(params.get("utm_medium")),
      utm_campaign: nettoyerUtm(params.get("utm_campaign"))
    };
  }

  function normaliserEspaces(texte) {
    return String(texte || "").replace(/\s+/g, " ").trim();
  }

  function sansControle(texte) {
    return String(texte || "").replace(/[\u0000-\u001f\u007f<>]/g, "");
  }

  function parmi(valeur, autorises) {
    return autorises.indexOf(valeur) !== -1 ? valeur : "";
  }

  /**
   * Valide les données saisies et construit les champs envoyés au webhook.
   * Retourne { ok, erreurs: {champ: message}, champs: {nom: chaîne} }.
   */
  function construirePayload(donnees, maintenant, options) {
    var d = donnees || {};
    var opts = options || {};
    var erreurs = {};
    var email = String(d.email || "").trim();
    if (!email) {
      erreurs.email = MESSAGES.emailVide;
    } else if (!emailValide(email)) {
      erreurs.email = MESSAGES.emailInvalide;
    }
    if (d.consentement !== true) {
      erreurs.consentement = MESSAGES.consentement;
    }
    var formats = [];
    (d.formats || []).forEach(function (f) {
      if (FORMATS.indexOf(f) !== -1 && formats.indexOf(f) === -1) { formats.push(f); }
    });
    var utm = d.utm || {};
    var champs = {
      email: email,
      prenom: normaliserEspaces(sansControle(d.prenom)).slice(0, PRENOM_MAX),
      formats: formats.join(","),
      budget: parmi(d.budget, BUDGETS),
      pour_qui: parmi(d.pour_qui, POUR_QUI),
      canton: parmi(d.canton, CANTONS),
      consentement: "oui",
      consentement_texte: normaliserEspaces(d.consentement_texte),
      consentement_version: String(opts.consentVersion || ""),
      horodatage_client: (maintenant instanceof Date ? maintenant : new Date()).toISOString(),
      page: String(opts.page || ""),
      source: "landing",
      utm_source: nettoyerUtm(utm.utm_source),
      utm_medium: nettoyerUtm(utm.utm_medium),
      utm_campaign: nettoyerUtm(utm.utm_campaign)
    };
    var ok = Object.keys(erreurs).length === 0;
    return { ok: ok, erreurs: erreurs, champs: ok ? champs : null };
  }

  racine.LandingCore = {
    FORMATS: FORMATS,
    BUDGETS: BUDGETS,
    POUR_QUI: POUR_QUI,
    CANTONS: CANTONS,
    MESSAGES: MESSAGES,
    webhookValide: webhookValide,
    emailValide: emailValide,
    nettoyerUtm: nettoyerUtm,
    lireUtm: lireUtm,
    construirePayload: construirePayload
  };

  if (typeof document === "undefined") { return; }

  /* ------------------------------------------------------------------ thème */
  function initTheme() {
    var bouton = document.getElementById("lp-theme");
    if (!bouton) { return; }
    var html = document.documentElement;
    var ordre = ["auto", "light", "dark"];
    var libelles = { auto: "automatique", light: "clair", dark: "sombre" };
    function actuel() {
      var t = html.getAttribute("data-theme");
      return t === "light" || t === "dark" ? t : "auto";
    }
    function afficher() { bouton.textContent = "Thème\u00a0: " + libelles[actuel()]; }
    bouton.hidden = false;
    afficher();
    bouton.addEventListener("click", function () {
      var suivant = ordre[(ordre.indexOf(actuel()) + 1) % ordre.length];
      if (suivant === "auto") { html.removeAttribute("data-theme"); } else { html.setAttribute("data-theme", suivant); }
      try {
        if (suivant === "auto") { racine.localStorage.removeItem("lp-theme"); } else { racine.localStorage.setItem("lp-theme", suivant); }
      } catch (e) {
        /* stockage indisponible : le choix vaut pour cette visite */
      }
      afficher();
    });
  }

  /* ------------------------------------------------------------ formulaire */
  function initFormulaire() {
    var form = document.getElementById("lp-formulaire");
    if (!form) { return; }
    var config = racine.LANDING_CONFIG || {};
    var bouton = document.getElementById("lp-envoyer");
    var statut = document.getElementById("lp-statut");
    var champsErreur = {
      email: { input: form.elements.email, message: document.getElementById("lp-email-erreur") },
      consentement: { input: form.elements.consentement, message: document.getElementById("lp-consentement-erreur") }
    };

    var utm = lireUtm(racine.location ? racine.location.search : "");
    Object.keys(utm).forEach(function (cle) {
      if (form.elements[cle]) { form.elements[cle].value = utm[cle]; }
    });

    var canton = form.elements.canton;
    var aideCanton = document.getElementById("lp-canton-aide");
    if (canton && aideCanton) {
      canton.addEventListener("change", function () {
        aideCanton.textContent = canton.value === "hors-suisse"
          ? "Nous livrons uniquement en Suisse\u00a0: vous pouvez vous inscrire, mais nous ne pourrons pas expédier à l'étranger."
          : "Nous livrons uniquement en Suisse.";
      });
    }

    function afficherStatut(type, texte) {
      statut.className = "lp-statut lp-statut--" + type;
      statut.textContent = texte;
    }

    if (!webhookValide(config.webhookUrl)) {
      bouton.disabled = true;
      form.setAttribute("data-etat", "desactive");
      afficherStatut("info", MESSAGES.desactive + (config.mode === "publication" ? "" : MESSAGES.desactiveApercu));
      return;
    }
    bouton.disabled = false;
    form.setAttribute("data-etat", "actif");

    function effacerErreurs() {
      Object.keys(champsErreur).forEach(function (cle) {
        var c = champsErreur[cle];
        c.input.removeAttribute("aria-invalid");
        c.message.textContent = "";
        c.message.hidden = true;
      });
    }

    function afficherErreurs(erreurs) {
      var premier = null;
      ["email", "consentement"].forEach(function (cle) {
        if (!erreurs[cle]) { return; }
        var c = champsErreur[cle];
        c.input.setAttribute("aria-invalid", "true");
        c.message.textContent = erreurs[cle];
        c.message.hidden = false;
        if (!premier) { premier = c.input; }
      });
      afficherStatut("erreur", "Le formulaire contient une erreur\u00a0: corrigez le champ indiqué.");
      if (premier) { premier.focus(); }
    }

    function lireFormulaire() {
      var formats = [];
      Array.prototype.forEach.call(form.querySelectorAll('input[name="formats"]:checked'), function (c) { formats.push(c.value); });
      var budget = form.querySelector('input[name="budget"]:checked');
      var texteConsentement = document.getElementById("lp-consentement-texte");
      return {
        email: form.elements.email.value,
        prenom: form.elements.prenom.value,
        formats: formats,
        budget: budget ? budget.value : "",
        pour_qui: form.elements.pour_qui.value,
        canton: form.elements.canton.value,
        consentement: form.elements.consentement.checked === true,
        consentement_texte: texteConsentement ? texteConsentement.textContent : "",
        piege: form.elements.site_web ? form.elements.site_web.value : "",
        utm: {
          utm_source: form.elements.utm_source.value,
          utm_medium: form.elements.utm_medium.value,
          utm_campaign: form.elements.utm_campaign.value
        }
      };
    }

    function afficherSucces() {
      var bloc = document.createElement("div");
      bloc.className = "lp-confirmation lp-statut--succes";
      var titre = document.createElement("h3");
      titre.className = "lp-h3";
      titre.tabIndex = -1;
      titre.textContent = MESSAGES.succesTitre;
      var p1 = document.createElement("p");
      p1.textContent = MESSAGES.succes;
      var p2 = document.createElement("p");
      p2.textContent = MESSAGES.succesSpam;
      bloc.appendChild(titre);
      bloc.appendChild(p1);
      bloc.appendChild(p2);
      form.innerHTML = "";
      form.appendChild(bloc);
      form.setAttribute("data-etat", "envoye");
      titre.focus();
    }

    function envoyer(champs) {
      var corps = new URLSearchParams();
      Object.keys(champs).forEach(function (cle) { corps.append(cle, champs[cle]); });
      var controleur = typeof AbortController !== "undefined" ? new AbortController() : null;
      var minuterie = setTimeout(function () { if (controleur) { controleur.abort(); } }, Number(config.timeoutMs) || 15000);
      return fetch(config.webhookUrl, {
        method: "POST",
        body: corps,
        mode: "cors",
        credentials: "omit",
        cache: "no-store",
        headers: { "Accept": "application/json" },
        signal: controleur ? controleur.signal : undefined
      }).then(function (reponse) {
        clearTimeout(minuterie);
        if (!reponse.ok) { throw new Error("HTTP " + reponse.status); }
        return reponse;
      }, function (erreur) {
        clearTimeout(minuterie);
        throw erreur;
      });
    }

    form.addEventListener("submit", function (evenement) {
      evenement.preventDefault();
      if (form.getAttribute("aria-busy") === "true") { return; }
      effacerErreurs();
      var donnees = lireFormulaire();
      if (donnees.piege) {
        afficherSucces();
        return;
      }
      var resultat = construirePayload(donnees, new Date(), {
        consentVersion: config.consentVersion || (form.elements.consentement_version ? form.elements.consentement_version.value : ""),
        page: racine.location ? racine.location.origin + racine.location.pathname : ""
      });
      if (!resultat.ok) {
        afficherErreurs(resultat.erreurs);
        return;
      }
      form.setAttribute("aria-busy", "true");
      bouton.disabled = true;
      afficherStatut("info", MESSAGES.envoi);
      envoyer(resultat.champs).then(function () {
        form.removeAttribute("aria-busy");
        afficherSucces();
      }, function () {
        form.removeAttribute("aria-busy");
        bouton.disabled = false;
        var contact = config.emailSupport && emailValide(config.emailSupport) ? MESSAGES.erreurContact + config.emailSupport + "." : "";
        afficherStatut("erreur", MESSAGES.erreur + contact);
      });
    });
  }

  function init() {
    initTheme();
    initFormulaire();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(typeof window !== "undefined" ? window : globalThis);
