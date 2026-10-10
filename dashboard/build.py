"""Génère le tableau de bord interne statique ``dashboard/out/index.html``.

**INTERNE — contient coûts et marges, ne jamais publier** (BP §7). Le fichier produit ne doit
jamais être copié sur le site public, un hébergement partagé, un prompt marketing ou un canal
public : il se lit en local (navigateur) ou derrière l'accès protégé de l'API.

Deux sources :

* ``python dashboard/build.py`` : données de démonstration **FICTIVES** (``pokeshop.dashboard.demo_inputs``),
  rendu déterministe (exemple committé dans ``dashboard/out/index.html``) ;
* ``python dashboard/build.py --api http://127.0.0.1:8000 --out ~/pokeshop/tableau.html`` : lit
  ``GET /dashboard/daily|weekly|monthly`` avec le jeton de la variable d'environnement ``POKESHOP_API_TOKEN``
  (jamais en argument de ligne de commande : il resterait dans l'historique du terminal). Les données
  réelles (coûts, marges, prix B2B) ne s'écrivent **jamais dans le dépôt** : sans ``--out``, la page va
  dans ``~/.pokeshop/tableau_de_bord.html`` ; un ``--out`` situé dans le dépôt est refusé (code 2), y
  compris l'exemple FICTIF suivi par git ``dashboard/out/index.html``.

Options : ``--day AAAA-MM-JJ``, ``--week AAAA-MM-JJ`` (un jour de la semaine), ``--month AAAA-MM``,
``--out CHEMIN`` ; ``--check`` vérifie que l'exemple committé correspond au rendu de démonstration.

HTML/CSS/JS autonomes : aucune ressource externe (politique de sécurité ``default-src 'none'``),
lisible sans JavaScript (les trois vues s'empilent), mobile d'abord, clair/sombre (préférence du
système + bouton), ``noindex``.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import sys
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from pokeshop.audit import to_jsonable  # noqa: E402
from pokeshop.dashboard import (  # noqa: E402
    DEMO_AS_OF,
    INTERNAL_BANNER,
    build_reports,
    demo_inputs,
    fmt_chf,
)

DEFAULT_OUT = ROOT / "dashboard" / "out" / "index.html"
"""Exemple FICTIF suivi par git (démonstration seulement)."""
API_DEFAULT_OUT = Path.home() / ".pokeshop" / "tableau_de_bord.html"
"""Sortie par défaut du tableau de bord réel (``--api``) : hors du dépôt."""
TOKEN_ENV = "POKESHOP_API_TOKEN"
DEMO_MONTH = "2026-11"
KINDS = (("daily", "Jour"), ("weekly", "Semaine"), ("monthly", "Mois"))

STATUS_META: dict[str, tuple[str, str, str]] = {
    "OK": ("ok", "✓", "OK"),
    "INFO": ("info", "i", "Info"),
    "ALERTE": ("alert", "!", "Alerte"),
    "CRITIQUE": ("crit", "‼", "Critique"),
    "INDISPONIBLE": ("na", "–", "Indisponible"),
}
TREND_FR = {
    "HAUSSE": "en hausse",
    "BAISSE": "en baisse",
    "STABLE": "stable",
    "INCONNUE": "inconnue (moins de 2 semaines closes)",
}

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#6b6a65;
--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--pos:#2a78d6;--neg:#e34948;--good:#0ca30c;
--warn:#fab219;--crit:#d03b3b;--info:#2a78d6;--na:#898781;--banner-bg:#0b0b0b;--banner-ink:#ffffff;
--chip-bg:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;
--surface:#1a1a19;--ink:#ffffff;--ink2:#c3c2b7;--muted:#a3a29b;--grid:#2c2c2a;--axis:#383835;
--ring:rgba(255,255,255,.10);--pos:#3987e5;--neg:#e66767;--info:#3987e5;--banner-bg:#fab219;
--banner-ink:#0b0b0b;--chip-bg:#262624}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;--ink2:#c3c2b7;
--muted:#a3a29b;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--pos:#3987e5;--neg:#e66767;
--info:#3987e5;--banner-bg:#fab219;--banner-ink:#0b0b0b;--chip-bg:#262624}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.banner{position:sticky;top:0;z-index:5;background:var(--banner-bg);color:var(--banner-ink);padding:8px 16px;
font-weight:700;letter-spacing:.02em;text-align:center}
.banner small{display:block;font-weight:500;letter-spacing:0}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
header.top{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;justify-content:space-between}
h1{font-size:1.35rem;margin:.2rem 0}
h2{font-size:1.1rem;margin:0 0 .6rem}
h3{font-size:1rem;margin:0 0 .5rem}
.meta{color:var(--ink2);font-size:.9rem}
.fictif{display:inline-block;margin-left:.4rem;padding:2px 8px;border-radius:999px;background:var(--chip-bg);
color:var(--ink);font-weight:700;font-size:.8rem;border:1px solid var(--ring)}
button.theme{background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;
padding:6px 12px;font:inherit;cursor:pointer}
nav.tabs{display:flex;gap:6px;margin:12px 0;flex-wrap:wrap}
nav.tabs button{background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:999px;
padding:6px 16px;font:inherit;cursor:pointer}
nav.tabs button[aria-selected="true"]{background:var(--ink);color:var(--page)}
.js section.view{display:none}.js section.view.active{display:block}
section.view{margin-bottom:28px}
.period{color:var(--ink2);margin:-.3rem 0 .8rem}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:16px;margin:0 0 14px}
.northstar .hero{font-size:clamp(2.6rem,7vw,3.6rem);font-weight:650;line-height:1.05;margin:.2rem 0}
.northstar .label{color:var(--ink2);font-size:.95rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}
.stat{border-top:1px solid var(--grid);padding-top:8px}
.stat .v{font-size:1.15rem;font-weight:600}
.stat .l{color:var(--ink2);font-size:.85rem}
.status{display:inline-flex;align-items:center;gap:6px;font-weight:600;font-size:.85rem;color:var(--ink)}
.status .ico{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;color:#fff;
font-size:.75rem;font-weight:800}
.st-ok .ico{background:var(--good)}.st-info .ico{background:var(--info)}.st-alert .ico{background:var(--warn);color:#0b0b0b}
.st-crit .ico{background:var(--crit)}.st-na .ico{background:var(--na)}
.card.st-crit{border-left:6px solid var(--crit)}.card.st-alert{border-left:6px solid var(--warn)}
.card.st-ok{border-left:6px solid var(--good)}
.headline{margin:.5rem 0 0;font-weight:500}
.levels{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:8px;margin:12px 0}
.level{border:1px solid var(--ring);border-radius:10px;padding:8px}
.level b{display:block;font-size:1.2rem}
.level.on{border-color:var(--warn);box-shadow:inset 0 0 0 1px var(--warn)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px;margin-bottom:14px}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:12px 14px}
.kpi .v{font-size:1.6rem;font-weight:620;margin:.15rem 0}
.kpi .l{color:var(--ink2);font-size:.9rem}
.kpi .d{font-size:.85rem;color:var(--ink2);margin-top:.35rem}
.kpi .t{font-size:.78rem;color:var(--muted);margin-top:.25rem}
ul.decisions{margin:0;padding-left:1.1rem}ul.decisions li{margin:.25rem 0}
.due{color:var(--muted);font-size:.85rem}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.88rem}
.tablewrap table{min-width:560px}
.tablewrap table.wide{min-width:860px}
td.long{min-width:16rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink2);font-weight:600;white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.note{color:var(--muted);font-size:.82rem;margin:.4rem 0 0}
.empty{color:var(--ink2);font-style:italic}
details summary{cursor:pointer;color:var(--ink2);margin-top:8px}
.chart{position:relative;margin-top:12px}
.chart svg{display:block;width:100%;height:auto;max-height:260px;overflow:visible}
.chart .bar{cursor:default}
.chart .bar:hover,.chart .bar:focus{opacity:.8;outline:none}
.tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--page);padding:6px 8px;border-radius:6px;
font-size:.8rem;white-space:nowrap;transform:translate(-50%,-110%);display:none}
.missing{color:var(--ink2);font-size:.88rem}
footer{color:var(--muted);font-size:.8rem;margin:24px 0}
@media print{.banner{position:static}nav.tabs,button.theme{display:none}.js section.view{display:block}}
@media (forced-colors:active){.status .ico{forced-color-adjust:none}}
"""

