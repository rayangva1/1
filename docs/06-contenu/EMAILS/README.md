# Emails transactionnels et automatisations

> Propriétaire (build) : agent « site-contenu ». Exploitation : agent 09 (textes, BL-102, BL-118, BL-135, BL-144), agent 07 / integrations (intégration Shopify et n8n), agent 12 (consentements, désinscription : BL-103).
> Sources : BP §9 « Automatisations marketing » (inscription → accueil et préférence de formats ; nouveau stock local → alerte aux inscrits intéressés ; commande expédiée → suivi ; livraison → demande d'avis ; réachat avec consentement et disponibilité ; panier abandonné seulement si la collecte le permet ; désinscription propagée à tous les outils ; pas de SMS ni d'email non sollicité), §7 (confirmation électronique exacte, consentements), §5 (précommandes) ; `docs/04-legal/PRECOMMANDES.md`, `CONFIDENTIALITE.md` (notes C2 à C4) ; gabarit DA `docs/05-da/components/email-transactionnel-a.html`.
> Nom de travail : « Quai des Cartes » (provisoire) — dans les modèles, le nom est le champ `{{NOM_BOUTIQUE}}`.

## 1. Fichiers

| Chemin | Contenu |
|---|---|
| `source/emails.yaml` | **Source unique** : objet, pré-en-tête, déclencheur, segment, base légale, fréquence, variables (avec exemple FICTIF), blocs de contenu |
| `html/NN-*.html` | Modèles HTML générés : tableaux, styles en ligne, largeur 600 px, couleurs de la DA (direction A, clair) lues dans `docs/05-da/tokens/tokens.json` |
| `html/_ligne-produit-*.html` | Gabarits d'une ligne produit (stock local, précommande) pour construire `lignes_produits_html` |
| `texte/NN-*.txt` | Versions texte |
| `apercu.html` | Les 19 emails remplis avec des données FICTIVES, pour la relecture par la propriétaire |
| `../outils/generer_emails.py` | Génération (`--verifier` : contrôle de synchronisation ; `--integration DOSSIER` : copie prête à intégrer avec les champs validés) |

## 2. Les 19 emails

