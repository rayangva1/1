"""Pages HTML de démonstration DA : mini-charte et composants.

Génère CHARTE.html et components/{badges,carte-produit,banniere,page-produit}.html.
Appelé par generer_da.py (ne pas éditer les HTML à la main : modifier ce module puis régénérer).
Toutes les données produit affichées sont FICTIVES.
"""

from __future__ import annotations

import re

from icones import ICONES, icone_inline

FONTS = ("https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&amp;family=Inter:opsz,wght@14..32,400..700"
         "&amp;family=IBM+Plex+Mono:wght@500;600&amp;family=Bricolage+Grotesque:opsz,wght@12..96,400..800"
         "&amp;family=DM+Sans:opsz,wght@9..40,400..700&amp;family=Space+Grotesk:wght@500;700&amp;display=swap")

def icons(html: str) -> str:
    """Remplace les marqueurs [[i:nom]] / [[i:nom:taille]] par l'icône SVG en ligne."""
    return re.sub(r"\[\[i:([a-z-]+)(?::(\d+))?\]\]", lambda m: icone_inline(m.group(1), int(m.group(2) or 16)), html)

def head(title: str, desc: str, prefix: str = "../") -> str:
    """En-tête HTML commun (polices Google, tokens, composants, favicon, aperçu)."""
    return f"""<!DOCTYPE html>
<html lang="fr-CH" data-da="a">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="{FONTS}">
  <link rel="stylesheet" href="{prefix}tokens/tokens.css">
  <link rel="stylesheet" href="{'components.css' if prefix == '../' else 'components/components.css'}">
  <link rel="icon" href="{prefix}logo/a/favicon.svg" type="image/svg+xml">
  <script src="{'apercu.js' if prefix == '../' else 'components/apercu.js'}" defer></script>
</head>
"""

BAR = """  <div class="da-preview-bar" role="toolbar" aria-label="Options d'aperçu">
    <strong>Aperçu</strong>
    <button type="button" data-set-da="a" aria-pressed="true">Direction A — Quai</button>
    <button type="button" data-set-da="b" aria-pressed="false">Direction B — Pochette</button>
    <span aria-hidden="true">·</span>
    <button type="button" data-set-theme="auto" aria-pressed="true">Auto</button>
    <button type="button" data-set-theme="light" aria-pressed="false">Clair</button>
    <button type="button" data-set-theme="dark" aria-pressed="false">Sombre</button>
  </div>
"""

FOOT = """    <footer class="da-footer">
      <p>{{NOM_BOUTIQUE}} — boutique indépendante, sans lien officiel avec les éditeurs des jeux vendus. Pokémon est une marque de ses détenteurs respectifs (mention à faire valider par le juriste).</p>
      <p>Page de démonstration DA — données d'exemple : FICTIF — <a href="../CHARTE.html">retour à la charte</a>.</p>
    </footer>
"""


def card(
    n: int,
    badges: list[str],
    title: str,
    meta: str,
    price: str,
    stock_cls: str,
    stock_icon: str,
    stock: str,
    detail: str,
    cta: str,
    cta_cls: str = "da-btn--primary",
) -> str:
    """Carte produit d'exemple (données FICTIVES)."""
    b = "".join(badges)
    return f"""      <article class="da-card" aria-labelledby="p{n}-titre">
        <div class="da-photo" role="img" aria-label="Emplacement : photo réelle du produit">Photo produit réelle<br>(boîte FR, face avant)</div>
        <div class="da-badges">{b}</div>
        <h3 class="da-card__title" id="p{n}-titre"><a href="page-produit.html">{title}</a></h3>
        <p class="da-card__meta">{meta}</p>
        <p class="da-card__price da-price">{price}</p>
        <p class="da-stock {stock_cls}">{stock_icon}<span>{stock}<span class="da-stock__detail">{detail}</span></span></p>
        <button type="button" class="da-btn {cta_cls} da-btn--block da-card__cta">{cta}</button>
      </article>
"""

FR = '<span class="da-badge da-badge--fr">[[i:langue:14]]FR</span>'
LOC = '<span class="da-badge da-badge--local">[[i:stock-local:14]]Stock local</span>'
NEW = '<span class="da-badge da-badge--new">[[i:nouveaute:14]]Nouveauté</span>'
PRE = '<span class="da-badge da-badge--preorder">[[i:precommande:14]]Précommande</span>'
OUT = '<span class="da-badge da-badge--out">[[i:rupture:14]]Rupture</span>'
ALE = '<span class="da-badge da-badge--restock">[[i:alerte:14]]Alerte réassort</span>'

cards = (
    card(1, [FR, LOC, NEW], "Display — Extension exemple — FR", "Display · français · scellé", "CHF 209.90",
         "da-stock--local", "[[i:stock-local:16]]", "En stock local", "Expédié depuis la Suisse sous {{DELAI_EXPEDITION}} · 2 max. par commande", "Ajouter au panier")
    + card(2, [FR, PRE], "Coffret — Extension exemple 2 — FR", "Coffret · français · scellé", "CHF 59.90",
         "da-stock--preorder", "[[i:precommande:16]]", "Précommande sur allocation confirmée", "Sortie prévue le {{DATE_SORTIE}} · expédié à réception", "Précommander")
    + card(3, [FR, OUT, ALE], "ETB — Extension exemple 3 — FR", "Coffret Dresseur d'élite · français · scellé", "CHF 64.90",
         "da-stock--out", "[[i:rupture:16]]", "Rupture de stock local", "Aucune date de réassort confirmée", "M'alerter du réassort", "da-btn--secondary")
    + card(4, [LOC], "Pochettes de protection ×100 (exemple)", "Accessoire · format standard", "CHF 9.90",
         "da-stock--local", "[[i:stock-local:16]]", "En stock local", "Expédié depuis la Suisse sous {{DELAI_EXPEDITION}}", "Ajouter au panier")
)


deco_b = '''<svg class="da-banner__deco" data-only="b" width="220" height="220" viewBox="0 0 220 220" aria-hidden="true" focusable="false" style="right:-40px;top:-30px">
          <rect x="60" y="30" width="110" height="154" rx="14" transform="rotate(12 115 107)" fill="none" stroke="var(--da-color-accent)" stroke-width="12"/>
        </svg>'''


ICON_GRID = "".join(
    f'<figure class="ch-icon"><span>{icone_inline(n, 28)}</span><figcaption>{lib}</figcaption></figure>'
    for n, (lib, _) in ICONES.items()
)

SWATCHES = [
    ("bg", "Fond de page"), ("surface", "Surface (cartes)"), ("surface-alt", "Surface alternée"),
    ("ink", "Encre (texte, prix)"), ("ink-muted", "Texte secondaire"), ("on-ink", "Texte sur encre"),
    ("line", "Filet décoratif"), ("line-strong", "Bordure de composant"), ("accent", "Accent"),
    ("on-accent", "Texte sur accent"), ("accent-text", "Accent en texte (liens)"), ("accent-soft", "Accent teinté"),
    ("focus", "Focus clavier"), ("error", "Erreur"),
]
SW = "".join(
    f'<li class="ch-swatch" data-token="{t}"><span class="ch-swatch__chip" style="background:var(--da-color-{t})"></span>'
    f'<span class="ch-swatch__name">{lib}</span><code class="ch-swatch__hex">--da-color-{t}</code>'
    f'<span class="ch-swatch__ratio" aria-live="polite"></span></li>'
    for t, lib in SWATCHES
)
PAIRS = [
    ("ink", "bg", 4.5, "Texte courant"), ("ink-muted", "bg", 4.5, "Texte secondaire"), ("accent-text", "bg", 4.5, "Lien"),
    ("on-accent", "accent", 4.5, "Texte sur accent"), ("on-ink", "ink", 4.5, "Bouton principal (A)"),
    ("line-strong", "bg", 3.0, "Bordure de champ"), ("focus", "bg", 3.0, "Focus"),
    ("status-local-fg", "status-local-bg", 4.5, "Stock local"), ("status-preorder-fg", "status-preorder-bg", 4.5, "Précommande"),
    ("status-new-fg", "status-new-bg", 4.5, "Nouveauté"), ("status-out-fg", "status-out-bg", 4.5, "Rupture"),
    ("status-restock-fg", "status-restock-bg", 4.5, "Alerte réassort"), ("lang-fr-fg", "lang-fr-bg", 4.5, "Badge FR"),
]
PAIR_ROWS = "".join(
    f'<tr data-fg="{fg}" data-bg="{bg}" data-min="{m}"><td>{u}</td>'
    f'<td><span class="ch-sample" style="color:var(--da-color-{fg});background:var(--da-color-{bg})">Aa 209.90</span></td>'
    f'<td><code>{fg}</code> / <code>{bg}</code></td><td class="ch-r"></td><td>{m}:1</td></tr>'
    for fg, bg, m, u in PAIRS
)


