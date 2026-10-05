# 06-contenu — ton, sujets, calendrier, vidéos, emails, publicité, SEO

> Propriétaire (build) : agent « site-contenu ». Exploitation : agents 08 SEO et rédaction, 09 Communication, 10 Acquisition ; tournage : propriétaire (A06).
> Sources : BP §8 (contenus de marque, ton), §9 (communication et acquisition sur 90 jours, rythme, automatisations, publicité et partenariats), §7 (fiche produit, consentements) ; DA `docs/05-da/` ; textes légaux `docs/04-legal/` ; plan `docs/00-pilotage/PLAN_90_JOURS.md` ; stop-loss `docs/00-pilotage/STOP_LOSS.md`.
> Nom de travail : « Quai des Cartes » (**provisoire, non validé**) ; dans les modèles réutilisables, le nom est le champ `{{NOM_BOUTIQUE}}`.

## Contenu

| Fichier | Rôle | BL |
|---|---|---|
| `TON_EDITORIAL.md` | Ton (précis, accessible, calme, honnête), mots à éviter, exemples avant/après, gabarits de phrases | BL-100 |
| `15_SUJETS.md` | 15 sujets éducatifs (8 du BP + 7) : angle, hook, plan, format, visuels réels, faits à sourcer, CTA | BL-100 |
| `CALENDRIER_90J.csv` | Calendrier importable dans Notion : 3 publications par semaine dès l'ouverture (1 guide, 1 nouveauté réellement accessible, 1 preuve de service), email hebdomadaire, jalons de production et de publicité | BL-101, BL-119 |
| `SCRIPTS_VIDEO.md` | 8 scripts de 20 à 45 s, plan par plan, à tourner en session groupée | A06 |
| `EMAILS/` | 14 emails (HTML + texte) générés depuis `EMAILS/source/emails.yaml`, aperçu FICTIF, règles du workflow | BL-102, BL-118, BL-135, BL-144 |
| `PUBLICITE_TEST.md` | Test publicitaire : 3 créations, offre claire, 500 CHF, plafond quotidien, règles d'arrêt, mesure sur commandes payées nettes | BL-130, BL-133 |
| `BRIEF_CREATEURS.md` | Collaboration avec un créateur TCG suisse : critères, preuves, coût dans le CAC, contrat minimal | BL-134 |
| `SEO.md` | Pages d'extension, mots-clés (sans volume), modèles de métadonnées, règles techniques | BL-143 |
| `outils/` | `generer_calendrier.py`, `generer_emails.py`, `verifier_contenu.py`, tests | — |

## Importer le calendrier dans Notion

1. Notion → Importer → CSV → choisir `CALENDRIER_90J.csv` (UTF-8, séparateur virgule, première colonne « Nom » = titre).
2. Passer la propriété « Date » en type **Date** (format ISO AAAA-MM-JJ reconnu), « Type », « Pilier », « Canal », « Statut » et « Responsable » en **Sélection**.
3. Créer une vue Calendrier sur « Date » et une vue Tableau groupée par « Semaine ».
4. Si J1 change : `python docs/06-contenu/outils/generer_calendrier.py --j1 AAAA-MM-JJ`, puis réimporter.

## Commandes

```bash
cd /home/user/1
python docs/06-contenu/outils/generer_calendrier.py            # régénère le calendrier (J1 = 5.10.2026 par défaut)
python docs/06-contenu/outils/generer_emails.py                # régénère EMAILS/html, texte, apercu.html et le tableau du README
python docs/06-contenu/outils/generer_emails.py --integration /tmp/emails --url-logo https://…/logo.png   # refuse tant qu'un champ n'est pas validé
python docs/06-contenu/outils/verifier_contenu.py              # contrôles (code 1 si erreur)
python -m pytest docs/06-contenu/outils -q                     # tests
```

## Règles qui s'appliquent à tout le dossier

1. **Aucun contenu « stock » avant la réception réelle** : la première « nouveauté accessible » est à J38 (ouverture douce), sous condition de stock local réel ; contrôle automatique sur le calendrier.
2. **Prix et stock** relus sur la page publique moins d'une heure avant diffusion (**hypothèse**, brief A-09) ; aucun prix en dur dans un modèle.
3. **Photos et vidéos réelles** ; jamais d'emballage, de carte ou de personnage généré.
4. **Consentement** : aucun email promotionnel sans double opt-in ou consentement au checkout ; désinscription propagée à tous les outils.
5. **Aucune donnée interne** (coût, marge, fournisseur, allocation chiffrée) dans un texte, un visuel ou un prompt.
6. **Stop-loss** : aucune promotion d'une référence sous stop-loss produit ; publicité coupée par le stop-loss pub ; rien pendant un gel global.

## Validation humaine requise

- [ ] Valider le ton (`TON_EDITORIAL.md`) et les 15 sujets (BL-100).
- [ ] Valider le calendrier (BL-101) ; ensuite, seules les exceptions vous remontent.
- [ ] Valider les textes des emails (`EMAILS/apercu.html`) et trancher les points juridiques C2 à C4.
- [ ] Planifier la session photos et vidéos (A06) après réception du stock.
- [ ] Décider le plan publicitaire (G4) et une éventuelle collaboration (C15).
