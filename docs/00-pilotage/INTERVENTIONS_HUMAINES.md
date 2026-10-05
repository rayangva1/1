# Interventions humaines — checklist maîtresse

> Tout ce qui exige **une personne**, et seulement cela. Le reste est fait par la flotte d'agents **dans le mandat écrit** (`DELEGATION_AUTONOMIE.md`, agent gouvernance) : plafonds, fournisseurs autorisés, interdits, journal.
> Sources : BP du 4.10.2026, §12 « Ce qui demande encore une personne », §2, §3, §7, §8, §13 ; modèle d'opération de la propriétaire ; `STOP_LOSS.md`, `DELEGATION_AUTONOMIE.md`, `config/mandate.v1.yaml` ; actes introduits par les corrections de la revue du 5.10.2026 (jetons, signatures, point zéro, hébergement).
> Ordre : la **checklist chronologique** (§1) d'abord, puis le **détail par catégorie** (§2 à §4). Chaque fiche cite ses tâches du backlog (colonne « Backlog ») : toute tâche de la propriétaire de `BACKLOG.csv` figure ici, à la même échéance (contrôle `check_interventions_backlog` de `outils/verifier_livrables.py`).

## Principe de minimisation

La propriétaire n'intervient que dans trois cas :

- **A. Physique récurrent** : réception, authenticité, colis, photos et vidéos réelles. Un robot logiciel ne prépare pas un colis (BP §12). S'y ajoutent deux gestes personnels : recruter les participants aux entretiens dans son réseau et saisir son temps.
- **B. Légal et identité, une seule fois** : KYC, ouverture de comptes, signatures, statut TVA, et la remise des clés : jetons et empreintes au coffre, hébergement à son nom.
- **C. Validations hors mandat** : décisions au-delà des plafonds, signatures des seuils, point zéro, et réarmement du stop-loss global.

Pour chaque item, les agents ont **déjà préparé** ce qu'ils pouvaient : comparatifs, textes, formulaires pré-remplis, dossiers, commandes prêtes à copier. La propriétaire apporte l'entrée qui lui est propre (identité, signature, présence physique, décision, jeton), rien de plus.

**Fermé par défaut.** Tant qu'un acte de cette liste n'est pas fait, le système reste dans l'état sûr : sans empreinte du mandat au coffre, aucune dépense autonome ; sans signature des seuils, les valeurs les plus strictes ; sans point zéro, la définition littérale du stop-loss global (gel avant la première vente) ; sans jeton propriétaire, aucune hausse de niveau ni aucun réarmement ; sans jetons nommés, toute dépense part en validation humaine.