# --- components/badges.html ---
_BADGES = head("Badges — composants DA", "Badges de statut produit : FR, Stock local, Précommande, Nouveauté, Rupture, Alerte réassort.") + """<body class="da-root">
""" + BAR + """  <main class="da-container">
    <h1 class="da-title" style="font-size:var(--da-text-2xl);margin:var(--da-space-6) 0 var(--da-space-2)">Badges de statut</h1>
    <p class="da-muted" style="max-width:40rem">Un badge dit un fait vérifiable (langue, stock, date). Il est toujours écrit en toutes lettres et accompagné d'une icône : la couleur seule ne porte jamais l'information. Maximum 3 badges par carte, dans l'ordre ci-dessous.</p>

    <h2 class="da-title" style="font-size:var(--da-text-xl);margin:var(--da-space-6) 0 var(--da-space-3)">Les 6 badges</h2>
    <div class="da-badges" role="list">
      <span class="da-badge da-badge--fr" role="listitem">[[i:langue:14]]FR</span>
      <span class="da-badge da-badge--local" role="listitem">[[i:stock-local:14]]Stock local</span>
      <span class="da-badge da-badge--preorder" role="listitem">[[i:precommande:14]]Précommande</span>
      <span class="da-badge da-badge--new" role="listitem">[[i:nouveaute:14]]Nouveauté</span>
      <span class="da-badge da-badge--out" role="listitem">[[i:rupture:14]]Rupture</span>
      <span class="da-badge da-badge--restock" role="listitem">[[i:alerte:14]]Alerte réassort</span>
    </div>

    <h2 class="da-title" style="font-size:var(--da-text-xl);margin:var(--da-space-6) 0 var(--da-space-3)">Règles d'attribution (automatiques, depuis le catalogue validé)</h2>
    <div style="overflow-x:auto">
    <table style="border-collapse:collapse;width:100%;min-width:560px;font-size:var(--da-text-sm)">
      <thead><tr style="text-align:left;border-bottom:2px solid var(--da-color-ink)"><th style="padding:8px">Badge</th><th style="padding:8px">Condition d'affichage</th><th style="padding:8px">Ne jamais l'afficher si…</th></tr></thead>
      <tbody>
        <tr style="border-bottom:1px solid var(--da-color-line)"><td style="padding:8px"><span class="da-badge da-badge--fr">[[i:langue:14]]FR</span></td><td style="padding:8px">Langue du produit = FR, vérifiée sur la fiche technique ET à réception.</td><td style="padding:8px">Langue inconnue ou ambiguë (la fiche reste en brouillon).</td></tr>
        <tr style="border-bottom:1px solid var(--da-color-line)"><td style="padding:8px"><span class="da-badge da-badge--local">[[i:stock-local:14]]Stock local</span></td><td style="padding:8px">Stock vendable local &gt; 0 (après réservations, dommages et stock de sécurité).</td><td style="padding:8px">La quantité n'existe que chez un tiers ou n'est pas encore réceptionnée.</td></tr>
        <tr style="border-bottom:1px solid var(--da-color-line)"><td style="padding:8px"><span class="da-badge da-badge--preorder">[[i:precommande:14]]Précommande</span></td><td style="padding:8px">Allocation ferme confirmée par écrit et quota de précommande &gt; 0.</td><td style="padding:8px">Allocation non confirmée, ou date de sortie inconnue sans mention « date à confirmer ».</td></tr>
        <tr style="border-bottom:1px solid var(--da-color-line)"><td style="padding:8px"><span class="da-badge da-badge--new">[[i:nouveaute:14]]Nouveauté</span></td><td style="padding:8px">Mise en vente depuis moins de {{N_JOURS_NOUVEAUTE}} jours ET achetable (stock local ou précommande).</td><td style="padding:8px">Produit en rupture : « Nouveauté » ne sert pas d'appât.</td></tr>
        <tr style="border-bottom:1px solid var(--da-color-line)"><td style="padding:8px"><span class="da-badge da-badge--out">[[i:rupture:14]]Rupture</span></td><td style="padding:8px">Stock vendable local = 0 et aucun quota de précommande.</td><td style="padding:8px">—</td></tr>
        <tr><td style="padding:8px"><span class="da-badge da-badge--restock">[[i:alerte:14]]Alerte réassort</span></td><td style="padding:8px">Produit en rupture pour lequel l'inscription à une alerte est ouverte.</td><td style="padding:8px">Un réassort est déjà exclu (fin de série confirmée).</td></tr>
      </tbody>
    </table>
    </div>

    <h2 class="da-title" style="font-size:var(--da-text-xl);margin:var(--da-space-6) 0 var(--da-space-3)">Combinaisons autorisées</h2>
    <ul style="display:grid;gap:var(--da-space-3);padding:0;list-style:none">
      <li class="da-badges"><span class="da-badge da-badge--fr">[[i:langue:14]]FR</span><span class="da-badge da-badge--local">[[i:stock-local:14]]Stock local</span><span class="da-badge da-badge--new">[[i:nouveaute:14]]Nouveauté</span></li>
      <li class="da-badges"><span class="da-badge da-badge--fr">[[i:langue:14]]FR</span><span class="da-badge da-badge--preorder">[[i:precommande:14]]Précommande</span></li>
      <li class="da-badges"><span class="da-badge da-badge--fr">[[i:langue:14]]FR</span><span class="da-badge da-badge--out">[[i:rupture:14]]Rupture</span><span class="da-badge da-badge--restock">[[i:alerte:14]]Alerte réassort</span></li>
    </ul>
    <p class="da-note">[[i:info:18]]<span>Interdit : « Stock local » + « Précommande » sur le même produit (deux promesses différentes = deux variantes ou deux fiches), « Dernières pièces », « Bientôt épuisé », compteurs ou minuteurs.</span></p>

    <h2 class="da-title" style="font-size:var(--da-text-xl);margin:var(--da-space-6) 0 var(--da-space-3)">Code (Shopify / thème)</h2>
    <pre style="overflow-x:auto;padding:var(--da-space-3);background:var(--da-color-surface);border:1px solid var(--da-color-line);font-size:var(--da-text-sm)"><code>&lt;span class="da-badge da-badge--local"&gt;&lt;svg class="da-icon" …&gt;…&lt;/svg&gt;Stock local&lt;/span&gt;
Modificateurs : --fr · --local · --preorder · --new · --out · --restock
Dépendances : tokens/tokens.css + components/components.css</code></pre>
""" + FOOT + """  </main>
</body>
</html>
"""


# --- components/carte-produit.html ---
_CARTE = head("Carte produit — composants DA", "Carte produit : prix CHF, statut de stock explicite, badges ; aucune donnée interne.") + """<body class="da-root">
""" + BAR + """  <main class="da-container">
    <h1 class="da-title" style="font-size:var(--da-text-2xl);margin:var(--da-space-6) 0 var(--da-space-2)">Carte produit</h1>
    <p class="da-muted" style="max-width:42rem">Quatre états réels : stock local, précommande sur allocation ferme, rupture avec alerte, accessoire. Le prix affiché est le prix public CHF validé par le moteur ; le statut de stock est écrit en toutes lettres.</p>
    <p class="da-fictif">Exemples FICTIF : noms, prix et dates ne correspondent à aucune offre réelle.</p>
    <section class="da-products" aria-label="Exemples de cartes produit">
""" + cards + """    </section>

    <h2 class="da-title" style="font-size:var(--da-text-xl);margin:var(--da-space-7) 0 var(--da-space-3)">Anatomie (ordre fixe)</h2>
    <ol style="max-width:42rem">
      <li><strong>Photo réelle</strong> (officielle autorisée ou prise par nous) — jamais d'emballage généré.</li>
      <li><strong>Badges</strong> : langue, puis stock, puis nouveauté (3 maximum).</li>
      <li><strong>Titre exact</strong> : format — extension — langue (BP §7).</li>
      <li><strong>Méta</strong> : format, langue, état scellé.</li>
      <li><strong>Prix public</strong> en CHF, police chiffres tabulaires, arrondi .90 (moteur de prix).</li>
      <li><strong>Statut de stock</strong> explicite + délai réaliste ou date confirmée.</li>
      <li><strong>Action</strong> unique : ajouter, précommander ou m'alerter.</li>
    </ol>
    <p class="da-note">[[i:info:18]]<span>Champs autorisés dans le gabarit : titre, format, langue, état, prix public, statut, délai, limite par commande, photo autorisée. Tout autre champ du catalogue reste interne ; le filtre de publication (module publish) fait foi.</span></p>
""" + FOOT + """  </main>
</body>
</html>
"""