JS = """
(function(){
  var root=document.documentElement;root.classList.add('js');
  try{var saved=localStorage.getItem('pokeshop-dashboard-theme');if(saved){root.setAttribute('data-theme',saved);}}catch(e){}
  var btn=document.getElementById('theme');
  if(btn){btn.addEventListener('click',function(){
    var dark=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&window.matchMedia&&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
    var next=dark?'light':'dark';root.setAttribute('data-theme',next);
    try{localStorage.setItem('pokeshop-dashboard-theme',next);}catch(e){}
  });}
  var tabs=document.querySelectorAll('nav.tabs button');
  function show(id){
    document.querySelectorAll('section.view').forEach(function(s){s.classList.toggle('active',s.id===id);});
    tabs.forEach(function(b){b.setAttribute('aria-selected',b.getAttribute('data-view')===id?'true':'false');});
    try{localStorage.setItem('pokeshop-dashboard-view',id);}catch(e){}
  }
  tabs.forEach(function(b){b.addEventListener('click',function(){show(b.getAttribute('data-view'));});});
  var first='view-daily';try{first=localStorage.getItem('pokeshop-dashboard-view')||first;}catch(e){}
  if(!document.getElementById(first)){first='view-daily';}
  show(first);
  document.querySelectorAll('.chart').forEach(function(chart){
    var tip=chart.querySelector('.tip');
    chart.querySelectorAll('.bar').forEach(function(bar){
      function on(){var r=chart.getBoundingClientRect(),b=bar.getBoundingClientRect();
        tip.textContent=bar.getAttribute('data-tip');tip.style.left=(b.left-r.left+b.width/2)+'px';
        tip.style.top=(b.top-r.top)+'px';tip.style.display='block';}
      function off(){tip.style.display='none';}
      bar.addEventListener('mouseenter',on);bar.addEventListener('focus',on);
      bar.addEventListener('mouseleave',off);bar.addEventListener('blur',off);
    });
  });
})();
"""