| Catégorie | Items | Charge totale estimée | Quand |
|---|---|---|---|
| A. Physique récurrent | 11 | ≈ 2 à 6 h/semaine après ouverture, selon le volume (hypothèse : à mesurer, A10) | À partir de S5 (A11 en S1) |
| B. Légal et identité, une fois | 24 | ≈ 14 à 19 h au total (hors délais d'attente), réparties sur S1-S4 | Surtout S1-S2 |
| C. Validations hors mandat | 26 | 10 à 30 min par décision ; ≈ 1 h/semaine en régime | Au fil des gates et des alertes |

> Les **délais** indiqués sont des **estimations** (fourchettes usuelles, non garanties par un prestataire). Ils seront remplacés par les délais réels annoncés par chaque prestataire.

## 1. Checklist chronologique

Cocher dans l'ordre. Un item n'attend que ce qui figure dans « Bloque ». J1 = lundi 5.10.2026 (hypothèse, C01).

| ✓ | Quand | ID | Action | Bloque |
|---|---|---|---|---|
| ☐ | J1 | B01 | Signer le mandat écrit, fixer les plafonds, **reporter son empreinte au coffre** ; activer le niveau 1 | Tout envoi externe et toute dépense des agents |
| ☐ | J1 | B02 | Créer la boîte email dédiée aux agents | Emails fournisseurs (J3) |
| ☐ | J1 | C01 | Valider la date de J1 et les seuils des gates | Calendrier, G0 |
| ☐ | J2 | B03 | Créer le coffre de secrets, déléguer les accès | Comptes outils, Shopify, API |
| ☐ | J2 | B21 | Générer **votre jeton** (propriétaire) et placer son empreinte au coffre | Point zéro, niveaux 2 à 4, réarmement, taux de change |
| ☐ | J2 | B22 | Générer un **jeton nommé** par agent et par workflow ; empreintes au coffre | Toute dépense approuvée sans vous |
| ☐ | J2 | C02 | Valider le dossier B2B (version provisoire) et le panier pilote | Demandes fournisseurs (J3) |
| ☐ | J3 | C03 | Valider le budget pilote et le financement des charges d'avant ouverture | Stop-loss cash |
| ☐ | J3 | C19 | Décider le **point zéro** du stop-loss global (option A recommandée) | Gel global avant la première vente |
| ☐ | J3 | B04 | Créer les comptes outils (formulaire, emailing) | Questionnaire, landing |
| ☐ | J3 | B05 | Ouvrir le PayPal dédié (KYC), verser l'enveloppe | Petits achats des agents |
| ☐ | J3 | C04 | Valider le texte de consentement des entretiens | Entretiens |
| ☐ | J4 | C05 | Autoriser ou non la piste Carletto AG (hors BP) | Contact Carletto |
| ☐ | J5 | B06 | Mandater la fiduciaire | Entité, TVA, IDE |
| ☐ | J7 | C06 | **Valider le nom** de la boutique (une fois) | Domaine, landing, DA |
| ☐ | J7 | B07 | Choisir l'entité exploitante (avec la fiduciaire) | IDE, banque, KYC |
| ☐ | J7 | A11 | Recruter 10 à 15 participants aux entretiens dans votre réseau | Entretiens, G2 |
| ☐ | J7-J14 | A01 | (Option) Conduire des entretiens oraux | Synthèse marché |
| ☐ | J8 | B08 | Acheter le domaine, créer les comptes réseaux sociaux | Landing |
| ☐ | J8 | B12 | Mandater le juriste (avancé : relecture express de la notice de la landing à J9) | C26, C11 |
| ☐ | J9 | C26 | Relecture express de la notice de la landing ; la dater ; choisir les polices ; hébergeur de la landing | C07 |
| ☐ | J10 | C07 | GO publication de la landing | KPI landing |
| ☐ | J10 | B09 | Obtenir ou confirmer l'IDE (inscription RC si requise) | Comptes revendeurs, PSP |
| ☐ | J10 | B10 | Statut TVA : décision écrite, inscription AFC si requise | Prix publics |
| ☐ | J10 | B11 | Créer les comptes revendeurs (KYC fournisseurs) | Devis nets, commande |
| ☐ | J12 | B13 | Faire valider par la fiduciaire les règles TVA et import | Pricing pilote |
| ☐ | J14 | B14 | Ouvrir le compte bancaire professionnel | Paiements, versements |
| ☐ | J14 | C08 | Ajouter le(s) fournisseur(s) à la liste autorisée du mandat | Achats |
| ☐ | J14 | C09 | Valider les règles de prix v1 | Prix publics |
| ☐ | J14 | C20 | **Signer** les seuils du stop-loss et les règles de prix (empreintes au coffre) | Seuils les plus stricts tant que non signés |
| ☐ | J16 | B15 | Créer la boutique Shopify (compte propriétaire) | Site test |
| ☐ | J16 | B24 | Créer la propriété Google Search Console | Mesure SEO |
| ☐ | J20 | C10 | **Valider la direction visuelle et le logo** (une fois) | Charte, thème |
| ☐ | J21 | B16 | Activer Shopify Payments ou un PSP, et TWINT | Tests de paiement |
| ☐ | J21 | B17 | Ouvrir le compte transporteur | Étiquettes, colis test |
| ☐ | J21 | B18 | S'affilier à l'AVS comme indépendante si requis | Conformité sociale |
| ☐ | J26 | B23 | Héberger l'API, n8n et la base (URL HTTPS, sauvegardes testées) | Webhooks, recette, niveau 2 |
| ☐ | J28 | C11 | Valider les textes légaux après relecture du juriste | Ouverture |
| ☐ | J28 | A02 | Envoyer un colis test et un retour test | G3 |
| ☐ | J28 | B19 | Signer l'assurance (RC, stock) | Réception du stock |
| ☐ | J30 | C12 | **Gate G3 : décider l'achat du stock pilote** | Commande |
| ☐ | J30 | C25 | (Si G3 révèle un blocage technique) faire chiffrer un développement externalisé | Décision de poursuivre |
| ☐ | J31 | C13 | Passer et payer la commande fournisseur | Réception |
| ☐ | J35 | A03, A04 | Réceptionner le stock, contrôler l'authenticité | Coût historique, fiches |
| ☐ | J35 | A05 | Aménager le lieu de stockage | Réception |
| ☐ | J37 | A06 | Session photos et vidéos réelles | Fiches, contenus |
| ☐ | J38 | C14 | Activer le niveau 2 (votre jeton ; point zéro posé) ; GO ouverture douce | Ventes |
| ☐ | J38 → | A07 | Préparer et expédier les colis | Livraisons |
| ☐ | J45 | B20 | Créer les comptes publicitaires | Test pub |
| ☐ | J45 | C15 | Gate G4 : GO test pub ; activer le niveau 3 | Campagnes |
| ☐ | J60 / J64 | C16 | Gate G5 : poursuivre ou couper la pub (J60 avec l'option B ; J64 avec l'option A, recommandée) | Budget pub suivant |
| ☐ | J62 → | C17 | Valider les réassorts (jusqu'au niveau 4) | Réassort |
| ☐ | J75 | B11 | Créer le compte du 2e fournisseur (deuxième source active) | Critère 6.5 de G6 |
| ☐ | J85 | C17 | (Option) Activer le niveau 4 | Réassorts automatiques |
| ☐ | J85-J90 | C21 | Renouveler ou clore le mandat avant sa fin de validité | Toute dépense après J90 |
| ☐ | J90 | C22 | Financement du BFR et assujettissement TVA anticipé | Croissance au-delà du pilote |
| ☐ | Hebdo | A10 | Saisir le temps passé (supervision, colis) | Résultat avec valorisation du temps |
| ☐ | Mensuel | A08 | Inventaire physique | Rapprochement stock |
| ☐ | Au besoin | A09, C18 | Retours physiques ; exceptions, litiges, « une personne sur demande », **réarmement du stop-loss global** | Reprise |
| ☐ | Au besoin | C23 | Actes avec votre jeton : taux de change, mémoire des apports, incident critique, révocation | Achat en devise, photo corrigée, reprise |
| ☐ | Au besoin | C24 | Service gelé au démarrage : réparer ou signer, puis redémarrer | Tout |
| ☐ | J_V1 + 60 | C16 | **Gate G7 : poursuivre, ajuster, reporter ou arrêter** | Suite du projet |

## 2. Catégorie A — Physique récurrent

| ID | Action | Pourquoi une personne | Entrée nécessaire | Livrable déjà préparé | Délai / temps estimé | Bloquant pour | Réduction possible | Backlog |
|---|---|---|---|---|---|---|---|---|
| A01 | Entretiens clients oraux (**optionnel**) | Une voix réelle et des relances spontanées ; les agents ne téléphonent pas à des particuliers | 10 à 15 créneaux de 30 min | `docs/01-marche/GUIDE_ENTRETIENS.md`, `QUESTIONNAIRE.md` | 5 à 8 h au total (S2) | G2 (≥ 10 entretiens) | Remplacer tout ou partie par le questionnaire en ligne géré par les agents | BL-026 |
| A02 | Colis test et retour test | Geste physique (emballer, déposer, recevoir) | Un produit factice ou un objet du même format | `docs/07-ops/SOP_PREPARATION_COLIS.md`, `docs/07-ops/SOP_SAV_RETOURS.md` | 1 h, une fois (S4) | G3 (condition « expédition testée ») | — | BL-105 |
| A03 | Réception du stock : comptage, scellés, langue FR, conformité au bon de livraison, dommages, photos de preuve | Contrôle physique de la marchandise (BP §12) | Présence le jour de livraison | `docs/07-ops/SOP_RECEPTION_STOCK.md` ; bon de réception préparé par l'agent 11 | 30 à 60 min par livraison | Coût historique, publication des fiches | Prestataire logistique (devis BL-055), qui doit être piloté | BL-111 |
| A04 | Contrôle d'authenticité de chaque lot | Jugement sur pièce (film, impression, cohérence des scellés) ; responsabilité de la propriétaire | Lot reçu | `docs/02-sourcing/CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md` §4 (points de contrôle), `docs/07-ops/SOP_RECEPTION_STOCK.md` | ≈ 15 min par lot | Mise en vente | Fournisseurs officiels uniquement : moins de lots à risque | BL-112 |
| A05 | Aménager et tenir le lieu de stockage (sec, sûr, étiqueté) | Lieu physique | Un espace dédié | `docs/07-ops/SOP_RECEPTION_STOCK.md` | 1 h une fois, puis 10 min par livraison | Réception | Prestataire logistique | — |
| A06 | Photos et vidéos réelles en session groupée (produits, déballage authentique, coulisses d'expédition) | Pas d'emballage généré par IA pour la marchandise vendue (BP §7, §8) | Produits reçus, 2 à 3 h | `docs/06-contenu/SCRIPTS_VIDEO.md` (scripts et liste de plans) | 2 à 3 h par arrivage (S6, puis à chaque réassort) | Fiches, 3 contenus/semaine | L'IA décline légendes et formats à partir des rushes (BP §8) | BL-114 |
| A07 | Préparer et expédier les colis : picking, scan, emballage, étiquette, dépôt | BP §12 : une personne ou un prestataire assure les contrôles physiques | Commandes du jour (bon de préparation automatique) | `docs/07-ops/SOP_PREPARATION_COLIS.md` ; étiquettes générées par le transporteur | ≈ 10 à 15 min par colis (hypothèse **à mesurer**) | Livraisons, satisfaction | Regrouper les envois sur 2 à 3 jours fixes par semaine ; prestataire logistique | BL-120 |
| A08 | Inventaire physique mensuel | Comptage réel | 1 h par mois | Routine dans `docs/07-ops/ROUTINES_PILOTAGE.md` ; liste de comptage préparée par l'agent 11 à partir du stock du moteur (aucune liste générée automatiquement à ce jour) | 1 h par mois | Rapprochement stock, valorisation | Comptage tournant de 5 références par semaine | BL-167 |
| A09 | Traitement physique des retours (état, remise en stock ou dommage) | Contrôle de l'état | Colis retour | `docs/07-ops/SOP_SAV_RETOURS.md` | ≈ 15 min par retour | Remboursement | — | — |
| A10 | Saisir chaque semaine le temps passé (supervision, colis) | Seule la propriétaire connaît son temps ; base du 2e compte de résultat (BP §3) | 5 min par semaine | Tableau de bord mensuel (`dashboard/`), ligne « temps » ; calcul par l'agent 05 | 5 min par semaine | Résultat avec valorisation du temps, décision G7 | Saisie au fil de l'eau | BL-171 |
| A11 | Recruter 10 à 15 participants aux entretiens dans votre réseau (clubs TCG, connaissances) | Contacts personnels ; les agents n'écrivent pas à des particuliers non inscrits | Liste de contacts, 30 min | `docs/01-marche/GUIDE_ENTRETIENS.md` (message d'invitation et consentement) ; appel diffusé par l'agent 09 | 30 min (S1) | Entretiens (A01), G2 | Questionnaire en ligne seul | BL-025 |

## 3. Catégorie B — Légal et identité, une seule fois

| ID | Action | Pourquoi une personne | Entrée nécessaire | Livrable déjà préparé | Délai estimé | Bloquant pour | Backlog |
|---|---|---|---|---|---|---|---|
| B01 | Signer le mandat écrit d'autonomie et fixer les plafonds ; **reporter son empreinte au coffre** (`POKESHOP_MANDATE_FINGERPRINT`) ; noter le niveau d'autonomie 1 | Seule la propriétaire peut déléguer ; c'est le report au coffre qui vaut signature (un agent sait calculer l'empreinte, pas écrire au coffre) | Plafonds par type de dépense, liste de fournisseurs autorisés ; budget stock du mandat = `stock_budget_chf` des règles de prix | `docs/00-pilotage/DELEGATION_AUTONOMIE.md` §9-§10, `config/mandate.v1.yaml` | 1 h | Tout acte externe des agents (G0) ; sans empreinte au coffre : mandat inactif, 0 CHF | BL-002, BL-006 |
| B02 | Créer la boîte email dédiée aux agents (2FA) | Création de compte au nom de l'entité | Nom de domaine provisoire ou adresse générique | — | 30 min | Envois aux fournisseurs (BL-040) | BL-003 |
| B03 | Créer le coffre de secrets et déléguer les accès minimaux | Détenteur des secrets maîtres (BP §6) | Choix de l'outil | `docs/08-agents/BRIEF_COMMUN.md` §10 (variables, noms seulement) | 30 min | Comptes et API | BL-005 |
| B04 | Créer les comptes outils de base (formulaire, emailing) | Création de compte et conditions d'utilisation acceptées par l'entité | Adresse dédiée | `docs/01-marche/QUESTIONNAIRE.md` | 30 min | Questionnaire, landing | BL-015 |
| B05 | Ouvrir le compte PayPal dédié (KYC) et y verser l'enveloppe | KYC du titulaire | Pièce d'identité, compte bancaire | `DELEGATION_AUTONOMIE.md` (plafonds, checklist §7) | 30 min + 1 à 5 jours ouvrés de vérification | Petits achats des agents (emballages, échantillons) | BL-004 |
| B06 | Mandater la fiduciaire (lettre de mission) | Signature d'un contrat | Choix dans la shortlist | `docs/02-sourcing/TRACKER_CONTACTS.csv` (shortlist), brief dans `DOSSIER_B2B.md` | 30 min + rendez-vous | B07, B09, B10, B13 | BL-009 |
| B07 | Choisir l'entité exploitante (raison individuelle existante ou nouvelle, Sàrl…) | Engage le patrimoine et la fiscalité de la propriétaire | Situation personnelle, autres activités | `docs/03-finance/NOTE_VERIFICATION_BP.md` (seuil TVA, BFR) | 1 rendez-vous | Dossier B2B définitif, KYC | BL-007 |
| B08 | Acheter le nom de domaine, créer les comptes réseaux sociaux de la boutique | Titulaire légal ; vérification d'identité des plateformes | Nom validé (C06) | `docs/05-da/NAMING.md` (3 pistes ; §6 liste les vérifications de domaine, handles, Swissreg, EUIPO et Zefix à faire avant l'achat) | 30 min | Landing, emails pro | BL-030 |
| B09 | Obtenir ou confirmer l'IDE (inscription RC si CA > 100 000 CHF ou volontaire) | Acte d'état civil de l'entreprise | Signature légalisée si RC | Données préparées dans `DOSSIER_B2B.md` | Quelques jours à 2 semaines (selon canton) | Comptes revendeurs, PSP | BL-011 |
| B10 | Statut TVA : décision écrite ; inscription à l'AFC si requise ou choisie | Déclaration fiscale ; l'IA ne décide jamais d'une TVA (BP §4) | Avis de la fiduciaire sur **toute** l'activité de l'entité | `config/pricing_rules.v1.yaml` (2 profils), note finance (seuil de 100 000 CHF) | Décision : 1 rendez-vous ; inscription : à confirmer par la fiduciaire | Prix publics (champs inconnus = brouillon) | BL-010 |
| B11 | Créer les comptes revendeurs chez les fournisseurs (formulaires, KYC, CGV fournisseur), y compris le 2e fournisseur | Identité de l'entreprise, acceptation des conditions | IDE, pièces, coordonnées | `docs/02-sourcing/DOSSIER_B2B.md`, `EMAILS_FOURNISSEURS.md` (réponses), formulaires pré-remplis par l'agent 02 | 20 min par fournisseur + vérification fournisseur (« quelques jours ouvrables » annoncés par CardCosmos, selon l'index) | Devis nets, commande | BL-045, BL-142 |
| B12 | Mandater le juriste (au plus tard à J8) | Signature d'un contrat | Choix entre 2 devis | Brouillons légaux dans `docs/04-legal/`, dont `docs/04-legal/CONFIDENTIALITE_LANDING.md` (notice de la landing) | 30 min | C26 (relecture express, J9), C11 | BL-057 |
| B13 | Faire valider par la fiduciaire les règles TVA et import | Responsabilité fiscale | Rendez-vous | `config/pricing_rules.v1.yaml`, `COMPARATEUR_OFFRES.xlsx` | 1 rendez-vous | Pricing pilote (BL-081) | BL-061 |
| B14 | Ouvrir le compte bancaire professionnel (KYC) | KYC | Pièces de l'entité | Comparatif banques (BL-051) | 1 à 3 semaines | PSP, versements | BL-052 |
| B15 | Créer la boutique Shopify (compte propriétaire, abonnement) | Titulaire du contrat et du moyen de paiement | Carte de l'entité | — | 30 min | Site test | BL-086 |
| B16 | Activer Shopify Payments (ou un PSP) et TWINT | KYC, contrat ; éligibilité TWINT sous conditions (BP §7, [S10]) | IBAN pro, IDE | Comparatif PSP (BL-051) | 30 min + quelques jours de vérification | Tests de paiement (G3) | BL-097 |
| B17 | Ouvrir le compte transporteur | Contrat commercial | Choix sur la base des tarifs écrits | Comparatif transporteurs (BL-053) | 1 à 2 semaines | Étiquettes, colis test | BL-054 |
| B18 | Affiliation AVS comme indépendante si raison individuelle | Obligation personnelle | Avis de la fiduciaire | — | Selon la caisse de compensation | Conformité | BL-012 |
| B19 | Signer l'assurance (RC entreprise, stock) | Contrat | Choix entre 2 devis | Devis (BL-058) | ≈ 1 semaine | Réception du stock | BL-059 |
| B20 | Créer les comptes publicitaires avec un plafond de dépense au niveau du compte | Identité et moyen de paiement | Carte, plafond | `docs/06-contenu/PUBLICITE_TEST.md` (plan de test) | 30 min + vérification | Test pub (G4) | BL-131 |
| B21 | Générer **votre jeton** (32 caractères aléatoires ou plus ; un jeton de moins de 16 caractères est refusé) et placer **seulement son empreinte** au coffre (`POKESHOP_OWNER_TOKEN_SHA256`) | Il porte vos actes réservés : réarmement, point zéro, mémoire des apports, hausse de niveau, taux de change, reprise d'un incident critique. Jamais transmis à un agent ni collé dans un chat | Votre gestionnaire de mots de passe | Commandes prêtes : `docs/00-pilotage/STOP_LOSS.md` §5 (génération, empreinte saisie au clavier) | 10 min | C14, C15, C17, C18, C19, C23 ; sans empreinte : aucun réarmement, aucune hausse de niveau | BL-176 |
| B22 | Générer **un jeton nommé** par agent et par workflow (`agent-NN-<nom>`, `n8n-NN-<workflow>`) et le jeton d'API commun ; empreintes au coffre (`POKESHOP_AGENT_TOKENS_SHA256`, `POKESHOP_API_TOKEN_SHA256`) | L'acteur journalisé est déduit du jeton : une photo de trésorerie ou un solde PayPal déposés par le jeton qui demande la dépense ne sont pas vérifiables | Liste des agents (`docs/08-agents/README.md`) et des workflows (`orchestration/n8n/`) | `.env.example` (format `nom:empreinte`), `docs/08-agents/BRIEF_COMMUN.md` §10 | 20 min | Toute dépense approuvée sans vous (sinon `TREASURY_UNVERIFIED`, validation humaine) | BL-177 |
| B23 | Héberger l'API du moteur, n8n et PostgreSQL au nom de l'entité ; URL HTTPS publique pour n8n (webhooks Shopify, formulaires) ; fichier d'environnement **hors** de l'arborescence des agents ; sauvegardes quotidiennes des journaux d'état et restauration testée ; enregistrer une fois l'empreinte de votre jeton en base (`pokeshop.owner_token_fingerprint`, compte membre de `pokeshop_owner`) | Contrat d'hébergement et moyen de paiement ; garde des secrets d'infrastructure | Choix de l'hébergeur (comparatif préparé par l'agent 07) | `orchestration/README.md` §11 (accès public de n8n), `db/README.md` (rôles, sauvegardes), `docker-compose.yml` | 1 à 2 h + délai de l'hébergeur | Webhooks, recette du parcours, niveau 2 ; sans empreinte en base : hausse de niveau refusée (403) | BL-178 |
| B24 | Créer la propriété Google Search Console du domaine et déléguer la lecture à l'agent 08 | Compte et vérification du domaine au nom de l'entité | Domaine acheté (B08) | `docs/06-contenu/SEO.md` (mesure) | 15 min | Mesure SEO (agent 08) | BL-179 |