<!-- TABLEAU:DEBUT (généré par docs/06-contenu/outils/generer_emails.py) -->
| N° | Email | Canal | Déclencheur | Segment | Base | Fréquence | Objet |
|---|---|---|---|---|---|---|---|
| 01 | [Confirmation d'inscription (double opt-in)](html/01-confirmation-inscription.html) · [texte](texte/01-confirmation-inscription.txt) | n8n | Formulaire d'inscription reçu (landing ou formulaire Shopify), adresse non encore confirmée | La seule personne inscrite, statut en_attente | Demande explicite de la personne ; email unique, sans contenu promotionnel | Une fois par inscription ; pas de relance automatique | Confirmez votre alerte {{NOM_BOUTIQUE}} |
| 02 | [Bienvenue et préférences](html/02-bienvenue-preferences.html) · [texte](texte/02-bienvenue-preferences.txt) | n8n | Clic sur le lien de confirmation | La personne qui vient de confirmer | Consentement confirmé (double opt-in) | Une fois | Vos alertes {{NOM_BOUTIQUE}} sont actives |
| 03 | [Ouverture douce (BL-118)](html/03-ouverture-boutique.html) · [texte](texte/03-ouverture-boutique.txt) | n8n | GO de l'ouverture douce (C14) : fiches publiées, stock local réel | Tous les inscrits confirmés | Consentement confirmé (alerte d'ouverture) | Une fois | {{NOM_BOUTIQUE}} est ouverte : ce qui est en stock local |
| 04 | [Alerte : nouveau stock local](html/04-alerte-stock-local.html) · [texte](texte/04-alerte-stock-local.txt) | n8n | Entrée en stock local réelle (réception contrôlée, fiche publiée) d'un produit suivi | Inscrits confirmés : alerte sur ce produit, ou préférences correspondant au format | Consentement confirmé (alertes de stock choisies) | Au plus une alerte par produit et par personne ; pas d'envoi si le stock repasse à zéro avant l'envoi | En stock local : [[produit_titre]] |
| 05 | [Récapitulatif hebdomadaire](html/05-recapitulatif-hebdo.html) · [texte](texte/05-recapitulatif-hebdo.txt) | n8n | Jeudi (calendrier), seulement s'il y a un contenu utile ; sinon pas d'envoi | Inscrits confirmés ayant choisi le récapitulatif | Consentement confirmé (récapitulatif au plus hebdomadaire) | Au plus un par semaine (BP §9) | Cette semaine chez {{NOM_BOUTIQUE}} : [[titre_semaine]] |
| 06 | [Confirmation de commande (notification Shopify)](html/06-confirmation-commande.html) · [texte](texte/06-confirmation-commande.txt) | shopify | Commande payée (notification Shopify « Confirmation de commande ») | Le client de la commande | Exécution du contrat ; aucun contenu promotionnel | Une fois par commande | Commande [[order_name]] confirmée |
| 07 | [Expédition et suivi (notification Shopify)](html/07-expedition-suivi.html) · [texte](texte/07-expedition-suivi.txt) | shopify | Envoi marqué expédié (notification Shopify « Confirmation d'expédition ») | Le client de la commande | Exécution du contrat | Une fois par envoi (une commande mixte = deux envois) | Commande [[order_name]] expédiée |
| 08 | [Précommande confirmée](html/08-precommande-confirmee.html) · [texte](texte/08-precommande-confirmee.txt) | n8n | Commande payée contenant une ligne de précommande (en plus de la confirmation de commande) | Le client de la commande | Exécution du contrat (information sur la précommande) | Une fois par ligne de précommande | Précommande enregistrée : [[produit_titre]] |
| 09 | [Précommande : report de date](html/09-precommande-report.html) · [texte](texte/09-precommande-report.txt) | n8n | Nouvelle date de sortie reçue (événement « report » du catalogue) | Clients ayant une précommande ouverte sur ce produit | Exécution du contrat (PRECOMMANDES : information du report) | À chaque report | Report de sortie : [[produit_titre]] |
| 10 | [Précommande annulée et remboursée (quantité réduite ou annulée)](html/10-precommande-annulee.html) · [texte](texte/10-precommande-annulee.txt) | n8n | Allocation réduite ou annulée : précommande non servie (ordre de paiement) | Clients dont la précommande ne peut pas être servie | Exécution du contrat (PRECOMMANDES : remboursement intégral) | Une fois | Précommande annulée et remboursée : [[produit_titre]] |
| 11 | [Demande d'avis après livraison](html/11-demande-avis.html) · [texte](texte/11-demande-avis.txt) | n8n | Livraison confirmée + 7 jours (hypothèse), commande sans réclamation ouverte | Clients non opposés (case d'opposition au checkout non cochée) | À valider par le juriste (note C3 : un seul email, avec lien de refus) | Une seule demande par commande | Votre commande [[numero_commande]] est bien arrivée ? |
| 12 | [Réachat : suggestion sur extension ou format déjà acheté](html/12-reachat.html) · [texte](texte/12-reachat.txt) | n8n | Produit de la même extension ou du même format entré en stock local | Clients ayant acheté cette extension ou ce format, avec consentement marketing, sans désinscription | Consentement marketing (ou client non opposé : note C2 du juriste) | Au plus une suggestion par mois et par personne (hypothèse) | [[produit_titre]] : en stock local |
| 13 | [Panier abandonné (seulement avec consentement marketing)](html/13-panier-abandonne.html) · [texte](texte/13-panier-abandonne.txt) | n8n | Paiement non terminé depuis 4 h (hypothèse) ; articles encore disponibles | Uniquement les personnes ayant coché le consentement marketing au checkout (note C4 du juriste) | Consentement marketing explicite ; sinon AUCUN envoi | Un seul email par panier ; aucun code promo | Votre panier est enregistré |
| 14 | [Désinscription confirmée (facultatif)](html/14-desinscription-confirmee.html) · [texte](texte/14-desinscription-confirmee.txt) | n8n | Clic sur « me désinscrire » (envoi facultatif : décision propriétaire et juriste) | La personne qui se désinscrit | Information sur l'exécution de la demande ; aucun contenu promotionnel | Une fois ; jamais de relance | Désinscription enregistrée |
| 15 | [Pré-drop : réservation garantie confirmée](html/15-pre-drop-reservation-confirmee.html) · [texte](texte/15-pre-drop-reservation-confirmee.txt) | n8n | Réservation pré-drop payée et confirmée par le moteur (POST /predrop/reservations : CONFIRMED, nouvellement enregistrée), en plus de la confirmation de commande Shopify (06) | Le client de la commande | Exécution du contrat (PRECOMMANDES : réservation garantie) | Une fois par réservation ; rejeu du webhook : aucun envoi | Réservation garantie confirmée : [[produit_titre]] |
| 16 | [Pré-drop : accès prioritaire des inscrits aux alertes](html/16-pre-drop-acces-prioritaire.html) · [texte](texte/16-pre-drop-acces-prioritaire.txt) | n8n | Pré-drop ouvert, fenêtre prioritaire (étape « prioritaire » calculée par le moteur, GET /predrop/offers) | Inscrits confirmés AVANT l'ouverture qui suivent ce produit (alerte sur la fiche), non désinscrits, dont le compte de la boutique est relié à l'inscription (étiquette alerte-produit posée) : sans compte relié, aucun email pendant la fenêtre prioritaire (email 17 à l'ouverture à tous) | Consentement confirmé (alerte demandée sur ce produit) | Une annonce par pré-drop et par personne ; pas de seconde annonce à l'ouverture à tous | Réservations garanties : [[produit_titre]], d'abord pour vous |
| 17 | [Pré-drop : annonce du drop, réservations garanties ouvertes à tous](html/17-pre-drop-ouverture.html) · [texte](texte/17-pre-drop-ouverture.txt) | n8n | Fin de la fenêtre prioritaire : réservations ouvertes à tous (étape « ouvertes » calculée par le moteur) | Inscrits confirmés qui suivent ce produit et n'ont pas reçu l'accès prioritaire (inscrits depuis l'ouverture, ou sans compte de la boutique relié), non désinscrits | Consentement confirmé (alerte demandée sur ce produit) | Une annonce par pré-drop et par personne | Drop le [[date_drop]] (date estimée) : [[produit_titre]] |
| 18 | [Pré-drop : réservation remboursée intégralement (allocation réduite, non servie ou annulée)](html/18-pre-drop-remboursement.html) · [texte](texte/18-pre-drop-remboursement.txt) | n8n | Remboursement pré-drop exécuté chez le prestataire de paiement et relevé au moteur (POST /predrop/refunds/{id}/executed, premier relevé) | Le client de la réservation remboursée | Exécution du contrat (PRECOMMANDES : remboursement intégral, supplément compris) | Une fois par remboursement | Réservation garantie remboursée : commande [[numero_commande]] |
| 19 | [Pré-drop : réservation garantie expédiée en priorité](html/19-pre-drop-expedition-prioritaire.html) · [texte](texte/19-pre-drop-expedition-prioritaire.txt) | n8n | Envoi d'une commande qui contient une réservation garantie (Shopify orders/fulfilled, ligne au SKU -RESA-), en plus de l'email 07 de Shopify (suivi) | Le client de la commande | Exécution du contrat (information sur la réservation garantie) | Une fois par envoi contenant une réservation | Réservation garantie expédiée : commande [[numero_commande]] |
<!-- TABLEAU:FIN -->

## 3. Trois sortes de variables

| Syntaxe dans les modèles | Origine | Rempli quand | Exemple |
|---|---|---|---|
| `{{ $json.nom }}` | Workflow n8n (données de l'envoi) | À chaque envoi, par le nœud n8n qui compose l'email | `{{ $json.salutation }}`, `{{ $json.url_desinscription }}` |
| `{{ nom }}` et balises `{% … %}` (minuscules) | Liquid des notifications Shopify | À chaque envoi, par Shopify | `{{ order_name }}`, `{% for line in subtotal_line_items %}` |
| `{{CHAMP}}` (majuscules) | Registre légal `docs/04-legal/champs_a_remplir.yaml` (+ `URL_LOGO_PNG`) | **Une fois, à l'intégration** : `generer_emails.py --integration DOSSIER` refuse tant qu'un champ utilisé n'est pas `valide` | `{{EMAIL_SUPPORT}}`, `{{DELAI_EXPEDITION}}` |

**Attention Shopify** : un `{{CHAMP}}` non remplacé serait lu par Liquid comme une variable vide, sans erreur. Ne jamais coller dans Shopify un fichier de `html/` : toujours la copie produite par `--integration`.

Variables Liquid utilisées (notifications « Confirmation de commande » et « Confirmation d'expédition ») : `order_name`, `customer.first_name`, `subtotal_line_items` (`line.title`, `line.quantity`, `line.final_price`, `line.final_line_price`), `subtotal_price`, `discounts_amount`, `shipping_price`, `total_price`, `shipping_address`, `order_status_url`, `fulfillment.fulfillment_line_items` (`line.line_item.title`, `line.quantity`), `fulfillment.tracking_numbers`, `fulfillment.tracking_urls`, `fulfillment.tracking_company`. Sources : référence des variables de notification Shopify et objets Liquid `order` / `fulfillment` (help.shopify.com, shopify.dev), **indexées le 4.10.2026, pages non ouvertes** (domaines bloqués par le proxy de l'environnement de build) : chaque variable est à vérifier dans l'éditeur de notifications avant activation (recette, « aperçu » Shopify). Format monétaire de la boutique à régler sur `CHF {{amount}}` (libellé exact du réglage à vérifier) pour rester cohérent avec la DA (« CHF 209.90 »).

## 4. Règles pour le workflow n8n (agent integrations)

1. **Consentement d'abord** : 02 à 05 ne partent qu'à une personne inscrite aux alertes au statut `confirme`, non désinscrite, avec la préférence correspondante ; 12 seulement à un client avec consentement marketing (ou non opposé, note C2), non désinscrit ; 13 uniquement si le consentement marketing a été coché au checkout (note C4) ; 11 uniquement si la personne ne s'y est pas opposée (note C3). Le pied de chaque email marketing dit le motif réel d'envoi (`motif_pied` de la source : `alertes`, `client` ou `checkout`) ; seuls les emails `alertes` ont un lien « Modifier mes préférences », tous ont la désinscription en un clic.
2. **Jamais de donnée interne** dans un nœud qui compose un email : prix, statut et titre sont lus sur la **page publique** (ou `/publish/preview`) au moment de l'envoi ; un produit dont le statut n'est plus « stock local » ou « précommande » est retiré de l'email ; si plus aucun produit ne reste, l'email n'est pas envoyé.
3. **Stop-loss** : aucun email promotionnel (03, 04, 05, 12, 13) sur une référence sous stop-loss produit ; aucun envoi pendant un gel global.
4. `salutation` = « Bonjour {prénom}, » si le prénom est renseigné, sinon « Bonjour, ».
5. `lignes_produits_html` = concaténation des gabarits `_ligne-produit-stock-local.html` / `_ligne-produit-precommande.html` remplis par produit ; `lignes_produits_texte` = une ligne « titre · statut · CHF prix » par produit.
6. `texte_option_annulation` (email 09), deux textes exacts possibles, choisis par calcul de dates (aucune IA) :
   - report > `SEUIL_REPORT_PRECOMMANDE` : « Le report dépasse le délai prévu par nos conditions : vous pouvez annuler et obtenir un remboursement intégral. Répondez simplement à cet email. »
   - sinon : « Vous pouvez aussi annuler sans frais selon nos conditions de précommande. »
7. Chaque lien de désinscription est à jeton unique ; la désinscription est appliquée **à tous les outils** (emailing, Shopify, base) dans la minute, puis la page `desinscription.html` s'affiche ; l'email 14 est facultatif (§6).
8. Journal : chaque envoi est journalisé (modèle, destinataire pseudonymisé, horodatage, segment), sans le contenu.
9. **Pré-drop (emails 15 à 19)** : 15 part du workflow 02 après une réservation **confirmée** et nouvellement enregistrée (jamais au rejeu) ; 16 (fenêtre prioritaire) et 17 (annonce du drop, ouverture à tous) partent de 06, une annonce par pré-drop et par personne, aux seuls inscrits confirmés qui suivent la référence, avec la date du drop et le chemin de la fiche de réservation (jamais un prix, une quantité, une heure de fermeture ni un compte à rebours ; les deux prix se lisent sur la fiche) ; 18 part de 02 après le **premier** relevé d'un remboursement exécuté, avec le montant et le motif du moteur (`amount_ttc`, `reason_fr`) ; 19 part de 06 à l'expédition d'une commande qui contient une ligne au SKU `-RESA-`, en plus de l'email 07. Les deux phrases de garantie (« Le supplément pré-drop paie la garantie… », « Aucun remboursement de la différence… ») sont celles du moteur, mot pour mot.

## 5. Contrôles automatiques

`python docs/06-contenu/outils/verifier_contenu.py` vérifie notamment : modèles synchronisés avec la source ; aucune donnée interne, aucun EAN, aucune fausse urgence ni promesse interdite ; tout prix est une variable (aucun montant en dur dans les modèles) ; lien de désinscription dans chaque email marketing, lien de préférences dans ceux des inscrits aux alertes, motif d'envoi conforme au segment ; expressions n8n intactes (« $json » en minuscules, y compris dans les titres de la version texte) ; aucune affirmation inexacte (« une personne vous répond », limite « par commande ») ; mention d'indépendance et identité de l'exploitant dans chaque pied ; aucun `<script>`, `<style>` ni `var()` ; champs `{{CHAMP}}` connus du registre ; variables n8n déclarées.

## 6. Points à trancher

| Point | Proposition | Décideur |
|---|---|---|
| Email 11 (avis) : publicitaire ou non ? | Un seul email, lien de refus, clients non opposés | Juriste (C3) |
| Email 12 (réachat) : base légale | Consentement marketing, ou client non opposé (exception « clients existants ») | Juriste (C2) |
| Email 13 (panier abandonné) | Seulement avec consentement marketing coché au checkout ; un seul envoi, 4 h après (**hypothèse**) ; aucun code promo | Juriste (C4) + propriétaire |
| Email 14 (désinscription) | Facultatif ; la page `desinscription.html` suffit | Propriétaire + juriste |
| Délai de la demande d'avis | 7 jours après livraison (**hypothèse**) | Propriétaire |
| Fréquence des suggestions de réachat | Au plus une par mois et par personne (**hypothèse**) | Propriétaire |

## Validation humaine requise

- [ ] Relire `apercu.html` et valider les textes des 19 emails (transactionnels : RACI L44), dont les 5 emails du pré-drop (15 à 19).
- [ ] Juriste : relire les emails 15 à 19 avec les conditions de la réservation garantie (`docs/04-legal/PRECOMMANDES.md`, partie « Pré-drop », notes P1 à P8).
- [ ] Juriste : trancher les points C2, C3 et C4 (§6) avant d'activer 11, 12 et 13.
- [ ] Valider les champs du registre utilisés par les emails (délais, URL, identité, `MENTION_TVA`), puis lancer `--integration`.
- [ ] Recette : envoyer chaque email à une adresse de test (Shopify : notifications de test ; n8n : exécution manuelle), vérifier affichage mobile, liens, désinscription.
