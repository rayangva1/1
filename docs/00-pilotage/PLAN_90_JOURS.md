# Plan 90 jours — {{NOM_BOUTIQUE}}

> Traduction opérationnelle du BP (version du 4.10.2026) : §9 (communication et acquisition sur 90 jours), §13 (plan de réalisation et critères de recette), §11 (ordre des dépendances).
> **Hypothèse de calendrier : J1 = lundi 5 octobre 2026** (à confirmer, BL-016). Si J1 glisse, toutes les dates glissent d'autant ; les dates externes du §2 ne bougent pas.
> Responsables : **H** = propriétaire (humain), **A-nn** = agent du BP §11 (01 chef de projet … 12 QA), **GOV** = agent gouvernance. Les numéros `BL-nnn` renvoient à `BACKLOG.csv`. Gates et seuils : `GATES_GO_NO_GO.md`.

## 1. En bref

| Élément | Valeur |
|---|---|
| Objectif unique | Étoile polaire : contribution nette cumulée positive et croissante. Ni CA ni followers. |
| Chemin critique | Mandat (J1) → demandes fournisseurs (J3) → compte + exemple de fichier (J14) → connecteur et 10 SKU (J18) → prix contrôlés (J21) → 20 synchronisations (J28) → recette (J30) → **G3 achat** (J30) → réception (J35) → **ouverture douce** (J38). Les 20 synchronisations ne comptent que sur **20 livraisons fournisseur réelles distinctes** (fichiers non FICTIFS, datés, de contenu différent ; `GET /sync/history`) : demander au fournisseur, dès l'exemple de fichier (BL-049), un flux au moins quotidien ou plusieurs livraisons par jour, sinon G3 glisse dans la marge (jusqu'à J45). |
| Marge sur le chemin critique | ≈ 7 jours : l'ouverture douce peut glisser jusqu'à J45 sans sortir de la fenêtre du BP (J31-45). Le délai de livraison du fournisseur est la grande inconnue. |
| Interventions humaines | Concentrées en S1-S2 (actes légaux et comptes, une fois), puis S5-S6 (achat, réception, photos). Ensuite : colis, validations hors mandat, stop-loss. Détail : `INTERVENTIONS_HUMAINES.md`. |
| Charge humaine estimée | 6 à 10 h par semaine de supervision au lancement, plus les colis (hypothèse BP §3). Estimation par semaine au §6. |
| Décision finale | G7 à J_V1 + 60 (J_V1 = 1re commande payée), soit vers le 3 au 17 janvier 2027, après J90 (écart EC-07). |

## 2. Calendrier externe à intégrer

Sources consultées le 4.10.2026 via index de recherche web (accès direct aux sites bloqué depuis l'environnement de build). Dates à reconfirmer sur la source officielle avant toute communication publique.

| Date | J | Événement | Effet sur le plan | Source |
|---|---|---|---|---|
| 2.10.2026 | J−3 | Bundle et mini-tins 30ᵉ Anniversaire (FR) | Références candidates du panier pilote | https://www.pokemon.com/fr/actualites/decouvrez-tous-les-produits-du-jcc-pokemon-qui-sortiront-en-septembre-2026 (et relais pokekalos.fr) |
| 23.10.2026 | J19 | Collection Classeur 30ᵉ Anniversaire (FR) | Candidate « coffrets » | idem |
| 24.10.2026 | J20 | Avant-premières Méga-Évolution – Règne Delta (boutiques Play! participantes) | Aucune action : nous ne sommes pas une boutique Play! | https://www.pokemon.com/fr/actualites/participez-a-un-evenement-davant-premiere-pour-lextension-mega-evolution-regne-delta-du-jcc-pokemon |
| 6.11.2026 | J33 | **Sortie FR Méga-Évolution – Règne Delta (ME06)** | Pic de demande pendant l'ouverture douce. Allocation improbable pour un nouveau compte : **aucune précommande sans allocation ferme**. | https://www.pokebip.com/news/7489/jcc-pokemon-nouvelle-extension-mega-evolution-regne-delta ; https://www.pokemon.com/us/news/the-pokemon-tcg-mega-evolution-delta-reign-expansion-arrives-november-6-2026 |
| 27.11.2026 | J54 | Black Friday | Enchères publicitaires élevées pendant le test pub (EC-10) | Calendrier commercial |
| Mi-décembre | ≈ J70-77 | Dernières dates d'expédition avant Noël | À relever chez le transporteur choisi (BL-053) et à afficher | À vérifier (transporteur) |
| 25.12.2026 | J82 | Noël | Disponibilité réduite de la propriétaire pour les colis : prévoir les dates d'expédition à l'avance | — |
| Fin janv. / début févr. 2027 | > J90 | Fenêtre habituelle de la 1re extension de l'année (rien d'annoncé au 4.10.2026) | Hors plan ; à surveiller pour G7 | https://jollycards.fr/pages/calendrier-des-sorties-pokemon (calendrier secondaire) |