def esc(value: Any) -> str:
    """Échappement HTML de toute valeur affichée (aucune donnée n'est injectée brute)."""
    return html.escape("" if value is None else str(value), quote=True)


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def status_badge(status: str, label: str | None = None) -> str:
    """Pastille de statut : icône + libellé (jamais la couleur seule)."""
    css, icon, text = STATUS_META.get(status, STATUS_META["INDISPONIBLE"])
    return (
        f'<span class="status st-{css}"><span class="ico" aria-hidden="true">{esc(icon)}</span>'
        f"{esc(label or text)}</span>"
    )


def _num_class(column: str) -> str:
    numeric = (
        "Montant",
        "Coût",
        "Stock",
        "Ventes",
        "Total",
        "Dépense",
        "CAC",
        "Contribution",
        "Écart",
        "Estimé",
        "Facturé",
        "Reste",
        "Engagé",
        "Quantité",
        "Offres",
        "Périmées",
        "Commandes",
        "Rotation",
        "Part",
        "CA",
    )
    return ' class="num"' if column.startswith(numeric) else ""


def render_table(table: Mapping[str, Any]) -> str:
    """Tableau interne (cellules déjà formatées par le moteur)."""
    columns: Sequence[str] = table["columns"]
    rows: Sequence[Sequence[str]] = table["rows"]
    parts = [f'<div class="card"><h3>{esc(table["title"])}</h3>']
    if not rows:
        parts.append(f'<p class="empty">{esc(table["empty_text"])}</p>')
    else:
        head = "".join(f'<th{_num_class(c)} scope="col">{esc(c)}</th>' for c in columns)
        body = "".join(
            "<tr>" + "".join(f"<td{_num_class(c)}>{esc(v)}</td>" for c, v in zip(columns, row, strict=True)) + "</tr>"
            for row in rows
        )
        wide = ' class="wide"' if len(columns) >= 6 else ""
        parts.append(
            f'<div class="tablewrap"><table{wide}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
        )
    if table.get("note"):
        parts.append(f'<p class="note">{esc(table["note"])}</p>')
    parts.append("</div>")
    return "".join(parts)


