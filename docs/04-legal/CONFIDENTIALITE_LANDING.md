# Déclaration de confidentialité de la page d'inscription (landing) — {{NOM_BOUTIQUE}}

> **À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION** (relecture express, avant le GO de publication de la landing C07).
> Brouillon v0.1 du 5.10.2026, rédigé par l'agent legal-ops. Ce texte n'est pas un avis juridique.
> Pourquoi une notice séparée : la landing est publiée à J10 (BP §9, J1-15), avant la boutique, le paiement, le transporteur et la relecture complète des textes (J28). La déclaration complète (`CONFIDENTIALITE.md`) décrit des traitements qui n'existent pas encore (commandes, paiement, livraison) et exige des champs connus seulement après les interventions B15, B16, B17 et C11. Cette notice décrit **uniquement** les traitements réels de la landing ; elle est remplacée par la déclaration complète à l'ouverture.
> Sources : formulaire `site/landing/index.html` et contrat `site/landing/inscription.schema.json` (chaque champ collecté est listé au ch. 2 : contrôle automatique par `site/outils/verifier_site.py`) ; contrat n8n `site/landing/README.md` §4 ; protocole `docs/01-marche/PROTOCOLE_LANDING_TEST.md` (hypothèses H2 à H4 : usages agrégés des réponses facultatives) ; LPD art. 6, 19, 21, 25 [L5].
> Page générée : `site/landing/confidentialite.html` (`python site/outils/publication.py source`). Les champs `{{…}}` sont ceux du registre `champs_a_remplir.yaml`.

<!-- TEXTE_PUBLIC:DEBUT -->
## Déclaration de confidentialité — inscription aux alertes

Version en vigueur depuis le {{DATE_VERSION_LANDING}}.

Notre boutique n'est pas encore ouverte. Cette déclaration couvre uniquement cette page de présentation, l'inscription à nos alertes et les messages que vous nous envoyez. Aucune commande, aucun paiement, aucune livraison et aucun compte client ne sont traités ici. À l'ouverture de la boutique, une déclaration complète remplacera celle-ci et nous l'annoncerons aux personnes inscrites. Elle se fonde sur la loi fédérale sur la protection des données (LPD).

### 1. Responsable du traitement

{{RAISON_SOCIALE}}, {{ADRESSE_POSTALE}}, Suisse. Personne responsable : {{NOM_RESPONSABLE}}. Contact pour toute question sur vos données : {{EMAIL_DONNEES}}.

### 2. Données traitées, finalités et durées