# --- components/banniere.html ---
_BANNIERES = head("Bannières — composants DA", "Bandeau d'annonce, bannière d'accueil, bannière de collection et bannière d'alertes.") + """<body class="da-root">
""" + BAR + """  <style>
    html:not([data-da="b"]) [data-only="b"] { display: none !important; }
  </style>
  <div class="da-annonce" role="note">
    <span>[[i:colis:16]] Livraison en Suisse uniquement</span>
    <span>Frais de livraison affichés avant paiement</span>
    <span><a href="#">Retours : nos conditions</a></span>
  </div>
  <main class="da-container" style="display:grid;gap:var(--da-space-7);padding-block:var(--da-space-6)">
    <p class="da-fictif">Textes d'exemple (FICTIF) ; toute promesse (délai, stock, prix) doit être vraie au moment de la publication.</p>

    <section class="da-banner" aria-labelledby="hero-titre">
      """ + deco_b + """
      <div style="display:grid;gap:var(--da-space-4);position:relative">
        <p class="da-badges" style="margin:0"><span class="da-badge da-badge--fr">[[i:langue:14]]FR</span><span class="da-badge da-badge--local">[[i:stock-local:14]]Stock local</span></p>
        <h1 class="da-title da-banner__title" id="hero-titre">Pokémon JCC en français, expédié depuis la Suisse.</h1>
        <p class="da-banner__text">Stock réel affiché, prix en CHF, précommandes uniquement sur allocation confirmée.</p>
        <div class="da-banner__actions">
          <a class="da-btn da-btn--primary" href="carte-produit.html">Voir le stock local</a>
          <a class="da-btn da-btn--secondary" href="#alertes">Recevoir les alertes</a>
        </div>
      </div>
      <div class="da-banner__media">
        <div class="da-photo" role="img" aria-label="Emplacement : photo réelle de produits FR en stock" style="aspect-ratio:4/3">Photo réelle des boîtes en stock<br>(prise lors de la session photo groupée)</div>
      </div>
    </section>

    <section aria-labelledby="col-titre" style="display:flex;flex-wrap:wrap;align-items:end;justify-content:space-between;gap:var(--da-space-3);padding-bottom:var(--da-space-3);border-bottom:3px solid var(--da-color-ink)">
      <div>
        <p class="da-muted" style="margin:0;font-size:var(--da-text-sm)">Collection</p>
        <h2 class="da-title" id="col-titre" style="font-size:var(--da-text-xl)">Nouveautés en stock local</h2>
      </div>
      <a href="carte-produit.html" style="font-weight:700">Tout voir ({{N_REFERENCES}})</a>
    </section>

    <section class="da-panel" id="alertes" aria-labelledby="alerte-titre" style="display:grid;gap:var(--da-space-3);max-width:40rem">
      <h2 class="da-title" id="alerte-titre" style="font-size:var(--da-text-lg)">[[i:alerte:20]] Alerte réassort par email</h2>
      <p style="margin:0">Choisissez vos formats (displays, ETB, coffrets, accessoires). Un récapitulatif par semaine au maximum, plus les alertes que vous demandez.</p>
      <form style="display:flex;flex-wrap:wrap;gap:var(--da-space-2)" onsubmit="return false">
        <label for="email-alerte" class="da-visually-hidden">Adresse email</label>
        <input id="email-alerte" type="email" autocomplete="email" placeholder="vous@exemple.ch" style="flex:1 1 220px;min-height:var(--da-touch-target);padding:8px 12px;border:2px solid var(--da-color-line-strong);border-radius:var(--da-radius-md);background:var(--da-color-surface);color:var(--da-color-ink);font:inherit">
        <button type="submit" class="da-btn da-btn--primary">M'inscrire</button>
      </form>
      <p class="da-muted" style="margin:0;font-size:var(--da-text-sm)">Désinscription en un clic dans chaque email. {{LIEN_CONFIDENTIALITE}} (texte de consentement à valider).</p>
    </section>
""" + FOOT + """  </main>
</body>
</html>
"""


# --- components/page-produit.html ---
_PRODUIT = head("Page produit — application DA", "Application des directions A et B à une fiche produit mobile-first.") + """<body class="da-root">
""" + BAR + """  <div class="da-annonce" role="note"><span>[[i:colis:16]] Livraison en Suisse uniquement · frais affichés avant paiement</span></div>
  <header class="da-container" style="display:flex;align-items:center;justify-content:space-between;gap:var(--da-space-3);padding-block:var(--da-space-3);border-bottom:1px solid var(--da-color-line)">
    <a href="#" aria-label="Accueil">
      <img class="lg lg-a-light" src="../logo/a/logo-a-horizontal.svg" alt="{{NOM_BOUTIQUE}}" width="180" height="24">
      <img class="lg lg-a-dark" src="../logo/a/logo-a-horizontal-fond-sombre.svg" alt="{{NOM_BOUTIQUE}}" width="180" height="24">
      <img class="lg lg-b-light" src="../logo/b/logo-b-principal.svg" alt="{{NOM_BOUTIQUE}}" width="180" height="25">
      <img class="lg lg-b-dark" src="../logo/b/logo-b-principal-fond-sombre.svg" alt="{{NOM_BOUTIQUE}}" width="180" height="25">
    </a>
    <nav aria-label="Raccourcis" style="display:flex;gap:var(--da-space-2)">
      <a class="da-btn da-btn--secondary" href="#" aria-label="Rechercher" style="padding:8px">[[i:recherche:20]]</a>
      <a class="da-btn da-btn--secondary" href="#" aria-label="Panier" style="padding:8px">[[i:panier:20]]</a>
    </nav>
  </header>
  <style>
    html:not([data-da="b"]) [data-only="b"] { display: none !important; }
    html[data-da="b"] [data-only="a"] { display: none !important; }
    .lg { display: none !important; }
    html:not([data-da="b"]):not([data-theme="dark"]) .lg-a-light,
    html[data-da="b"]:not([data-theme="dark"]) .lg-b-light,
    html:not([data-da="b"])[data-theme="dark"] .lg-a-dark,
    html[data-da="b"][data-theme="dark"] .lg-b-dark { display: block !important; }
    @media (prefers-color-scheme: dark) {
      html:not([data-da="b"]):not([data-theme]) .lg-a-light,
      html[data-da="b"]:not([data-theme]) .lg-b-light { display: none !important; }
      html:not([data-da="b"]):not([data-theme]) .lg-a-dark,
      html[data-da="b"]:not([data-theme]) .lg-b-dark { display: block !important; }
    }
  </style>
  <main class="da-container">
    <p class="da-fictif">Fiche d'exemple — FICTIF (BP §7) : titre, prix et dates ne correspondent à aucune offre réelle. En production, chaque champ vient du catalogue validé.</p>
    <nav aria-label="Fil d'Ariane"><ol class="da-breadcrumb"><li><a href="#">Accueil</a></li><li><a href="#">Displays</a></li><li aria-current="page">Extension exemple</li></ol></nav>
    <div class="da-product">
      <section class="da-gallery" aria-label="Photos du produit">
        <div class="da-photo" role="img" aria-label="Emplacement : photo réelle, face avant">Photo réelle — face avant<br>(boîte FR, fond neutre)</div>
        <div class="da-gallery__thumbs">
          <div class="da-photo" role="img" aria-label="Emplacement : dos">Dos</div>
          <div class="da-photo" role="img" aria-label="Emplacement : côté avec mention de langue">Mention FR</div>
          <div class="da-photo" role="img" aria-label="Emplacement : film scellé">Scellé</div>
          <div class="da-photo" role="img" aria-label="Emplacement : échelle (main ou règle)">Échelle</div>
        </div>
      </section>
      <section class="da-product__info" aria-labelledby="produit-titre">
        <div class="da-badges"><span class="da-badge da-badge--fr">[[i:langue:14]]FR</span><span class="da-badge da-badge--local">[[i:stock-local:14]]Stock local</span></div>
        <h1 class="da-title da-product__title" id="produit-titre">Display — Extension exemple — FR</h1>
        <p class="da-muted" style="margin:0;font-size:var(--da-text-sm)">Réf. {{SKU}} · EAN {{EAN_SI_EXISTANT}}</p>
        <div>
          <p class="da-price da-product__price">CHF 209.90</p>
          <p class="da-muted" style="margin:0;font-size:var(--da-text-sm)">{{MENTION_TVA}} · <a href="#">frais de livraison</a> calculés avant paiement</p>
        </div>
        <div class="da-panel" style="display:grid;gap:var(--da-space-3)">
          <p class="da-stock da-stock--local">[[i:stock-local:18]]<span>En stock local — prêt à partir<span class="da-stock__detail">Expédié depuis la Suisse sous {{DELAI_EXPEDITION}} · 2 maximum par commande</span></span></p>
          <div style="display:flex;flex-wrap:wrap;gap:var(--da-space-3);align-items:center">
            <div class="da-qty" role="group" aria-label="Quantité">
              <button type="button" aria-label="Retirer une unité">−</button>
              <input type="number" value="1" min="1" max="2" inputmode="numeric" aria-label="Quantité (2 maximum)">
              <button type="button" aria-label="Ajouter une unité">+</button>
            </div>
            <button type="button" class="da-btn da-btn--primary" style="flex:1 1 200px">[[i:panier:18]] Ajouter au panier</button>
          </div>
        </div>
        <dl class="da-facts">
          <dt>Format</dt><dd>Display (boîte de boosters)</dd>
          <dt>Langue</dt><dd>Français (FR), vérifiée à réception</dd>
          <dt>Extension</dt><dd>{{EXTENSION}}</dd>
          <dt>Contenu</dt><dd>{{CONTENU_VALIDE}} (selon la fiche technique de l'éditeur)</dd>
          <dt>État</dt><dd>Neuf, scellé d'origine</dd>
          <dt>Sortie</dt><dd>{{DATE_SORTIE_CONFIRMEE}}</dd>
        </dl>
        <p class="da-note">[[i:scelle:18]]<span>Produit scellé : le contenu des boosters est aléatoire. Nous ne promettons aucune carte particulière ni aucune valeur future.</span></p>
        <section aria-labelledby="desc-titre">
          <h2 class="da-title" id="desc-titre" style="font-size:var(--da-text-lg);margin-bottom:var(--da-space-2)">Pour qui ?</h2>
          <p style="margin:0">Pour ouvrir une extension sur la durée ou compléter une collection. Pour débuter ou offrir, comparez avec l'ETB : <a href="#">ETB ou display, que choisir ?</a></p>
        </section>
        <section aria-labelledby="mixte-titre">
          <h2 class="da-title" id="mixte-titre" style="font-size:var(--da-text-lg);margin-bottom:var(--da-space-2)">Commande mixte</h2>
          <p style="margin:0">Si votre panier contient une précommande, les articles en stock local partent d'abord ; la précommande suit à réception. <a href="#">Conditions</a>.</p>
        </section>
      </section>
    </div>
""" + FOOT + """  </main>
</body>
</html>
"""