def render_chart(weeks: Sequence[Mapping[str, Any]], chart_id: str) -> str:
    """Colonnes de contribution nette hebdomadaire (divergent bleu/rouge autour de zéro) + vue tableau."""
    if not weeks:
        return ""
    values = [Decimal(str(w["net"])) for w in weeks]
    top = max(max(values), Decimal(0))
    bottom = min(min(values), Decimal(0))
    span = (top - bottom) or Decimal(1)
    width = max(360, min(640, 90 * len(weeks)))
    height, pad_x, pad_top, pad_bottom = 200, 40, 24, 44
    plot_h = height - pad_top - pad_bottom
    step = (width - 2 * pad_x) / len(weeks)
    bar_w = min(24.0, step * 0.6)

    def y(v: Decimal) -> float:
        return pad_top + float((top - v) / span) * plot_h

    zero_y = y(Decimal(0))
    parts = [
        f'<div class="chart" id="{esc(chart_id)}"><div class="tip" role="status"></div>',
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Contribution nette par semaine (CHF)">',
        f'<line x1="{pad_x}" x2="{width - pad_x}" y1="{zero_y:.1f}" y2="{zero_y:.1f}" stroke="var(--axis)" stroke-width="1"/>',
        f'<text x="{pad_x - 6}" y="{zero_y + 4:.1f}" text-anchor="end" font-size="11" fill="var(--muted)">0</text>',
    ]
    last_closed = max((i for i, w in enumerate(weeks) if w.get("complete")), default=None)
    for i, (w, v) in enumerate(zip(weeks, values, strict=True)):
        cx = pad_x + step * i + step / 2
        x0 = cx - bar_w / 2
        y_v = y(v)
        h = abs(y_v - zero_y)
        r = min(4.0, h)
        color = "var(--pos)" if v >= 0 else "var(--neg)"
        opacity = "1" if w.get("complete") else "0.45"
        if h < 0.5:
            path = f"M{x0:.1f},{zero_y - 0.5:.1f}h{bar_w:.1f}v1h{-bar_w:.1f}z"
        elif v >= 0:
            path = (
                f"M{x0:.1f},{zero_y:.1f}V{y_v + r:.1f}Q{x0:.1f},{y_v:.1f} {x0 + r:.1f},{y_v:.1f}"
                f"H{x0 + bar_w - r:.1f}Q{x0 + bar_w:.1f},{y_v:.1f} {x0 + bar_w:.1f},{y_v + r:.1f}V{zero_y:.1f}Z"
            )
        else:
            path = (
                f"M{x0:.1f},{zero_y:.1f}V{y_v - r:.1f}Q{x0:.1f},{y_v:.1f} {x0 + r:.1f},{y_v:.1f}"
                f"H{x0 + bar_w - r:.1f}Q{x0 + bar_w:.1f},{y_v:.1f} {x0 + bar_w:.1f},{y_v - r:.1f}V{zero_y:.1f}Z"
            )
        state = "close" if w.get("complete") else "en cours"
        tip = f"{w['iso_week']} ({state}) : {fmt_chf(v)} ; cumul {fmt_chf(_dec(w['cumulative']))}"
        parts.append(
            f'<path class="bar" tabindex="0" d="{path}" fill="{color}" fill-opacity="{opacity}" '
            f'data-tip="{esc(tip)}"><title>{esc(tip)}</title></path>'
        )
        label = w["iso_week"].split("-")[-1]
        parts.append(
            f'<text x="{cx:.1f}" y="{height - 8}" text-anchor="middle" font-size="11" fill="var(--muted)">{esc(label)}</text>'
        )
        if i == last_closed:
            ty = y_v - 6 if v >= 0 else y_v + 14
            parts.append(
                f'<text x="{cx:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="11" fill="var(--ink)">'
                f"{esc(fmt_chf(v))}</text>"
            )
    parts.append("</svg>")
    rows = "".join(
        f"<tr><td>{esc(w['iso_week'])}</td><td>{'close' if w.get('complete') else 'en cours'}</td>"
        f'<td class="num">{esc(w["orders"])}</td><td class="num">{esc(fmt_chf(_dec(w["net"])))}</td>'
        f'<td class="num">{esc(fmt_chf(_dec(w["cumulative"])))}</td></tr>'
        for w in weeks
    )
    parts.append(
        '<details><summary>Voir les données (tableau)</summary><div class="tablewrap"><table><thead><tr>'
        '<th scope="col">Semaine</th><th scope="col">État</th><th class="num" scope="col">Commandes</th>'
        '<th class="num" scope="col">Contribution nette</th><th class="num" scope="col">Cumul</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></details></div>"
    )
    return "".join(parts)