**Ce qui n'est pas demandé à la propriétaire :** rechercher et comparer les prestataires, rédiger et envoyer les demandes d'information depuis l'adresse dédiée, relancer, remplir le comparateur, préparer les formulaires et les dossiers, suivre les réponses. Tout cela est fait par les agents dans le mandat.

## 4. Catégorie C — Validations hors mandat et réarmement du stop-loss

| ID | Décision | Pourquoi une personne | Entrée nécessaire | Livrable déjà préparé | Délai de réponse attendu | Bloquant pour | Backlog |
|---|---|---|---|---|---|---|---|
| C01 | Date de J1 et seuils des gates | Engage le calendrier et les critères d'arrêt | Lecture (15 min) | `GATES_GO_NO_GO.md`, `PLAN_90_JOURS.md` | J1 | Tout le plan ; critère 0.5 de G0 | BL-016 |
| C02 | Dossier B2B et panier pilote | Engage l'image de l'entreprise auprès des fournisseurs | Lecture, champs d'identité | `docs/02-sourcing/DOSSIER_B2B.md`, `PANIER_PILOTE.csv` | 24 h | Demandes fournisseurs | BL-036, BL-038 |
| C03 | Budget pilote de 8 000 CHF et financement des charges d'avant ouverture | Argent de la propriétaire | Montant disponible | Note finance (EC-F-06) | J3 | Stop-loss cash | BL-013 |
| C04 | Texte de consentement des entretiens et du questionnaire | Données personnelles | Lecture | `GUIDE_ENTRETIENS.md` §2 | 24 h | Entretiens | BL-024 |
| C05 | Piste Carletto AG (hors BP) | Ajout d'un fournisseur hors liste | Lecture de l'écart EC-01 | `ECARTS_BP.md`, `EMAILS_FOURNISSEURS.md` §7 | J4 | BL-042 | BL-043 |
| C06 | **Nom de la boutique** (une fois) | Identité de marque, risque de marque | Choix entre 3 pistes, après les vérifications de `NAMING.md` §6 (recherches publiques faisables par un agent disposant d'un accès web ; décision humaine) | `docs/05-da/NAMING.md` | J7 | Domaine, landing | BL-029 |
| C07 | Publication de la landing | Première prise de parole publique | Relecture ; relecture express du juriste faite (C26) | `PROTOCOLE_LANDING_TEST.md`, page `site/landing/index.html`, notice `docs/04-legal/CONFIDENTIALITE_LANDING.md` | 24 h | KPI marché | BL-032 |
| C08 | Ajouter un fournisseur à la liste autorisée du mandat (nouvelle version signée, empreinte au coffre) | Engagement commercial | Checklist remplie | `CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md`, `COMPARATEUR_OFFRES.xlsx` | 48 h | Achats | BL-047 |
| C09 | Règles de prix v1, puis tout changement de **valeur** (nouvelle version) | Politique commerciale (BP §5) | Lecture | `config/pricing_rules.v1.yaml` | 48 h | Prix publics | BL-084 |
| C10 | **Direction visuelle et logo** (une fois) | Identité validée une fois (BP §8) | Choix entre 2 directions | `docs/05-da/DIRECTION_A.md`, `DIRECTION_B.md`, `CHARTE.html`, `logo/` | 48 h | Charte, thème | BL-071 |
| C11 | Textes légaux finaux, y compris la durée de conservation des paniers abandonnés (`DUREE_CONSERVATION_PANIER`, proposé : 30 jours) | Responsabilité juridique | Avis du juriste | `docs/04-legal/` (CGV, livraison et retours, confidentialité, mentions, précommandes, cookies) | 48 h | Ouverture | BL-096 |
| C12 | **Achat du stock pilote** (G3) | Engagement de cash au-delà du mandat initial | Fiche G3 (avec les relevés de prix des références de la grille, dont REF-16, REF-17, REF-19 et REF-20) | `GATES_GO_NO_GO.md` G3, `ASSORTIMENT_PILOTE.md`, comparateur | 24 h | Commande | BL-107 |
| C13 | Commande et paiement fournisseur (virement préparé, signé par vous) | Paiement depuis le compte de l'entité | Bon de commande préparé | Comparateur (onglet Synthèse fournisseurs) | 24 h | Réception | BL-110 |
| C14 | Niveau d'autonomie 2 (hausse avec votre jeton) et GO de l'ouverture douce ; vérifier que le point zéro est posé (C19) | Passage de la simulation au réel (BP §13) | Recette OK | Fiche G3, rapports QA | 24 h | Ventes | BL-116, BL-117 |
| C15 | GO du test publicitaire (≤ 500 CHF, plafond jour) et niveau 3 (votre jeton) ; contrat avec un créateur | Dépense marketing, droits d'image | Fiche G4 | `GATES_GO_NO_GO.md` G4 | 24 h | Campagnes | BL-123, BL-132 |
| C16 | Gates G5 (J60 avec l'option B ; J64 avec l'option A, 7 jours complets de données) et G7 (poursuivre, ajuster, reporter, arrêter) ; dossier du stop-loss « temps » ; activités hors périmètre de départ après G7 | Décisions de continuité | Fiche du gate | `GATES_GO_NO_GO.md`, `docs/06-contenu/PUBLICITE_TEST.md` | G5 : 24 h ; G7 : 1 semaine | Suite du projet | BL-136, BL-150, BL-174 |
| C17 | Réassorts (jusqu'au niveau 4) ; niveau 4 optionnel (votre jeton) | Engagement de cash | Proposition chiffrée **enregistrée** par le moteur | Propositions du moteur stock (`engine/pokeshop/stock.py`, `POST /stock/reorder-proposal`) | 24 h (sinon la proposition expire) | Disponibilité | BL-141, BL-146 |
| C18 | Exceptions : allocation rare, dépassement du plafond de 25 % par extension, produit sous plancher, prix > marché + 10 %, variation de prix > 5 % par jour, litige complexe, fraude, geste hors règle, client qui demande qu'**une personne** lui réponde ou réexamine (`docs/07-ops/SOP_SAV_RETOURS.md`, principe 4 bis). **Réarmement du stop-loss global** après un gel : vous lisez `rearm_reference` dans `GET /stoploss/status` et **attestez** la valeur nette (`reference_chf`, `photo_sha256`) dans `POST /stoploss/rearm` avec votre jeton | Hors règles par définition ; seule la propriétaire réarme (modèle d'opération) | Alerte et dossier de l'agent 01 ; votre jeton (B21) | `STOP_LOSS.md` §5 (procédure), `GATES_GO_NO_GO.md` §1, `REGISTRE_RISQUES.md` | Exceptions : 48 h ; dépense hors mandat : 24 h (expiration du workflow 08) ; réarmement : à votre rythme, le gel tient tant que vous n'avez pas décidé | Reprise de l'activité concernée | BL-168, BL-172, BL-173 |
| C19 | **Point zéro** du stop-loss global : décider l'option à J3 avec le budget (option A recommandée : référence 4 200 CHF, seuil 840 CHF), puis le poser (`POST /stoploss/baseline` avec votre jeton, après le dépôt d'une première photo) dès la mise en service de l'API, avant toute dépense autonome et au plus tard avant C14 | Sans lui, la définition littérale gèle tout dès 1 600 CHF de coûts de lancement non récupérables, avant la première vente | Décision C03 ; jeton (B21) ; API hébergée (B23) | `STOP_LOSS.md` §5 (options A et B, commande prête) | J3 (décision) | Lancement sans gel automatique ; C14 | BL-180 |
| C20 | **Signer** les seuils du stop-loss (`python -m pokeshop.stoploss fingerprint`) et les règles de prix (`rules-fingerprint`) : empreintes au coffre (`POKESHOP_STOPLOSS_FINGERPRINT`, `POKESHOP_RULES_FINGERPRINT`) ; garder le budget stock du mandat égal à celui des règles ; signer à nouveau après toute modification | Seule la propriétaire fixe un seuil ; un fichier modifié par un agent sans signature ne peut que durcir les seuils, une empreinte différente gèle le service | Seuils validés (STOP_LOSS.md, C09) | `STOP_LOSS.md` §1 et validation, `DELEGATION_AUTONOMIE.md` §10 étape 5 | J14 (avec C09) | Sans signature : seuils les plus stricts ; dossier G3 (critère 3.6) | BL-181 |
| C21 | Renouveler ou clore le mandat avant `valid_until` (fin du pilote, J90) : nouvelle version signée, nouvelle empreinte au coffre | Seule la propriétaire délègue ; un mandat expiré coupe toute dépense autonome | Bilan G6 | `DELEGATION_AUTONOMIE.md` §9-§10, `config/mandate.v1.yaml` | J85-J90 | Toute dépense des agents après J90 | BL-182 |
| C22 | Financement du besoin en fonds de roulement ; examen de l'assujettissement TVA anticipé si la trajectoire approche 100 000 CHF | Argent et fiscalité de la propriétaire | Bilan G6, avis de la fiduciaire | `docs/03-finance/NOTE_VERIFICATION_BP.md` (BFR, seuil TVA) | J90 | Croissance au-delà du pilote | BL-148, BL-149 |
| C23 | Actes au fil de l'eau avec votre jeton : taux de change de référence avant un achat en devise (`POST /fx/rates`, source officielle datée) ; réinitialisation de la mémoire des apports après un apport erroné (`POST /stoploss/capital-memory/reset`) ; attestation d'un test ou reprise d'un incident critique ; révocation du mandat (vider l'empreinte du coffre ou `POST /mandate/revoke`) | Chiffres décisifs : jamais auto-déclarés par l'agent qui en bénéficie | Votre jeton (B21) | `DELEGATION_AUTONOMIE.md` §7 et §10, `STOP_LOSS.md` §3 | Achat en devise : 24 h (sinon validation humaine) ; autres : à votre rythme | Achat en devise, photo corrigée, reprise d'un workflow | BL-183 |
| C24 | Service gelé au démarrage : journal d'état illisible (`RESTORE_FAILED`, visible dans `/health`) → réparer ou restaurer le stockage (table `pokeshop.engine_state_journal` ou dossier `POKESHOP_STATE_DIR`) ; configuration modifiée sans signature ou incohérente (`CONFIG_UNSIGNED`) → signer (C20) ou corriger ; puis redémarrer | Aucun réarmement n'est possible dans ces deux cas : seule une intervention sur l'infrastructure ou une signature le lève | Sauvegardes (B23) | `STOP_LOSS.md` §5 « Persistance », `db/README.md` | À votre rythme ; le gel tient | Tout | — |
| C25 | Faire chiffrer un développement externalisé (intégration Shopify et n8n), exigé par le BP §3 « avant décision », si le gate G3 révèle un blocage technique (écart EC-23) | Engagement de budget hors enveloppe | Fiche G3 | `ECARTS_BP.md` EC-23 ; demande de devis préparée par l'agent 02 | J30 (si blocage) | Décision de poursuivre au-delà de G3 | BL-184 |
| C26 | Relecture express de la notice de la landing par le juriste (notes N1 à N6), datation (`DATE_VERSION_LANDING`), choix Google Fonts ou polices du système (`ST_POLICES`, `ST_POLICES_PAYS`, cohérents avec `--sans-google-fonts`), hébergeur de la landing (`ST_HEBERGEMENT_LANDING`, avec l'agent 12) | Responsabilité juridique avant la première collecte de données | Juriste mandaté (B12) | `docs/04-legal/CONFIDENTIALITE_LANDING.md`, `docs/04-legal/champs_a_remplir.yaml` | J9 | C07 (publication de la landing) | BL-185 |

## Validation humaine requise

- [ ] Relire cette liste et signaler tout item qu'elle souhaite **déléguer** davantage (par exemple via un prestataire logistique pour A03 à A09).
- [ ] Confirmer les délais de réponse attendus en catégorie C : au-delà, la proposition expire et l'agent 01 relance ; une dépense hors mandat expire à 24 h.
- [ ] Bloquer dans son agenda les jalons physiques et légaux : S1-S2 (B01 à B14, B21, B22, C19), S4 (B23), S5-S6 (A03 à A06), et les jours d'expédition.
- [ ] Ranger le jeton propriétaire (B21) dans un gestionnaire de mots de passe et ne jamais le transmettre à un agent ni à un workflow.
- [ ] Choisir l'option du point zéro (C19 : A recommandée, ou B) avec la décision de budget (C03).
- [ ] Désigner une personne de remplacement pour la catégorie A en cas d'absence (fêtes de fin d'année notamment), ou accepter une suspension des expéditions annoncée à l'avance.