# --- CHARTE.html ---
_CHARTE = head("Mini-charte — Quai des Cartes (nom de travail)",
            "Mini-charte de marque : logo, couleurs, typographie, grille, composants, photo, ton, do/don't, applications. Proposition à valider.",
            prefix="") + """<body class="da-root">
""" + BAR + """  <style>
    html:not([data-da="b"]) [data-only="b"] { display: none !important; }
    html[data-da="b"] [data-only="a"] { display: none !important; }
    .lg { display: none !important; }
    html:not([data-da="b"]):not([data-theme="dark"]) .lg-a-light,
    html[data-da="b"]:not([data-theme="dark"]) .lg-b-light,
    html:not([data-da="b"])[data-theme="dark"] .lg-a-dark,
    html[data-da="b"][data-theme="dark"] .lg-b-dark { display: block !important; }
    @media (prefers-color-scheme: dark) {
      html:not([data-da="b"]):not([data-theme]) .lg-a-light,
      html[data-da="b"]:not([data-theme]) .lg-b-light { display: none !important; }
      html:not([data-da="b"]):not([data-theme]) .lg-a-dark,
      html[data-da="b"]:not([data-theme]) .lg-b-dark { display: block !important; }
    }
    .ch-layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--da-space-6); padding-block: var(--da-space-5) var(--da-space-8); }
    @media (min-width: 1000px) { .ch-layout { grid-template-columns: 220px minmax(0, 1fr); } .ch-toc { position: sticky; top: 64px; align-self: start; } }
    .ch-toc ol { margin: 0; padding-left: 1.4em; display: grid; gap: 4px; font-size: var(--da-text-sm); }
    .ch-toc a { color: var(--da-color-ink); }
    .ch-section { padding-block: var(--da-space-6); border-top: 3px solid var(--da-color-ink); scroll-margin-top: 64px; }
    [data-da="b"] .ch-section { border-top: 1px solid var(--da-color-line-strong); }
    .ch-section > h2 { font-size: var(--da-text-xl); margin-bottom: var(--da-space-4); }
    .ch-section h3 { font-family: var(--da-font-text); font-size: var(--da-text-md); margin: var(--da-space-5) 0 var(--da-space-2); }
    .ch-num { display: inline-block; min-width: 2.2em; color: var(--da-color-accent-text); font-family: var(--da-font-price); }
    .ch-lead { font-size: var(--da-text-md); max-width: 46rem; }
    .ch-cols { display: grid; gap: var(--da-space-4); }
    @media (min-width: 700px) { .ch-cols { grid-template-columns: repeat(2, minmax(0, 1fr)); } .ch-cols--3 { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    .ch-tile { display: grid; place-items: center; min-height: 160px; margin: 0; padding: var(--da-space-5); background: #FFFFFF; border: 1px solid var(--da-color-line); border-radius: var(--da-radius-md); }
    figure.ch-tile figcaption { color: #4A4843; }
    .ch-tile--dark { background: #111111; border-color: #111111; }
    .ch-tile figcaption, .ch-cap { margin-top: var(--da-space-2); font-size: var(--da-text-sm); color: var(--da-color-ink-muted); text-align: center; }
    figure.ch-tile.ch-tile--dark figcaption { color: #CFCFCF; }
    .ch-tile img { max-height: 120px; width: auto; }
    .ch-clear { position: relative; display: inline-block; padding: 28px; background: #FFFFFF; border: 2px dashed #B33F00; }
    .ch-clear img { max-height: 110px; width: auto; }
    .ch-clear span { position: absolute; font: 600 12px var(--da-font-price); color: #B33F00; }
    table.ch-table { width: 100%; border-collapse: collapse; font-size: var(--da-text-sm); }
    .ch-table th, .ch-table td { padding: 8px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--da-color-line); }
    .ch-table thead th { border-bottom: 2px solid var(--da-color-ink); }
    .ch-scroll { overflow-x: auto; }
    .ch-swatches { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--da-space-3); padding: 0; list-style: none; }
    .ch-swatch { display: grid; gap: 2px; padding: var(--da-space-2); background: var(--da-color-surface); border: 1px solid var(--da-color-line); border-radius: var(--da-radius-md); font-size: var(--da-text-sm); }
    .ch-swatch__chip { height: 56px; border-radius: var(--da-radius-sm); border: 1px solid var(--da-color-line); }
    .ch-swatch__name { font-weight: 700; }
    .ch-swatch__hex { font-size: var(--da-text-xs); color: var(--da-color-ink-muted); overflow-wrap: anywhere; }
    .ch-swatch__ratio { font-family: var(--da-font-price); font-size: var(--da-text-xs); }
    .ch-sample { display: inline-block; padding: 4px 10px; border-radius: var(--da-radius-sm); font-weight: 700; }
    .ch-r { font-family: var(--da-font-price); font-weight: 600; white-space: nowrap; }
    .ch-spec { display: grid; gap: var(--da-space-2); padding: var(--da-space-4); background: var(--da-color-surface); border: 1px solid var(--da-color-line); border-radius: var(--da-radius-md); }
    .ch-spec small { color: var(--da-color-ink-muted); font-family: var(--da-font-price); }
    .ch-gridviz { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--da-gutter-mobile); padding: 0 var(--da-margin-mobile); height: 90px; background: var(--da-color-surface-alt); }
    .ch-gridviz span { background: var(--da-color-accent-soft); border: 1px solid var(--da-color-accent-text); }
    .ch-gridviz span:nth-child(n+5) { display: none; }
    @media (min-width: 600px) { .ch-gridviz { grid-template-columns: repeat(8, 1fr); } .ch-gridviz span:nth-child(n+5) { display: block; } .ch-gridviz span:nth-child(n+9) { display: none; } }
    @media (min-width: 900px) { .ch-gridviz { grid-template-columns: repeat(12, 1fr); gap: var(--da-gutter-desktop); } .ch-gridviz span:nth-child(n+9) { display: block; } }
    .ch-space { display: grid; gap: 6px; }
    .ch-space div { display: flex; align-items: center; gap: var(--da-space-3); font: 500 var(--da-text-sm) var(--da-font-price); }
    .ch-space i { display: block; height: 14px; background: var(--da-color-accent); }
    .ch-icons { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: var(--da-space-3); }
    .ch-icon { margin: 0; display: grid; justify-items: center; gap: 6px; padding: var(--da-space-3); background: var(--da-color-surface); border: 1px solid var(--da-color-line); border-radius: var(--da-radius-md); font-size: var(--da-text-xs); text-align: center; }
    .ch-dd { display: grid; gap: var(--da-space-3); }
    @media (min-width: 700px) { .ch-dd { grid-template-columns: 1fr 1fr; } }
    .ch-do, .ch-dont { padding: var(--da-space-4); border-radius: var(--da-radius-md); background: var(--da-color-surface); border: 1px solid var(--da-color-line); }
    .ch-do { border-top: 6px solid var(--da-color-status-local-fg); }
    .ch-dont { border-top: 6px solid var(--da-color-error); }
    .ch-do h3, .ch-dont h3 { margin-top: 0; }
    .ch-do ul, .ch-dont ul { margin: 0; padding-left: 1.2em; display: grid; gap: 6px; }
    .ch-apps { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--da-space-3); }
    .ch-apps figure { margin: 0; }
    .ch-apps img { width: 100%; height: auto; border: 1px solid var(--da-color-line); background: #fff; }
    .ch-check { display: grid; gap: var(--da-space-2); padding: 0; list-style: none; }
    .ch-check li { display: flex; gap: var(--da-space-2); align-items: flex-start; }
    .ch-check li::before { content: ""; flex: none; width: 18px; height: 18px; margin-top: 3px; border: 2px solid var(--da-color-ink); border-radius: var(--da-radius-sm); }
  </style>
  <header class="da-container" style="padding-top:var(--da-space-6)">
    <img class="lg lg-a-light" src="logo/a/logo-a-principal.svg" alt="Quai des Cartes — logo direction A (nom de travail)" width="220" height="104">
    <img class="lg lg-a-dark" src="logo/a/logo-a-principal-fond-sombre.svg" alt="Quai des Cartes — logo direction A (nom de travail)" width="220" height="104">
    <img class="lg lg-b-light" src="logo/b/logo-b-principal.svg" alt="quai des cartes — logo direction B (nom de travail)" width="280" height="39">
    <img class="lg lg-b-dark" src="logo/b/logo-b-principal-fond-sombre.svg" alt="quai des cartes — logo direction B (nom de travail)" width="280" height="39">
    <h1 class="da-title" style="font-size:var(--da-text-2xl);margin-top:var(--da-space-5)">Mini-charte de marque</h1>
    <p class="ch-lead">Proposition du 4 octobre 2026. Nom de travail <strong>« Quai des Cartes »</strong> et identité <strong>non validés</strong> : la responsable choisit une direction (A ou B) et valide le nom une seule fois, après vérification humaine du domaine et des marques (voir <a href="NAMING.md">NAMING.md</a>). Utilisez la barre d'aperçu pour comparer les directions en mode clair et sombre.</p>
  </header>
  <div class="da-container ch-layout">
    <nav class="ch-toc" aria-label="Sommaire">
      <ol>
        <li><a href="#intro">Introduction</a></li><li><a href="#logo">Logo</a></li><li><a href="#couleurs">Couleurs</a></li>
        <li><a href="#typo">Typographie</a></li><li><a href="#grille">Grille</a></li><li><a href="#composants">Composants</a></li>
        <li><a href="#icones">Iconographie</a></li><li><a href="#photo">Photographie</a></li><li><a href="#ton">Ton</a></li>
        <li><a href="#dodont">À faire / à éviter</a></li><li><a href="#applications">Applications</a></li><li><a href="#validation">Validation</a></li>
      </ol>
    </nav>
    <main>

      <section class="ch-section" id="intro" aria-labelledby="t1">
        <h2 class="da-title" id="t1"><span class="ch-num">01</span>Introduction</h2>
        <p class="ch-lead">Promesse (BP §1) : <strong>Pokémon FR, expédié depuis la Suisse, avec une disponibilité lisible, des produits identifiés correctement et un service fiable.</strong> La marque est indépendante : « Pokémon » désigne les produits vendus, jamais la boutique.</p>
        <p>Rôle de la DA dans l'étoile polaire (contribution nette cumulée) : faire acheter en confiance (moins d'hésitations, moins d'erreurs de langue ou de format, donc moins de SAV et de retours) avec un coût de production minimal. Une belle DA ne compense pas une marge insuffisante.</p>
        <div class="ch-scroll"><table class="ch-table">
          <thead><tr><th>Critère</th><th>Direction A — Quai (signal)</th><th>Direction B — Pochette (collection)</th></tr></thead>
          <tbody>
            <tr><td>Idée</td><td>Signalétique de quai et étiquette logistique : précis, fiable, suisse.</td><td>Cartes qu'on sort de la pochette : vif, rond, collection.</td></tr>
            <tr><td>Accent</td><td>Orange Signal #FF5B14 (texte dessus : noir)</td><td>Violet Électrique #5A31F4 (texte dessus : blanc)</td></tr>
            <tr><td>Typographie</td><td>Archivo (titres capitales) · Inter · IBM Plex Mono (prix)</td><td>Bricolage Grotesque (titres bas-de-casse) · DM Sans · Space Grotesk (prix)</td></tr>
            <tr><td>Formes</td><td>Angles vifs, filets, barre-quai</td><td>Coins arrondis, pastilles, carte inclinée</td></tr>
            <tr><td>Force</td><td>Crédibilité, lisibilité, sobriété : vieillit bien, multi-TCG facile.</td><td>Enthousiasme, mémorisation, réseaux sociaux.</td></tr>
            <tr><td>Risque</td><td>Peut paraître froid sans photos vivantes.</td><td>Violet moins « logistique » ; demande plus de discipline.</td></tr>
          </tbody>
        </table></div>
      </section>

      <section class="ch-section" id="logo" aria-labelledby="t2">
        <h2 class="da-title" id="t2"><span class="ch-num">02</span>Logo</h2>
        <p>Lettrage original dessiné en contours (aucune police, aucun personnage, aucun symbole de licence). Fichiers : <code>logo/a/</code> et <code>logo/b/</code> ; règles complètes dans <a href="logo/REGLES_LOGO.md">REGLES_LOGO.md</a>.</p>
        <div class="ch-cols ch-cols--3" data-only="a">
          <figure class="ch-tile"><img src="logo/a/logo-a-principal.svg" alt="Logo principal A" width="200" height="94"><figcaption>Principal (empilé)</figcaption></figure>
          <figure class="ch-tile"><img src="logo/a/logo-a-horizontal.svg" alt="Logo horizontal A" width="220" height="29"><figcaption>Horizontal (en-tête, email)</figcaption></figure>
          <figure class="ch-tile"><img src="logo/a/logo-a-monogramme.svg" alt="Monogramme A" width="96" height="96"><figcaption>Monogramme (avatar, sticker)</figcaption></figure>
          <figure class="ch-tile"><img src="logo/a/logo-a-mono-noir.svg" alt="Logo A noir" width="200" height="94"><figcaption>Mono noir (tampon, fax, gravure)</figcaption></figure>
          <figure class="ch-tile ch-tile--dark"><img src="logo/a/logo-a-mono-blanc.svg" alt="Logo A blanc" width="200" height="94"><figcaption>Mono blanc sur fond foncé</figcaption></figure>
          <figure class="ch-tile"><img src="logo/a/favicon.svg" alt="Favicon A" width="48" height="48"><figcaption>Favicon (16–48 px)</figcaption></figure>
        </div>
        <div class="ch-cols ch-cols--3" data-only="b">
          <figure class="ch-tile"><img src="logo/b/logo-b-principal.svg" alt="Logo principal B" width="240" height="33"><figcaption>Principal (une ligne)</figcaption></figure>
          <figure class="ch-tile"><img src="logo/b/logo-b-empile.svg" alt="Logo empilé B" width="170" height="72"><figcaption>Empilé (sticker, carte)</figcaption></figure>
          <figure class="ch-tile"><img src="logo/b/logo-b-monogramme.svg" alt="Monogramme B" width="96" height="96"><figcaption>Monogramme (avatar)</figcaption></figure>
          <figure class="ch-tile"><img src="logo/b/logo-b-mono-noir.svg" alt="Logo B noir" width="240" height="33"><figcaption>Mono noir</figcaption></figure>
          <figure class="ch-tile ch-tile--dark"><img src="logo/b/logo-b-mono-blanc.svg" alt="Logo B blanc" width="240" height="33"><figcaption>Mono blanc sur fond foncé</figcaption></figure>
          <figure class="ch-tile"><img src="logo/b/favicon.svg" alt="Favicon B" width="48" height="48"><figcaption>Favicon (16–48 px)</figcaption></figure>
        </div>
        <h3>Zone de protection et tailles minimales</h3>
        <div class="ch-cols">
          <div style="display:grid;place-items:center;padding:var(--da-space-4)">
            <div class="ch-clear" data-only="a"><img src="logo/a/logo-a-principal.svg" alt="" width="190" height="90"><span style="top:6px;left:8px">X</span><span style="bottom:6px;right:8px">X</span></div>
            <div class="ch-clear" data-only="b"><img src="logo/b/logo-b-principal.svg" alt="" width="240" height="33"><span style="top:6px;left:8px">X</span><span style="bottom:6px;right:8px">X</span></div>
          </div>
          <div>
            <p data-only="a"><strong>X = 2 × l'épaisseur de la barre-quai</strong> (≈ 13 % de la hauteur du logo principal). Rien ne pénètre dans cette marge : texte, bord d'image, autre logo.</p>
            <p data-only="b"><strong>X = la moitié de la hauteur d'x</strong> (hauteur d'un « a »), soit ≈ 29 % de la hauteur du logo. Le point du « i » reste toujours violet ou de la couleur du texte (version mono).</p>
            <div class="ch-scroll"><table class="ch-table">
              <thead><tr><th>Version</th><th>Écran (largeur)</th><th>Impression (largeur)</th></tr></thead>
              <tbody data-only="a">
                <tr><td>Principal empilé</td><td>96 px</td><td>25 mm</td></tr>
                <tr><td>Horizontal</td><td>140 px</td><td>35 mm</td></tr>
                <tr><td>Monogramme</td><td>24 px</td><td>7 mm</td></tr>
                <tr><td>En dessous</td><td colspan="2">favicon.svg (16–32 px)</td></tr>
              </tbody>
              <tbody data-only="b">
                <tr><td>Principal une ligne</td><td>120 px</td><td>30 mm</td></tr>
                <tr><td>Empilé</td><td>80 px</td><td>20 mm</td></tr>
                <tr><td>Monogramme</td><td>24 px</td><td>8 mm</td></tr>
                <tr><td>En dessous</td><td colspan="2">favicon.svg (16–32 px)</td></tr>
              </tbody>
            </table></div>
          </div>
        </div>
      </section>

      <section class="ch-section" id="couleurs" aria-labelledby="t3">
        <h2 class="da-title" id="t3"><span class="ch-num">03</span>Couleurs</h2>
        <p>Fond clair neutre, contraste noir, un seul accent vif. Proportions indicatives : <strong>70 % neutres, 20 % encre, 10 % accent au maximum.</strong> Les couleurs de statut sont fonctionnelles : elles ne servent jamais de décoration. Les ratios ci-dessous sont <strong>calculés en direct</strong> (WCAG 2.x, tronqués à 2 décimales) à partir des variables actives ; ils changent avec la direction et le mode.</p>
        <ul class="ch-swatches">""" + SW + """</ul>
        <h3>Paires vérifiées (texte ≥ 4.5:1, bordures et focus ≥ 3:1)</h3>
        <div class="ch-scroll"><table class="ch-table" id="ch-pairs">
          <thead><tr><th>Usage</th><th>Aperçu</th><th>Tokens</th><th>Ratio</th><th>Seuil</th></tr></thead>
          <tbody>""" + PAIR_ROWS + """</tbody>
        </table></div>
        <p class="da-muted" style="font-size:var(--da-text-sm)">Liste exhaustive (96 paires, 2 directions × 2 modes) : <a href="DIRECTION_A.md">DIRECTION_A.md</a>, <a href="DIRECTION_B.md">DIRECTION_B.md</a>, contrôlée par <code>tools/verifier_da.py</code>.</p>
      </section>

      <section class="ch-section" id="typo" aria-labelledby="t4">
        <h2 class="da-title" id="t4"><span class="ch-num">04</span>Typographie</h2>
        <p>Trois rôles, trois polices Google Fonts (licence SIL Open Font License, à reconfirmer sur fonts.google.com au moment de l'achat du thème).</p>
        <div class="ch-cols ch-cols--3">
          <div class="ch-spec"><small>Titres · --da-font-display</small><p class="da-title" style="font-size:var(--da-text-2xl)">Display FR en stock</p><small data-only="a">Archivo 800, capitales, largeur 112 %</small><small data-only="b">Bricolage Grotesque 800, bas-de-casse</small></div>
          <div class="ch-spec"><small>Texte · --da-font-text</small><p style="margin:0">Expédié depuis la Suisse. Langue vérifiée à réception, contenu selon la fiche de l'éditeur.</p><small data-only="a">Inter 400 / 600 / 700</small><small data-only="b">DM Sans 400 / 500 / 700</small></div>
          <div class="ch-spec"><small>Prix · --da-font-price</small><p class="da-price" style="margin:0;font-size:var(--da-text-2xl)">CHF 209.90</p><small data-only="a">IBM Plex Mono 600 (chasse fixe)</small><small data-only="b">Space Grotesk 700 (chiffres tabulaires)</small></div>
        </div>
        <h3>Échelle (mobile d'abord)</h3>
        <div class="ch-scroll"><table class="ch-table">
          <thead><tr><th>Token</th><th>Taille</th><th>Usage</th></tr></thead>
          <tbody>
            <tr><td><code>--da-text-display</code></td><td>36 → 64 px (fluide)</td><td>Accroche de bannière</td></tr>
            <tr><td><code>--da-text-2xl</code></td><td>36 px</td><td>Titre de page, prix de fiche</td></tr>
            <tr><td><code>--da-text-xl</code></td><td>28 px</td><td>Titre de section</td></tr>
            <tr><td><code>--da-text-lg</code></td><td>22 px</td><td>Prix sur carte</td></tr>
            <tr><td><code>--da-text-base</code></td><td>16 px</td><td>Texte courant (jamais moins sur mobile)</td></tr>
            <tr><td><code>--da-text-sm</code></td><td>14 px</td><td>Badges, méta</td></tr>
            <tr><td><code>--da-text-xs</code></td><td>12 px</td><td>Mentions (jamais un prix ni un statut)</td></tr>
          </tbody>
        </table></div>
        <h3>Formats suisses</h3>
        <p>Prix : <code>CHF 209.90</code> (CHF devant, point décimal, apostrophe des milliers : <code>CHF 1’209.90</code>). Dates : <code>14.11.2026</code>. Langue : <code>FR</code> en capitales dans les badges.</p>
      </section>

      <section class="ch-section" id="grille" aria-labelledby="t5">
        <h2 class="da-title" id="t5"><span class="ch-num">05</span>Grille et espacements</h2>
        <p>4 colonnes (mobile) → 8 (≥ 600 px) → 12 (≥ 900 px). Marges 16 / 32 px, gouttières 16 / 24 px, largeur max 1200 px. Cible tactile 44 px minimum. Produits : 2 par ligne sur mobile, 4 sur ordinateur.</p>
        <div class="ch-gridviz" aria-hidden="true">""" + "<span></span>" * 12 + """</div>
        <p class="ch-cap">Redimensionnez la fenêtre : la grille affichée suit les points de rupture.</p>
        <h3>Espacements (base 4 px)</h3>
        <div class="ch-space">""" + "".join(f'<div><i style="width:{v}px"></i>--da-space-{k} · {v} px</div>' for k, v in [(1, 4), (2, 8), (3, 12), (4, 16), (5, 24), (6, 32), (7, 48), (8, 64), (9, 96)]) + """</div>
      </section>

      <section class="ch-section" id="composants" aria-labelledby="t6">
        <h2 class="da-title" id="t6"><span class="ch-num">06</span>Composants</h2>
        <p>Pages de référence : <a href="components/badges.html">badges</a>, <a href="components/carte-produit.html">carte produit</a>, <a href="components/banniere.html">bannières</a>, <a href="components/page-produit.html">page produit</a>, emails <a href="components/email-transactionnel-a.html">A</a> / <a href="components/email-transactionnel-b.html">B</a>.</p>
        <h3>Badges</h3>
        <div class="da-badges">
          <span class="da-badge da-badge--fr">[[i:langue:14]]FR</span>
          <span class="da-badge da-badge--local">[[i:stock-local:14]]Stock local</span>
          <span class="da-badge da-badge--preorder">[[i:precommande:14]]Précommande</span>
          <span class="da-badge da-badge--new">[[i:nouveaute:14]]Nouveauté</span>
          <span class="da-badge da-badge--out">[[i:rupture:14]]Rupture</span>
          <span class="da-badge da-badge--restock">[[i:alerte:14]]Alerte réassort</span>
        </div>
        <h3>Boutons</h3>
        <div style="display:flex;flex-wrap:wrap;gap:var(--da-space-3)">
          <button type="button" class="da-btn da-btn--primary">[[i:panier:18]] Ajouter au panier</button>
          <button type="button" class="da-btn da-btn--secondary">M'alerter du réassort</button>
          <button type="button" class="da-btn da-btn--accent">Voir les nouveautés</button>
          <button type="button" class="da-btn da-btn--primary" disabled>Indisponible</button>
        </div>
        <h3>Carte produit (exemple FICTIF)</h3>
        <div class="da-products" style="max-width:640px">
          <article class="da-card" aria-labelledby="c1">
            <div class="da-photo" role="img" aria-label="Emplacement photo réelle">Photo produit réelle</div>
            <div class="da-badges"><span class="da-badge da-badge--fr">[[i:langue:14]]FR</span><span class="da-badge da-badge--local">[[i:stock-local:14]]Stock local</span></div>
            <h4 class="da-card__title" id="c1"><a href="components/page-produit.html">Display — Extension exemple — FR</a></h4>
            <p class="da-card__price da-price">CHF 209.90</p>
            <p class="da-stock da-stock--local">[[i:stock-local:16]]<span>En stock local<span class="da-stock__detail">Expédié sous {{DELAI_EXPEDITION}}</span></span></p>
            <button type="button" class="da-btn da-btn--primary da-btn--block da-card__cta">Ajouter au panier</button>
          </article>
          <article class="da-card" aria-labelledby="c2">
            <div class="da-photo" role="img" aria-label="Emplacement photo réelle">Photo produit réelle</div>
            <div class="da-badges"><span class="da-badge da-badge--fr">[[i:langue:14]]FR</span><span class="da-badge da-badge--preorder">[[i:precommande:14]]Précommande</span></div>
            <h4 class="da-card__title" id="c2"><a href="components/page-produit.html">Coffret — Extension exemple 2 — FR</a></h4>
            <p class="da-card__price da-price">CHF 59.90</p>
            <p class="da-stock da-stock--preorder">[[i:precommande:16]]<span>Précommande sur allocation confirmée<span class="da-stock__detail">Sortie prévue le {{DATE_SORTIE}}</span></span></p>
            <button type="button" class="da-btn da-btn--primary da-btn--block da-card__cta">Précommander</button>
          </article>
        </div>
      </section>

      <section class="ch-section" id="icones" aria-labelledby="t7">
        <h2 class="da-title" id="t7"><span class="ch-num">07</span>Iconographie</h2>
        <p>Pictogrammes originaux au trait de 2 px sur grille de 24 px, couleur du texte. Direction A : extrémités carrées ; direction B : extrémités arrondies. Une icône accompagne toujours un libellé. Sprite : <code>components/icones.svg</code>.</p>
        <div class="ch-icons">""" + ICON_GRID + """</div>
        <p class="da-note" style="margin-top:var(--da-space-4)">[[i:info:18]]<span>Interdits : symboles d'énergie ou de types, Poké Ball, éclair façon personnage, silhouettes de créatures, logos d'éditeurs. Pour une icône manquante, partir d'une bibliothèque libre (ex. Lucide, licence ISC) et l'ajuster au trait 2 px.</span></p>
      </section>

      <section class="ch-section" id="photo" aria-labelledby="t8">
        <h2 class="da-title" id="t8"><span class="ch-num">08</span>Photographie</h2>
        <p><strong>Uniquement des photos réelles</strong> : visuels officiels dont l'usage est autorisé par écrit, ou photos prises par la boutique lors d'une session groupée (BP §8). Jamais d'emballage généré, de montage d'un produit non reçu ni de carte « rare » mise en avant.</p>
        <div class="ch-cols">
          <div>
            <h3>Prise de vue</h3>
            <ul>
              <li>Fond : <span data-only="a">papier gris chaud proche de <code>#ECEAE4</code>, lumière du jour latérale, ombre courte et nette.</span><span data-only="b">papier gris clair proche de <code>#E9E9F0</code>, lumière diffuse, légère inclinaison des boîtes autorisée.</span></li>
              <li>Cadrage 1:1 pour la fiche (produit ≈ 70 % de la surface), 4:5 et 9:16 pour les réseaux.</li>
              <li>Balance des blancs neutre ; retouche limitée à l'exposition, au recadrage et au détourage.</li>
              <li>Mention de langue (FR) lisible sur au moins une vue.</li>
            </ul>
          </div>
          <div>
            <h3>Liste de vues par produit</h3>
            <ol>
              <li>Face avant (photo principale)</li>
              <li>Dos (contenu imprimé lisible)</li>
              <li>Côté avec mention de langue</li>
              <li>Film / scellé intact</li>
              <li>Échelle (main ou objet courant)</li>
            </ol>
          </div>
        </div>
      </section>

      <section class="ch-section" id="ton" aria-labelledby="t9">
        <h2 class="da-title" id="t9"><span class="ch-num">09</span>Ton et rédaction</h2>
        <p>Précis, accessible, sans jargon inutile, <strong>sans fausse urgence</strong> (BP §8). On montre les stocks et délais réellement proposés. Tutoiement exclu, vouvoiement chaleureux.</p>
        <div class="ch-scroll"><table class="ch-table">
          <thead><tr><th>À dire</th><th>À éviter</th></tr></thead>
          <tbody>
            <tr><td>« En stock local : expédié depuis la Suisse sous 2 jours ouvrables. » (si vrai)</td><td>« DERNIÈRES PIÈCES !!! Dépêchez-vous »</td></tr>
            <tr><td>« Précommande sur allocation confirmée, sortie prévue le 14.11.2026. »</td><td>« Réservez avant tout le monde ! » sans allocation</td></tr>
            <tr><td>« Le contenu des boosters est aléatoire. »</td><td>« Cartes rares garanties », « investissement », « valeur qui va monter »</td></tr>
            <tr><td>« ETB ou display : le bon choix selon votre usage. »</td><td>Jargon non expliqué (« pull rates », « hit »)</td></tr>
            <tr><td>« Boutique indépendante basée en Suisse. »</td><td>« Boutique officielle Pokémon », « partenaire officiel »</td></tr>
            <tr><td>« Rupture : aucune date de réassort confirmée. Activez l'alerte. »</td><td>« Bientôt de retour ! » sans date ni commande fournisseur confirmée</td></tr>
          </tbody>
        </table></div>
      </section>

      <section class="ch-section" id="dodont" aria-labelledby="t10">
        <h2 class="da-title" id="t10"><span class="ch-num">10</span>À faire / à éviter</h2>
        <div class="ch-dd">
          <div class="ch-do"><h3>À faire</h3><ul>
            <li>Utiliser les fichiers SVG fournis, sans les redessiner.</li>
            <li>Garder le fond clair neutre et un seul accent par visuel.</li>
            <li>Écrire le statut de stock en toutes lettres + icône.</li>
            <li>Reprendre le prix validé par le moteur au moment de publier.</li>
            <li>Nommer les produits : format — extension — langue.</li>
            <li>Mentionner « boutique indépendante » sur les supports durables.</li>
          </ul></div>
          <div class="ch-dont"><h3>À éviter</h3><ul>
            <li>Personnages, Poké Ball, police ou logo Pokémon, symboles d'énergie.</li>
            <li>Cercle coupé horizontalement en deux couleurs avec un rond central.</li>
            <li>Duo jaune vif + bleu évoquant le logo de la licence.</li>
            <li>Déformer, ombrer, contourer ou recolorer le logo hors palette.</li>
            <li>Texte blanc sur l'orange (A) ; texte noir sur le violet (B).</li>
            <li>Emballage généré par IA, faux stock, compte à rebours, coût ou marge visibles.</li>
          </ul></div>
        </div>
      </section>

      <section class="ch-section" id="applications" aria-labelledby="t11">
        <h2 class="da-title" id="t11"><span class="ch-num">11</span>Applications</h2>
        <h3>Réseaux sociaux (zones photo à remplacer par des photos réelles)</h3>
        <div class="ch-apps" data-only="a">
          <figure><img src="social/a/couverture-4x5.svg" alt="Couverture 4:5, direction A" width="1080" height="1350" loading="lazy"><figcaption class="ch-cap">Couverture 4:5</figcaption></figure>
          <figure><img src="social/a/story-9x16-nouveau-stock.svg" alt="Story 9:16, direction A" width="1080" height="1920" loading="lazy"><figcaption class="ch-cap">Story 9:16</figcaption></figure>
          <figure><img src="social/a/carrousel-4x5-2.svg" alt="Carrousel slide 2, direction A" width="1080" height="1350" loading="lazy"><figcaption class="ch-cap">Carrousel 2/3</figcaption></figure>
          <figure><img src="social/a/couverture-1x1.svg" alt="Couverture 1:1, direction A" width="1080" height="1080" loading="lazy"><figcaption class="ch-cap">Couverture 1:1</figcaption></figure>
        </div>
        <div class="ch-apps" data-only="b">
          <figure><img src="social/b/couverture-4x5.svg" alt="Couverture 4:5, direction B" width="1080" height="1350" loading="lazy"><figcaption class="ch-cap">Couverture 4:5</figcaption></figure>
          <figure><img src="social/b/story-9x16-nouveau-stock.svg" alt="Story 9:16, direction B" width="1080" height="1920" loading="lazy"><figcaption class="ch-cap">Story 9:16</figcaption></figure>
          <figure><img src="social/b/carrousel-4x5-2.svg" alt="Carrousel slide 2, direction B" width="1080" height="1350" loading="lazy"><figcaption class="ch-cap">Carrousel 2/3</figcaption></figure>
          <figure><img src="social/b/couverture-1x1.svg" alt="Couverture 1:1, direction B" width="1080" height="1080" loading="lazy"><figcaption class="ch-cap">Couverture 1:1</figcaption></figure>
        </div>
        <h3>Packaging (à faire chiffrer : <a href="packaging/NOTE_CHIFFRAGE.md">NOTE_CHIFFRAGE.md</a>)</h3>
        <div class="ch-apps" data-only="a">
          <figure><img src="packaging/a/sticker-rond-50mm.svg" alt="Sticker rond A" width="200" height="200" loading="lazy"><figcaption class="ch-cap">Sticker Ø 50 mm</figcaption></figure>
          <figure><img src="packaging/a/carte-merci-a6-recto.svg" alt="Carte merci recto A" width="200" height="277" loading="lazy"><figcaption class="ch-cap">Carte A6 recto</figcaption></figure>
          <figure><img src="packaging/a/carte-merci-a6-verso.svg" alt="Carte merci verso A" width="200" height="277" loading="lazy"><figcaption class="ch-cap">Carte A6 verso</figcaption></figure>
          <figure><img src="packaging/a/repere-commande-70x37mm.svg" alt="Repère commande A" width="200" height="106" loading="lazy"><figcaption class="ch-cap">Repère commande 70 × 37 mm</figcaption></figure>
        </div>
        <div class="ch-apps" data-only="b">
          <figure><img src="packaging/b/sticker-rond-50mm.svg" alt="Sticker rond B" width="200" height="200" loading="lazy"><figcaption class="ch-cap">Sticker Ø 50 mm</figcaption></figure>
          <figure><img src="packaging/b/carte-merci-a6-recto.svg" alt="Carte merci recto B" width="200" height="277" loading="lazy"><figcaption class="ch-cap">Carte A6 recto</figcaption></figure>
          <figure><img src="packaging/b/carte-merci-a6-verso.svg" alt="Carte merci verso B" width="200" height="277" loading="lazy"><figcaption class="ch-cap">Carte A6 verso</figcaption></figure>
          <figure><img src="packaging/b/repere-commande-70x37mm.svg" alt="Repère commande B" width="200" height="106" loading="lazy"><figcaption class="ch-cap">Repère commande 70 × 37 mm</figcaption></figure>
        </div>
        <h3>Site et emails</h3>
        <p><a href="components/page-produit.html">Page produit</a> (mobile d'abord) · <a href="components/email-transactionnel-a.html">email de confirmation A</a> · <a href="components/email-transactionnel-b.html">email de confirmation B</a>.</p>
      </section>

      <section class="ch-section" id="validation" aria-labelledby="t12">
        <h2 class="da-title" id="t12"><span class="ch-num">12</span>Validation humaine requise</h2>
        <p>Une seule séance de validation par la responsable (≈ 30 min), puis les agents de contenu n'utilisent plus que les composants approuvés (BP §8).</p>
        <ul class="ch-check">
          <li>Choisir le nom (recommandé : « Quai des Cartes ») <em>après</em> vérification humaine du domaine .ch, des comptes sociaux et des registres de marques (Swissreg/IPI, EUIPO).</li>
          <li>Choisir la direction A ou B (une seule) ; les fichiers de l'autre direction sont archivés.</li>
          <li>Valider le logo, la couleur d'accent et les polices.</li>
          <li>Faire valider par le juriste : mention « boutique indépendante » et mention de marque en pied de page.</li>
          <li>Valider les textes fixes du packaging (délai de signalement, adresse, raison sociale) avec les CGV.</li>
          <li>Demander les devis d'impression réels avant toute commande (NOTE_CHIFFRAGE.md).</li>
        </ul>
      </section>
""" + FOOT.replace("../CHARTE.html", "#intro").replace("retour à la charte", "haut de page") + """    </main>
  </div>
  <script>
    (function () {
      "use strict";
      function lin(c) { c = c / 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
      function lum(hex) {
        var h = hex.replace("#", "");
        if (h.length !== 6) { return null; }
        var r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
      }
      function ratio(a, b) {
        var la = lum(a), lb = lum(b);
        if (la === null || lb === null) { return null; }
        var hi = Math.max(la, lb), lo = Math.min(la, lb);
        return Math.floor(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
      }
      function token(name) { return getComputedStyle(document.documentElement).getPropertyValue("--da-color-" + name).trim().toUpperCase(); }
      function render() {
        var bg = token("bg"), ink = token("ink");
        document.querySelectorAll(".ch-swatch").forEach(function (el) {
          var hex = token(el.getAttribute("data-token"));
          el.querySelector(".ch-swatch__hex").textContent = hex + " · --da-color-" + el.getAttribute("data-token");
          var rb = ratio(hex, bg), ri = ratio(hex, ink);
          el.querySelector(".ch-swatch__ratio").textContent = "vs fond " + (rb ? rb.toFixed(2) : "?") + ":1 · vs encre " + (ri ? ri.toFixed(2) : "?") + ":1";
        });
        document.querySelectorAll("#ch-pairs tbody tr").forEach(function (tr) {
          var r = ratio(token(tr.getAttribute("data-fg")), token(tr.getAttribute("data-bg")));
          var min = parseFloat(tr.getAttribute("data-min"));
          tr.querySelector(".ch-r").textContent = r === null ? "?" : r.toFixed(2) + ":1 " + (r >= min ? "✓" : "✗ insuffisant");
        });
      }
      document.addEventListener("da:change", render);
      if (window.matchMedia) { window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render); }
      if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", render); } else { render(); }
    })();
  </script>
</body>
</html>
"""


def pages() -> dict[str, str]:
    """{chemin relatif à docs/05-da: HTML final (icônes développées)}."""
    return {
        "components/badges.html": icons(_BADGES),
        "components/carte-produit.html": icons(_CARTE),
        "components/banniere.html": icons(_BANNIERES),
        "components/page-produit.html": icons(_PRODUIT),
        "CHARTE.html": icons(_CHARTE),
    }