def render_northstar(block: Mapping[str, Any], kind: str) -> str:
    """Bloc 1 — étoile polaire (toujours en tête)."""
    parts = [f'<div class="card northstar st-{STATUS_META.get(block["status"], STATUS_META["INDISPONIBLE"])[0]}">']
    parts.append(f"<h2>Étoile polaire — contribution nette cumulée {status_badge(block['status'])}</h2>")
    if not block["available"]:
        parts.append(f'<p class="hero">{esc(fmt_chf(_dec(block["cumulative"])))}</p>')
        parts.append(f'<p class="missing">{esc(block["reason"])}</p></div>')
        return "".join(parts)
    parts.append(
        '<p class="label">Ventes nettes HT − coût historique − paiement − logistique − SAV − acquisition − '
        "charges fixes, depuis le lancement</p>"
    )
    parts.append(f'<p class="hero">{esc(fmt_chf(_dec(block["cumulative"])))}</p>')
    stats: list[tuple[str, str]] = []
    if block.get("last_closed_week"):
        stats.append((f"Dernière semaine close ({block['last_closed_week']})", fmt_chf(_dec(block["last_closed_net"]))))
        delta = _dec(block["last_closed_delta"])
        stats.append(("Delta vs semaine précédente", ("+" if delta is not None and delta > 0 else "") + fmt_chf(delta)))
    if block.get("current_week"):
        stats.append((f"Semaine en cours ({block['current_week']})", fmt_chf(_dec(block["current_week_net"]))))
    if block.get("average_4_weeks") is not None:
        stats.append(
            (
                f"Moyenne des {block['average_weeks_count']} dernière(s) semaine(s) close(s)",
                fmt_chf(_dec(block["average_4_weeks"])),
            )
        )
    stats.append(("Tendance", TREND_FR.get(block["trend"], block["trend"])))
    stats.append((f"{block['period_label']} : contribution nette", fmt_chf(_dec(block["period_net"]))))
    if block["period_after_acquisition"] != block["period_net"]:
        stats.append(
            (f"{block['period_label']} : avant charges fixes", fmt_chf(_dec(block["period_after_acquisition"])))
        )
    parts.append('<div class="stats">')
    for label, value in stats:
        parts.append(f'<div class="stat"><div class="v">{esc(value)}</div><div class="l">{esc(label)}</div></div>')
    parts.append("</div>")
    parts.append(f'<p class="headline">{esc(block["headline"])}</p>')
    parts.append(render_chart(block.get("weeks", ()), f"chart-{kind}"))
    parts.append("</div>")
    return "".join(parts)