## 3. Jours 1 à 15 — au jour (BP §9 « étude concurrence ; 10 entretiens ; dossier B2B ; page présentation et inscriptions » ; §13 S1-S2)

| J | Date | Livrables du jour | Responsable | Sortie attendue | Dépend de |
|---|---|---|---|---|---|
| J0 | dim. 4.10 | Dossiers du build livrés : dossier B2B, emails, panier, comparateur, protocoles, gates | A-01, A-02 (build) | Pack prêt à valider | — |
| J1 | lun. 5.10 | Créer l'email dédié (BL-003) · créer le coffre de secrets **avant** la signature (BL-005) · signer le mandat et reporter son empreinte au coffre (BL-002) · activer le niveau 1 (BL-006) · valider J1 et les seuils des gates (BL-016) | **H** (≈ 2 h) | G0 VERT | BL-001 |
| J1 | lun. 5.10 | Re-vérifier URL et contacts (BL-021) · lancer le relevé concurrence (BL-020) · shortlist fiduciaires (BL-008) · lancer le naming (BL-028) | A-02, A-06 | Tracker daté | G0 |
| J2 | mar. 6.10 | Votre jeton (BL-176), un jeton par rôle utilisé (17 : les 10 connecteurs n8n et les 7 agents qui ont accès à l'API) et un secret par passerelle n8n (10) sur votre ordinateur (Linux ou macOS) (une commande, `DELEGATION_AUTONOMIE.md` §10 étape 6), jetons et secrets au coffre, empreintes prêtes pour J8 (BL-177) · valider le dossier B2B provisoire (BL-036) et le panier pilote (BL-038) | **H** (≈ 1 h 45) | Dossier et panier validés ; jetons au coffre, empreintes prêtes | BL-035, BL-039 |
| J2 | mar. 6.10 | Demandes : banques et PSP (BL-051), transporteurs (BL-053), juristes (BL-056), assurances (BL-058) | A-02 | Demandes envoyées | BL-002, BL-003 |
| J3 | mer. 7.10 | **Envoyer la demande aux 3 fournisseurs FR** : Asmodee, Matoo et Miao, TCG Distribution (BL-040) | A-02 | 3 envois datés | BL-036, BL-038, BL-021 |
| J3 | mer. 7.10 | Budget et charges d'avant ouverture (BL-013) · point zéro du stop-loss global : **décision** (BL-180, option A recommandée ; pose à J27, BL-191) · comptes outils (BL-015) · PayPal dédié (BL-004) · consentement des entretiens (BL-024) | **H** (≈ 1 h 45) | Budget et point zéro actés | — |
| J4 | jeu. 8.10 | Demandes OtakuWorld et CardCosmos (BL-041) · questionnaire en ligne (BL-023) · 3 pistes de nom (BL-028) | A-02, A-09, A-06 | 5/5 demandes envoyées | BL-040 |
| J4 | jeu. 8.10 | Décider de la piste Carletto AG (BL-043) | **H** (10 min) | Oui ou non | EC-01 |
| J5 | ven. 9.10 | Mandater la fiduciaire (BL-009) | **H** (≈ 30 min + rendez-vous) | Lettre de mission | BL-008 |
| J5 | ven. 9.10 | Contacter Carletto AG si autorisé (BL-042) · relevé concurrence (suite) | A-02 | — | BL-043 |
| J6-J7 | sam.-dim. 10-11.10 | **Valider le nom** (BL-029, avancé : EC-08) · choisir l'entité exploitante avec la fiduciaire (BL-007) · recruter les participants et diffuser l'appel à entretiens (BL-025) | **H** (≈ 1 h 15) | Nom et entité retenus | BL-028, BL-009 |
| J7 | dim. 11.10 | **Gate G1** (BL-063) : accès fournisseur et hypothèses critiques identifiés | A-01 | Fiche G1 | BL-040, BL-020 |
| J8 | lun. 12.10 | Relance J+5 (BL-044) · médiane marché (BL-022) | A-02, A-05 | Relances envoyées | BL-040, BL-020 |
| J8 | lun. 12.10 | Acheter le domaine, créer les comptes réseaux (BL-030) · mandater le juriste (BL-057, avancé pour la relecture de J9) · héberger n8n en HTTPS au nom de l'entité avec la pile interne en simulation : fichier de variables hors du dépôt, empreintes de rôle copiées sur le serveur (`scp`), contrôlées, ajoutées puis copie effacée (`shred -u`), version de n8n épinglée (`N8N_IMAGE`, jamais `latest`) avant le premier lancement, `scripts/compose.sh up -d db db-migrate db-backup api n8n`, seuls le webhook d'inscription et les liens des emails publics, 04 et les liens des emails exécutés dans la version épinglée avant activation (BL-186, avec l'agent 07) · premiers entretiens (BL-026) | **H** (≈ 3 h 30 + entretiens) | Domaine actif ; juriste mandaté ; n8n en ligne, incidents notifiés par 04 | BL-029, BL-056, BL-005, BL-015, BL-176, BL-177 |
| J9 | mar. 13.10 | Landing construite (BL-031) · notice de confidentialité (BL-033) · workflow n8n « inscription aux alertes » construit et recetté, aucune exécution conservée (BL-187, contrat `site/landing/README.md` §4) | A-07, A-12 | Landing en préproduction ; `WEBHOOK_INSCRIPTION` validé | BL-029, BL-186 |
| J9 | mar. 13.10 | Relecture express de la notice par le juriste, datation `DATE_VERSION_LANDING`, choix des polices et de l'hébergeur de la landing, acceptation du fournisseur d'IA (`ST_IA`), validation des durées de conservation des alertes et des messages (BL-185) | **H** + juriste (≈ 45 min) | Notice relue et datée ; champs de la landing au statut `valide` | BL-033, BL-057 |
| J10 | mer. 14.10 | **Publier la landing** (BL-032, après la relecture BL-185, n8n en ligne BL-186 et le workflow d'inscription recetté BL-187 ; `python site/outils/publication.py etat` : 24/24 champs valides) · IDE (BL-011) · statut TVA (BL-010) · comptes revendeurs (BL-045) | **H** (≈ 1 h 30) | Landing en ligne ; comptes demandés | BL-031, BL-185, BL-186, BL-187, BL-007 |
| J11 | jeu. 15.10 | Saisie des premiers devis (BL-048) · import assisté si tarif PDF/email | A-02, A-03 | Comparateur alimenté | Réponses |
| J12 | ven. 16.10 | Due diligence des répondants (BL-046) · dossier B2B final (BL-037) | A-02, A-12 | Checklists remplies | BL-044 |
| J12 | ven. 16.10 | Validation des règles TVA et import par la fiduciaire (BL-061) | **H** + fiduciaire | Avis écrit | BL-009 |
| J13 | sam. 17.10 | Classement des offres (BL-048) | A-02, A-05 | Classement | BL-022 |
| J14 | dim. 18.10 | Exemple de fichier archivé (BL-049) · schéma de base et importeurs (BL-077, BL-078) · fin des entretiens (BL-026) | A-03, **H** | Fichier réel daté | BL-040 |
| J14 | (lun. 19.10 au plus tard) | Ajouter un fournisseur au mandat (BL-047) · valider les règles de prix v1 (BL-084) · signer les seuils du stop-loss et les règles de prix, empreintes au coffre (BL-181) · compte bancaire pro (BL-052) | **H** (≈ 1 h 15) | Fournisseur autorisé ; seuils signés | BL-046, BL-083 |
| J15 | lun. 19.10 | Relance J+12 (BL-044) · synthèse des entretiens (BL-027) · note de choix des sources (BL-050) · **Gate G2** (BL-064) | A-02, A-01 | Fiche G2 | BL-050, BL-049 |

**Critère de passage (BP §9) :** flux fournisseur et marges pilote identifiés. **BP §13 S1 :** accès fournisseur et hypothèses critiques identifiés. **BP §13 S2 :** calculs contrôlés contre facture/devis (écart EC-09 : S3 au plus tard).

## 4. Semaines 3 à 13 — à la semaine

| Semaine | Dates | J | Livrables (BL) | Responsable : agents | Responsable : humain (H) | Critère de passage (BP) | Dépendances clés |
|---|---|---|---|---|---|---|---|
| S3 | 19-25.10 | J15-21 | 2 directions visuelles (070) · connecteur sur fichier réel (079) · 10 SKU normalisés (080) · pricing pilote (081) · contrôle contre devis (082) · API moteur (089) · SOP ops (104) | A-06, A-03, A-04, A-05, A-12, A-07, A-11 | Valider la DA et le logo (071) · créer la boutique Shopify (086) · Search Console (179) · activer paiements et TWINT (097) · compte transporteur (054) · AVS si requis (012) | §13 S2 : calculs contrôlés contre devis (0 écart > 0,01 CHF) | G2 ; exemple de fichier (049) ; statut TVA (010) |
| S4 | 26.10-1.11 | J22-28 | Charte (072) · composants (073) · thème (087) · client Shopify (088) · workflows n8n (090) · dashboard (091) · **20 synchronisations** sur livraisons réelles (092) · 10 fiches (094) · contenus (100, 101) · emails (102, 103) · packaging (075) · tests paiement (098) · dettes et précommandes déclarées chaque jour par l'agent 05, hausse seulement (190) | A-06, A-07, A-12, A-04, A-08, A-09, A-05 | Mise en service de la pile lancée à J8 : workflows 01 à 08 importés avec credentials par rôle et secrets de passerelle, activés dans l'ordre unique de `orchestration/README.md` §7 (05, 08, 01 et 03 à J26 ; 04 et les liens des emails de 06 depuis J8 ; 02 et les déclencheurs Shopify de 06 au niveau 2), webhooks Shopify et formulaires, restauration des sauvegardes vérifiée (178) · apports au registre (188) · accès en lecture seule à la banque et à PayPal, soldes du jour déposés par vous avec votre jeton tant que les relevés ne sont pas recettés (189) · canal d'alerte S1 (194) · **point zéro posé** à J27 avec la première photo (191), **puis** activation du workflow 07 · relecture juridique (096) · colis test et retour test (105) · assurance (059) · validation des 10 fiches FICTIVES de la recette si elles sont publiées par le moteur (197) | §13 S3-4 : 20 synchronisations sans erreur critique | Boutique (086) ; paiements (097) ; juriste (057) |
| S5 | 2-8.11 | J29-35 | Recette du parcours (099) · **dossier G3** (106) · emballages (076) · quota de précommande (170) · déclaration au moteur de chaque réception contrôlée (196) · commandes expédiées et avoirs enregistrés par le workflow 02, câblé **avant** la revue du niveau 2 (199, J34) | A-12, A-01, A-11, A-07 | Paiements réels de la recette, signature de la synthèse de recette et de la checklist LCD (193) · **Décision d'achat** ≤ 3 000 CHF (107) · devis de développement externalisé si G3 révèle un blocage technique (184) · commande et paiement (110) · **réception** (111) · **authenticité** (112) · avant la revue du niveau 2 : flotte isolée sous un compte dédié, vérifiée par script (204) · compte n8n sécurisé (205) · rotation d'un jeton et de deux secrets rejouée (206) · 02 et déclencheurs Shopify de 06 exécutés dans la version épinglée de n8n (207) | §9 J16-30 : paiement et stock sans erreur critique (à J30) | G3 VERT ; délai fournisseur ; **sortie Règne Delta le 6.11 (J33)** |
| S6 | 9-15.11 | J36-42 | Coût historique (113) · fiches publiées (115) · email d'ouverture aux inscrits (118) · 3 contenus/semaine (119) · SAV (121) · facture → marge (122) | A-05, A-07, A-04, A-09, A-11 | Session photos et vidéos (114) · **validation des fiches** avant publication (197) · vérifier que le point zéro est posé (C19) · revue adverse de sécurité relancée sur la version qui sera activée, après 199 et 204 à 207, sans critical/high ouvert (200) · niveau 2 (116) · **GO ouverture douce** (117) · **colis** (120) | §13 S5-6 : commandes tests payées et livrées correctement | Réception (111) ; recette (099) ; J_V1 consigné |
| S7 | 16-22.11 | J43-49 | **Dossier G4** (123) · plan du test pub (130) · connecteur publicitaire construit et recetté avant toute campagne (198) | A-01, A-10, A-07, A-12 | Décision G4 (123) · comptes pub et accès en lecture du connecteur publicitaire (131) · revue adverse de sécurité relancée, sans critical/high ouvert (201) · niveau 3 (132) · revue limitée au diff du connecteur publicitaire, sans critical/high ouvert, avant la première campagne (203, J49) · colis | §9 J31-45 : premières commandes livrées et contribution positive (à J45) | Commandes livrées |
| S8 | 23-29.11 | J50-56 | Test pub plafonné (130), jamais avant la recette du connecteur publicitaire et la revue de son diff (S7) · emails de réassort (135) · collaboration locale (134) | A-10, A-09 | Contrat du créateur s'il y en a un (134) · colis | — | **Black Friday le 27.11 (J54)** : plafond jour réduit ou démarrage le 30.11 |
| S9 | 30.11-6.12 | J57-63 | Mesure du CAC (133) · **dossier G5** (option B) · propositions de réassort (140) | A-10, A-05, A-11 | Décision G5 à J60 avec l'option B (136) · validation des réassorts (141) · colis | §9 J46-60 : CAC inférieur à la contribution disponible (à J60 avec l'option B) | 7 jours complets de données pub |
| S10 | 7-13.12 | J64-70 | Pages SEO par extension (143) · **dossier G5** (option A) · réassorts validés · affichage des dates limites d'expédition de Noël | A-08, A-11, A-10, A-05 | Décision G5 à J64 avec l'option A, recommandée : test démarré le 30.11 (136) · réception du réassort · colis | Critère G5 sur 7 jours complets (J57-J63) | Délai fournisseur avant Noël |
| S11 | 14-20.12 | J71-77 | Activation du 2e fournisseur (142) · scénarios email (144) | A-02, A-09 | Compte du 2e fournisseur (142) · colis (pic de Noël) | §13 S7-12 : deuxième fournisseur | Due diligence (046) |
| S12 | 21-27.12 | J78-84 | Marge réelle contre estimation (145) · SAV des fêtes | A-05, A-11 | Colis aux dates annoncées ; absence planifiée ; si le niveau 4 est envisagé : revue adverse de sécurité relancée, sans critical/high ouvert (202) | — | Factures reçues |
| S13 | 28.12-3.1 | J85-91 | **Bilan G6** (147) · niveau 4 optionnel (146) · examen TVA anticipé (148) · BFR (149) | A-01, A-05 | Décisions (146, 148, 149) · renouvellement ou fin du mandat avant `valid_until` (182) | §9 J61-90 : rotation et trésorerie compatibles avec croissance ; §13 S7-12 : automatisation stable et contribution positive | Bilan |
| Après | ≈ 3 au 17.1.2027 | J_V1 + 60 | **Dossier G7** (150) | A-01, A-05, A-12 | **Décision poursuivre / ajuster / reporter / arrêter** | BP §1 (4 indicateurs) et §13 | Bilan G6 |

**En continu à partir de S1 :** revue des exceptions chaque lundi (162), trésorerie sur 13 semaines (165), registre des risques (163), écarts BP (164). **Dès qu'une vente a eu lieu :** rapprochements (166), inventaire mensuel (167), mesure du temps passé (171). **Au besoin, avec votre jeton :** taux de change chaque jour ouvré d'achat ou de synchronisation en devise (183), approbation d'un prix hors règles (192), validation de toute fiche nouvelle ou modifiée (197), exception au plafond de 25 % (172), réarmement (168), mémoire des apports, reprise d'un incident critique, écriture manuelle de l'étoile polaire, ajustement de facture de plus de 2 % (`INTERVENTIONS_HUMAINES.md` C18, C23, C24, C27, C30). **Chaque mois :** copie des sauvegardes hors machine et contrôle R-I04 (195). Les stop-loss s'appliquent à tout moment (`GATES_GO_NO_GO.md` §1).

## 5. Ordre des dépendances (BP §11) et parallélisme

```
Sourcing + cadre fiscal ──► données fiables ──► catalogue et coûts ──► prix et stock ──► site
   (S1-S2)                   (S2-S3)              (S3)                   (S3-S4)            (S4-S5)
DA ─────────── en parallèle dès le nom validé (J7) ─────────────────────────────────────────►
Publication marketing ── attend le stock local reçu (S6) ou une allocation ferme ───────────►
QA ── contrôle les calculs (S3) et le parcours (S4-S5) ; peut bloquer une mise en ligne ────►
```

| Si ce maillon glisse… | Effet | Parade |
|---|---|---|
| Aucun fournisseur ne répond avant J12 | G2 ROUGE ; tout l'aval glisse | Relance J+12, appel téléphonique de la propriétaire (5 min, hors mandat), piste Carletto |
| Le compte est accepté mais sans fichier | Connecteur impossible en S3 | Import assisté d'un email ou PDF (BP §6, priorité 3) ; le gate G2 accepte l'ORANGE |
| KYC banque ou PSP > 2 semaines | Pas de tests de paiement en S4 ; G3 ROUGE | Lancer BL-052 et BL-097 dès J10 ; PSP de repli |
| Livraison fournisseur > 5 jours ouvrés | Ouverture repoussée vers J45 | Commander à J30 au plus tard ; ne pas promettre de date publique avant réception |
| Validation DA retardée | Thème et fiches retardés | Thème standard sobre (sans logo) pour la recette ; la DA s'applique ensuite |

## 6. Charge humaine estimée (hypothèse, à mesurer : BL-171)

| Semaine | Actes ponctuels (une fois) | Récurrent | Total estimé |
|---|---|---|---|
| S1 | Coffre puis mandat et son empreinte au coffre, email, jetons, budget, décision du point zéro, comptes outils, PayPal, fiduciaire, nom, entité, recrutement des participants | Entretiens (diffusion) | 7 à 9 h |
| S2 | Domaine, hébergement de n8n et de la pile interne (fichier de variables, compose, proxy), juriste et relecture de la notice, landing, IDE, TVA, comptes revendeurs, banque, règles de prix et signature des seuils | Entretiens (si oraux : 10 × 30 min) | 7 à 11 h |
| S3 | DA, Shopify, paiements, transporteur | — | 3 à 5 h |
| S4 | Mise en service (workflows, webhooks, formulaires, restauration vérifiée), apports, accès en lecture seule banque et PayPal, canal d'alerte, point zéro, textes légaux, colis test, assurance, validation des fiches de la recette | Copie chiffrée des sauvegardes (mensuel) | 6 à 9 h |
| S5 | Paiements réels et signature de la recette, achat, commande ; isolation de la flotte, compte n8n, rotation des secrets, exécution de 02 et 06 dans n8n (≈ 3 h 30) | Réception et authenticité | 9 à 13 h |
| S6 | Validation des fiches (≈ 3 min par fiche), niveau 2, GO ouverture | Photos et vidéos (session groupée), colis | 7 à 11 h + colis |
| S7-S13 | Gates G4 et G5, niveaux 3 et 4, réassorts, 2e fournisseur | Colis, inventaire, validations | 6 à 10 h + colis (BP §3) |

## Validation humaine requise

- [ ] Confirmer la date de J1 (lundi 5.10.2026 par hypothèse) ou en fixer une autre ; toutes les dates du plan se recalent.
- [ ] Accepter l'avancement de la validation du nom à J6-J7 (écart EC-08), condition de la landing en S2.
- [ ] Confirmer la disponibilité indiquée au §6, notamment en S1-S2 et S5-S6.
- [ ] Décider de la position face à la sortie Règne Delta (6.11) : l'ouverture douce n'en dépend pas, et aucune précommande sans allocation ferme.
- [ ] Choisir la règle autour du Black Friday pour le test publicitaire (G4).
- [ ] Planifier la disponibilité pour les colis entre le 21.12 et le 3.1.