| Situation | Données | Pourquoi | Durée de conservation |
|---|---|---|---|
| Inscription aux alertes | Adresse email ; texte, version et date de votre consentement ; date de confirmation | Vous envoyer l'email de confirmation puis, seulement après votre clic, l'alerte d'ouverture, les alertes de stock que vous avez choisies et au plus un email récapitulatif par semaine ; prouver votre consentement | {{DUREE_CONSERVATION_ALERTES}} |
| Réponses facultatives du formulaire | Prénom ; formats qui vous intéressent ; budget habituel par achat ; pour qui vous achetez ; canton | Vous saluer par votre prénom et n'envoyer que les alertes qui correspondent à vos choix. De façon agrégée (jamais personne par personne) : étudier la demande pour choisir notre assortiment, nos contenus et les régions où faire connaître la boutique | Même durée que l'inscription |
| Origine de votre visite | Source, support et campagne du lien suivi (paramètres « utm ») ; adresse de la page d'inscription | Savoir, de façon agrégée, quels canaux amènent des inscriptions | Même durée que l'inscription |
| Lecture de nos emails | Ouvertures et clics mesurés par l'outil d'envoi | Cesser d'écrire aux personnes qui ne lisent plus nos emails ; mesurer, de façon agrégée, l'intérêt de nos envois | Même durée que l'inscription |
| Désinscription | Adresse email et date de la désinscription | Ne plus jamais vous écrire (liste d'exclusion) | Tant que nécessaire pour respecter votre désinscription |
| Protection du formulaire | Adresse IP et heure de l'envoi du formulaire | Limiter les envois abusifs ou automatisés | Non enregistrées avec votre inscription ; effacées après le contrôle |
| Visite de la page | Données techniques transmises par votre navigateur (adresse IP, type de navigateur, page demandée) | Afficher la page et la sécuriser ; charger les polices de caractères | Selon les règles de l'hébergeur et du fournisseur des polices (ch. 4) |
| Messages que vous nous envoyez | Vos messages, nos réponses | Vous répondre | {{DUREE_CONSERVATION_SAV}} |

Les réponses facultatives le restent : sans elles, vous recevez les mêmes alertes générales. Nous ne vendons pas vos données et ne vous demandons aucune donnée sensible au sens de la LPD. Cette page ne dépose aucun cookie et ne contient ni outil de mesure d'audience, ni pixel publicitaire. Si vous choisissez un thème d'affichage (clair ou sombre), ce seul choix est mémorisé dans votre navigateur (stockage local) et n'est transmis à personne ; vous pouvez l'effacer avec les données de navigation.

### 3. Emails et désinscription

- Nous ne vous écrivons qu'après votre confirmation : case non pré-cochée, puis lien de confirmation dans un email. Sans confirmation, vous ne recevez aucun autre email.
- Chaque email contient un lien de désinscription gratuit, en un clic. La désinscription est appliquée à tous nos outils sans délai.
- Nous n'envoyons pas de SMS et ne transmettons votre adresse ni à une régie publicitaire, ni à un réseau social.

### 4. Prestataires et destinataires

Nous confions certains traitements à des prestataires qui agissent pour notre compte, selon nos instructions et sous contrat :

| Rôle | Prestataire | Pays de traitement et garantie |
|---|---|---|
| Hébergement de cette page | {{ST_HEBERGEMENT_LANDING}} | {{ST_HEBERGEMENT_LANDING_PAYS}} |
| Polices de caractères de la page | {{ST_POLICES}} | {{ST_POLICES_PAYS}} |
| Réception du formulaire et automatisations (confirmation, alertes, désinscription) | {{ST_BASE}} | {{ST_BASE_PAYS}} |
| Envoi des emails | {{ST_EMAILING}} | {{ST_EMAILING_PAYS}} |
| Messagerie (messages que vous nous envoyez) | {{ST_MESSAGERIE}} | {{ST_MESSAGERIE_PAYS}} |
| Outils d'intelligence artificielle qui trient vos messages, préparent et envoient nos réponses courantes | {{ST_IA}} | {{ST_IA_PAYS}} |

Vos réponses au formulaire d'inscription ne sont transmises à aucun outil d'intelligence artificielle. Nous transmettons aussi des données lorsque la loi l'exige (par exemple à une autorité).

### 5. Communication à l'étranger

Certains prestataires peuvent traiter des données hors de Suisse. Nous ne le faisons que vers des États dont la législation assure un niveau de protection adéquat selon le Conseil fédéral ou, à défaut, avec des garanties appropriées, en particulier des clauses contractuelles types (art. 16 LPD). Le pays et la garantie de chaque prestataire sont indiqués au chiffre 4. Vous pouvez nous demander une copie des garanties utilisées.

### 6. Réponses automatisées

- Les réponses courantes à vos messages sont préparées et envoyées par des outils automatisés, à partir de modèles que nous avons validés. Vous pouvez à tout moment demander qu'une personne reprenne votre demande ; toute décision qui vous concerne peut être réexaminée par une personne, et vous pouvez donner votre point de vue (art. 21 LPD).
- Nous ne transmettons à ces outils que les informations nécessaires pour vous répondre et n'autorisons pas leur fournisseur à utiliser vos données pour entraîner ses modèles.

### 7. Sécurité

Nous protégeons vos données par des mesures techniques et organisationnelles adaptées : accès limités au strict nécessaire, double authentification sur les comptes d'administration, prestataires sous contrat. En cas de violation de la sécurité des données présentant un risque élevé pour vous, nous l'annonçons au Préposé fédéral à la protection des données et à la transparence (PFPDT) et, si nécessaire, nous vous en informons (art. 24 LPD).

### 8. Vos droits

Vous pouvez à tout moment, gratuitement :

- savoir si nous traitons des données vous concernant et en obtenir une copie (droit d'accès, art. 25 LPD) ;
- faire corriger des données inexactes ou compléter vos préférences ;
- demander l'effacement de vos données ou vous opposer à un traitement, y compris à l'usage agrégé de vos réponses facultatives ;
- retirer votre consentement, pour l'avenir ;
- recevoir les données que vous nous avez fournies dans un format électronique courant (art. 28 LPD).

Écrivez à {{EMAIL_DONNEES}}. Nous répondons dans un délai de 30 jours ; nous pouvons vous demander une preuve d'identité pour éviter qu'une autre personne n'accède à vos données. Si vous estimez que vos droits ne sont pas respectés, vous pouvez vous adresser au PFPDT (www.edoeb.admin.ch).

### 9. Mineurs

Les personnes de moins de 16 ans doivent obtenir l'accord de leur représentant légal avant de s'inscrire.

### 10. Modifications

Nous pouvons adapter cette déclaration. La version en vigueur est publiée sur cette page, avec sa date. À l'ouverture de la boutique, elle est remplacée par la déclaration complète.
<!-- TEXTE_PUBLIC:FIN -->

## Partie interne (ne pas publier)

### A. Notes pour le juriste (relecture express avant J10)

| # | Point | Question |
|---|---|---|
| N1 | Réponses facultatives et analyse agrégée | Base suffisante : information claire au moment de la collecte (aide sous la case de consentement et ch. 2) et caractère facultatif ? Faut-il une case distincte pour l'usage agrégé (H2 à H4 du protocole landing) ? |
| N2 | Polices Google Fonts | Le chargement transmet l'adresse IP à Google. Option sans transfert : publication avec `--sans-google-fonts` et `ST_POLICES` = « aucun : polices du système ». `publication.py` refuse une notice incohérente avec le choix fait. |
| N3 | Adresse IP du formulaire | Limitation des envois abusifs par le workflow n8n, sans enregistrement avec l'inscription (`site/landing/README.md` §4) : formulation et durée suffisantes ? |
| N4 | Messages et IA | Mêmes questions que C5 et C6 de `CONFIDENTIALITE.md` (sous-traitance, transfert, entraînement exclu, réexamen par une personne sur demande). |
| N5 | Âge de 16 ans | Même question que C8 de `CONFIDENTIALITE.md`. |
| N6 | Durée de validité | Notice limitée à la période d'avant ouverture (J10 à J38 visés) : remplacement par la déclaration complète à l'ouverture, annoncé aux inscrits. |

### B. Champs exigés pour publier la landing

La liste fermée est `CHAMPS_LANDING` dans `site/outils/publication.py` (commande `python site/outils/publication.py etat`). Chaque champ doit avoir le statut `valide` ; aucun ne dépend de la boutique Shopify, du prestataire de paiement, du transporteur ni de la relecture complète des textes (C11). Champs **provisoires autorisés** (valeur validée mais appelée à changer, republier après changement) : `URL_LANDING` (adresse de l'hébergeur avant le domaine), `MOIS_OUVERTURE` (mois visé, jamais une date ferme), `DATE_VERSION_LANDING` (version de cette notice, remplacée à l'ouverture).

## Validation humaine requise

- [ ] Juriste : relecture express de ce texte et des notes N1 à N6 avant le GO de publication de la landing (C07).
- [ ] Propriétaire : valider les durées (`DUREE_CONSERVATION_ALERTES`, `DUREE_CONSERVATION_SAV`) et dater la version (`DATE_VERSION_LANDING`).
- [ ] Agent 12 QA puis juriste : remplir les prestataires de la landing et leurs pays à partir des contrats réellement acceptés (hébergeur, polices, n8n, emailing, messagerie, IA) ; aucun pays ne doit être supposé.
- [ ] Propriétaire : choisir Google Fonts ou les polices du système (`--sans-google-fonts`) et renseigner `ST_POLICES` en conséquence.