def render_stoploss(block: Mapping[str, Any]) -> str:
    """Bloc 2 — état des six stop-loss (immédiatement après l'étoile polaire)."""
    css = STATUS_META.get(block["status"], STATUS_META["INDISPONIBLE"])[0]
    level = block.get("autonomy_level")
    level_txt = f" · autonomie niveau {level}" if level is not None else ""
    parts = [
        f'<div class="card stoploss st-{css}">',
        f'<h2>Stop-loss {status_badge(block["status"])}<span class="meta">{esc(level_txt)}</span></h2>',
        f'<p class="headline">{esc(block["headline"])}</p>',
        '<div class="levels">',
    ]
    for lv in block.get("levels", ()):
        on = " on" if lv["count"] else ""
        parts.append(f'<div class="level{on}"><b>{esc(lv["count"])}</b>{esc(lv["label"])}</div>')
    parts.append("</div>")
    triggers = block.get("triggers", ())
    if triggers:
        rows = "".join(
            f'<tr><td>{esc(t["level_label"])}</td><td>{esc(t["scope"])}</td><td class="num">{esc(t["value_display"])}</td>'
            f'<td class="num">{esc(t["threshold_display"])}</td><td>{esc(t["action_label"])}</td><td class="long">{esc(t["reason"])}</td></tr>'
            for t in triggers
        )
        parts.append(
            '<div class="tablewrap"><table class="wide"><thead><tr><th scope="col">Niveau</th><th scope="col">Périmètre</th>'
            '<th class="num" scope="col">Mesure</th><th class="num" scope="col">Seuil</th><th scope="col">Action</th>'
            f'<th scope="col">Cause</th></tr></thead><tbody>{rows}</tbody></table></div>'
        )
    if block.get("rearm_instructions"):
        items = "".join(f"<li>{esc(i)}</li>" for i in block["rearm_instructions"])
        parts.append(f"<h3>Comment réarmer (propriétaire uniquement)</h3><ol>{items}</ol>")
    parts.append("</div>")
    return "".join(parts)


def render_kpi(kpi: Mapping[str, Any]) -> str:
    """Tuile d'indicateur : libellé, valeur, statut (icône + libellé), détail, seuil."""
    parts = [
        f'<div class="kpi"><div class="l">{esc(kpi["label"])}</div>',
        f'<div class="v">{esc(kpi["display"])}</div>',
        status_badge(kpi["status"]),
    ]
    if kpi.get("detail"):
        parts.append(f'<div class="d">{esc(kpi["detail"])}</div>')
    if kpi.get("threshold"):
        parts.append(f'<div class="t">Seuil : {esc(kpi["threshold"])}</div>')
    parts.append("</div>")
    return "".join(parts)


def render_view(kind: str, report: Mapping[str, Any]) -> str:
    """Une vue (jour, semaine ou mois)."""
    complete = "" if report["complete"] else " (en cours)"
    parts = [
        f'<section class="view" id="view-{esc(kind)}" aria-labelledby="title-{esc(kind)}">',
        f'<h2 id="title-{esc(kind)}">{esc(report["title"])} {status_badge(report_status(report))}</h2>',
        f'<p class="period">{esc(report["period_label"])}{esc(complete)}</p>',
        render_northstar(report["north_star"], kind),
        render_stoploss(report["stoploss"]),
    ]
    decisions = report.get("decisions", ())
    parts.append('<div class="card"><h3>Décisions attendues</h3>')
    if decisions:
        items = []
        for d in decisions:
            due = f' <span class="due">(avant le {esc(_fmt_due(d["due"]))})</span>' if d.get("due") else ""
            items.append(f"<li>{esc(d['label'])}{due}</li>")
        parts.append(f'<ul class="decisions">{"".join(items)}</ul>')
    else:
        parts.append('<p class="empty">Aucune décision attendue.</p>')
    parts.append("</div>")
    parts.append('<div class="kpis">' + "".join(render_kpi(k) for k in report["kpis"]) + "</div>")
    parts.extend(render_table(t) for t in report.get("tables", ()))
    if report.get("unavailable"):
        missing = "".join(f"<li>{esc(u)}</li>" for u in report["unavailable"])
        parts.append(f'<div class="card"><h3>Sources non branchées</h3><ul class="missing">{missing}</ul></div>')
    parts.append("</section>")
    return "".join(parts)


def _fmt_due(text: str) -> str:
    # « 2026-11-17T07:30:00+01:00 » -> « 17.11.2026 07:30 »
    day, _, rest = text.partition("T")
    y, m, d = day.split("-")
    return f"{d}.{m}.{y} {rest[:5]}".strip()


def report_status(report: Mapping[str, Any]) -> str:
    """Pire statut d'une vue (même règle que ``DashboardReport.status``)."""
    rank = {"OK": 0, "INFO": 1, "INDISPONIBLE": 2, "ALERTE": 3, "CRITIQUE": 4}
    statuses: list[str] = [
        str(report["north_star"]["status"]),
        str(report["stoploss"]["status"]),
        *(str(k["status"]) for k in report["kpis"]),
    ]
    return max(statuses, key=lambda s: rank.get(s, 0))


def render_html(reports: Mapping[str, Mapping[str, Any]], *, source_label: str) -> str:
    """Page complète : bandeau INTERNE, onglets Jour / Semaine / Mois, étoile polaire et stop-loss en tête."""
    daily = reports["daily"]
    fictif = any(r.get("fictif") for r in reports.values())
    badge = '<span class="fictif">DONNÉES FICTIVES — démonstration</span>' if fictif else ""
    nav = "".join(
        f'<button type="button" data-view="view-{k}" aria-selected="false">{esc(label)}</button>' for k, label in KINDS
    )
    views = "".join(render_view(k, reports[k]) for k, _ in KINDS)
    return f"""<!doctype html>
<html lang="fr-CH">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:">
<title>Tableau de bord interne — {{{{NOM_BOUTIQUE}}}}</title>
<style>{CSS}</style>
</head>
<body>
<div class="banner" role="note">{esc(INTERNAL_BANNER)}<small>Coûts, marges et données internes : lecture en local ou derrière l'accès protégé de l'API uniquement.</small></div>
<div class="wrap">
<header class="top">
<div><h1>Tableau de bord interne — {{{{NOM_BOUTIQUE}}}}{badge}</h1>
<p class="meta">Photo du {esc(_fmt_due(daily["as_of"]))} · générée le {esc(_fmt_due(daily["generated_at"]))} · source : {esc(source_label)}</p></div>
<button class="theme" id="theme" type="button">Clair / sombre</button>
</header>
<nav class="tabs" aria-label="Période">{nav}</nav>
{views}
<footer>Lecture seule. Étoile polaire : pokeshop.northstar ; stop-loss : pokeshop.stoploss (évalué par le moteur) ;
KPI : pokeshop.dashboard (BP §12, ROUTINES_PILOTAGE.md §6). Un indicateur « Indisponible » signale une source non branchée,
jamais un zéro inventé. {esc(INTERNAL_BANNER)}.</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""


def demo_payloads() -> dict[str, dict[str, Any]]:
    """Trois vues de démonstration FICTIVES, déterministes (générées « à » ``DEMO_AS_OF``)."""
    bundle = build_reports(demo_inputs(), month=DEMO_MONTH, now=DEMO_AS_OF)
    data: dict[str, dict[str, Any]] = to_jsonable(bundle)
    return data


def fetch_payloads(
    api_url: str, token: str, *, day: str | None = None, week: str | None = None, month: str | None = None
) -> dict[str, dict[str, Any]]:
    """Lit les trois vues sur l'API (jeton d'API en en-tête ; JSON sans nombre flottant)."""
    import httpx

    def reject_float(text: str) -> Any:
        raise ValueError(f"nombre flottant inattendu dans la réponse : {text}")

    out: dict[str, dict[str, Any]] = {}
    params = {"daily": {"day": day}, "weekly": {"week": week}, "monthly": {"month": month}}
    with httpx.Client(base_url=api_url.rstrip("/"), timeout=30) as client:
        for kind, _ in KINDS:
            query = {k: v for k, v in params[kind].items() if v}
            resp = client.get(f"/dashboard/{kind}", params=query, headers={"X-Pokeshop-Token": token})
            if resp.status_code != 200:
                raise SystemExit(f"/dashboard/{kind} : HTTP {resp.status_code} — {resp.text[:300]}")
            out[kind] = json.loads(resp.content, parse_float=reject_float)["report"]
    return out


def build(
    out: Path = DEFAULT_OUT, payloads: Mapping[str, Mapping[str, Any]] | None = None, *, source_label: str = ""
) -> Path:
    """Écrit la page (démonstration FICTIVE par défaut) et renvoie son chemin."""
    data = payloads if payloads is not None else demo_payloads()
    label = source_label or "démonstration FICTIVE (pokeshop.dashboard.demo_inputs)"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(data, source_label=label), encoding="utf-8")
    return out


def _inside_repo(path: Path) -> bool:
    """Vrai si ``path`` (liens résolus) est dans le dépôt : les données réelles n'y vont jamais."""
    return path.expanduser().resolve().is_relative_to(ROOT.resolve())


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(description="Tableau de bord interne (INTERNE — ne jamais publier).")
    parser.add_argument("--api", help="URL de l'API du moteur (ex. http://127.0.0.1:8000) ; défaut : démonstration")
    parser.add_argument("--day", help="jour AAAA-MM-JJ (défaut : la veille)")
    parser.add_argument("--week", help="un jour de la semaine voulue AAAA-MM-JJ (défaut : dernière semaine close)")
    parser.add_argument("--month", help="mois AAAA-MM (défaut : mois précédent)")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="fichier HTML produit (défaut : exemple FICTIF du dépôt ; avec --api : ~/.pokeshop/tableau_de_bord.html, "
        "jamais dans le dépôt)",
    )
    parser.add_argument("--check", action="store_true", help="vérifie que l'exemple committé est à jour")
    args = parser.parse_args(argv)
    if args.api and args.out is not None and _inside_repo(args.out):
        print(
            f"Sortie réelle interdite dans le dépôt ({args.out}) : coûts et marges réels. "
            "Utiliser --out hors du dépôt (ex. ~/pokeshop/tableau.html).",
            file=sys.stderr,
        )
        return 2
    if args.out is None:
        args.out = API_DEFAULT_OUT if args.api else DEFAULT_OUT
    if args.check:
        expected = render_html(demo_payloads(), source_label="démonstration FICTIVE (pokeshop.dashboard.demo_inputs)")
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current != expected:
            diff = difflib.unified_diff(current.splitlines(), expected.splitlines(), "committé", "attendu", lineterm="")
            print("\n".join(list(diff)[:40]))
            print(f"{args.out} n'est pas à jour : relancer python dashboard/build.py")
            return 1
        print(f"{args.out} à jour.")
        return 0
    if args.api:
        token = os.environ.get(TOKEN_ENV, "")
        if not token:
            print(f"Jeton absent : définir {TOKEN_ENV} (jamais en argument).", file=sys.stderr)
            return 2
        payloads = fetch_payloads(args.api, token, day=args.day, week=args.week, month=args.month)
        path = build(args.out, payloads, source_label=f"API {args.api}")
        path.chmod(0o600)  # coûts et marges réels : lisible par la seule personne qui l'a produit
    else:
        if args.day or args.week or args.month:
            print("--day/--week/--month s'appliquent à --api ; la démonstration est figée.", file=sys.stderr)
        path = build(args.out)
    print(f"Écrit : {path} — {INTERNAL_BANNER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
