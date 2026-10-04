# Registre des risques — {{NOM_BOUTIQUE}}

> Mis à jour chaque lundi par l'agent 01 (BL-163) et présenté à la revue des exceptions (BL-162).
> Sources : BP du 4.10.2026 (§1 à §13), note finance (`docs/03-finance/NOTE_VERIFICATION_BP.md`), écarts (`ECARTS_BP.md`), recherches publiques du 4.10.2026.
> Lien avec les stop-loss : quand un risque a un stop-loss associé, c'est le **stop-loss** qui agit automatiquement. Le registre sert à **anticiper**, pas à remplacer les coupures (`STOP_LOSS.md`, agent gouvernance).

## Échelles

| Probabilité | Sens |
|---|---|
| F (faible) | Peu plausible sur 90 jours |
| M (moyenne) | Plausible |
| E (élevée) | Attendu sans mesure particulière |

| Impact | Sens (sur l'étoile polaire ou le calendrier) |
|---|---|
| 1 Faible | < 100 CHF ou < 3 jours de retard |
| 2 Moyen | 100 à 500 CHF ou 1 à 2 semaines de retard |
| 3 Élevé | 500 à 1 600 CHF, ou gate en REPORT |
| 4 Critique | ≥ 1 600 CHF (seuil du stop-loss global), ou arrêt du projet, ou atteinte à la réputation ou au droit |

Score = probabilité (F = 1, M = 2, E = 3) × impact. **Score ≥ 6** : suivi chaque semaine en revue des exceptions.

## Registre

| ID | Risque | P | I | Score | Mitigation (préventive) | Déclencheur mesurable | Réaction si déclenché | Stop-loss lié | Pilote |
|---|---|---|---|---|---|---|---|---|---|
| R01 | Aucun fournisseur FR n'accepte une entreprise suisse ou n'exporte en Suisse | M | 4 | 8 | 5 sources du BP contactées en même temps (J3-J4) ; piste Carletto (EC-01) ; dossier B2B professionnel | 0 réponse positive écrite à J15 | G2 en REPORT ; appel téléphonique de la propriétaire ; nouvelles sources ; STOP proposé à J29 | Temps | A-02 |
| R02 | Distributeur suisse (Carletto) : les concurrents suisses achètent sans frais d'import et vendent moins cher | M | 3 | 6 | Mesurer l'écart dans le comparateur (coût rendu contre référence marché) ; interroger Carletto | > 50 % des références à prix plancher > marché + 10 % | REPORT au sens du BP §13 ; sourcing suisse | Produit | A-02, A-05 |
| R03 | Pas de flux automatisable : seulement un portail navigateur | E | 2 | 6 | Volet technique dans chaque email ; demande d'un exemple de fichier ; « un portail n'est pas une API » | Aucun fichier ni documentation d'API à J14 | Import assisté (BP §6, priorité 3) ; niveau d'autonomie limité à 2 | — | A-03 |
| R04 | Aucune allocation sur Règne Delta (6.11) pour un nouveau compte | E | 2 | 6 | Assortiment pilote indépendant de la nouveauté ; aucune précommande sans allocation ferme | Allocation = 0 ou non confirmée par écrit à J30 | Fiche en « alerte réassort » ; communication honnête | — | A-02 |
| R05 | Survente (stock simultané, synchronisation, stock fournisseur publié) | F | 4 | 4 | Shopify autorité de vente ; vendable = stock local seulement ; 20 synchronisations sans erreur critique ; test de dernière unité | ≥ 1 commande non couverte | Quarantaine, retour au niveau précédent, remboursement et excuse, analyse | Global (si pertes) | A-12 |
| R06 | Produit contrefait ou non conforme dans un lot | F | 4 | 4 | Fournisseurs officiels ou due diligence ; contrôle d'authenticité à chaque lot (A04) | Scellé ou impression suspects | Lot en quarantaine ; réclamation fournisseur ; aucun produit vendu | Produit | H, A-02 |
| R07 | Erreur de langue ou de contenu (FR/EN/JP de même nom, bundle différent) | M | 3 | 6 | Clé d'identité GTIN + langue + extension + format + contenu ; identité ambiguë = brouillon | Langue ou contenu non confirmés par le fournisseur | Fiche en brouillon ; contrôle à réception | Produit | A-04 |
| R08 | Statut TVA mal établi ou mal paramétré | M | 3 | 6 | Décision écrite de la fiduciaire (B10) ; profils versionnés ; examen de toute l'activité de l'entité | Pas de décision à J14 | Aucun nouveau prix public (champ inconnu = brouillon) | — | A-05, H |
| R09 | Réserve de trésorerie entamée avant le test pub (charges d'avant ouverture non budgétées, EC-F-06) | E | 3 | 9 | Financer ces charges hors réserve (C03) ; trésorerie 13 semaines chaque lundi | Cash disponible prévu < 1 600 CHF sur une semaine à venir | Achats et pub bloqués ; arbitrage de la propriétaire | Cash | A-05 |
| R10 | BFR du scénario central non finançable (≈ 11 239 CHF contre 4 600 mobilisables, délais FICTIFS) | E | 2 | 6 | Rester au volume pilote tant que le financement n'est pas décidé (BL-149) ; négocier un paiement à terme | Ventes > rythme finançable par la trésorerie | Plafond de croissance ; plus de réassort au-delà du cash | Cash | A-05 |
| R11 | Le rythme du pilote (≈ 15 commandes/mois) est déficitaire par construction et mène au gel global vers la semaine 28 | M | 3 | 6 | Viser ≥ 31 commandes/mois après le test (G7, critère 7.10) | Contribution nette hebdomadaire négative 4 semaines de suite | Dossier « ajuster » ; leviers nommés | Global, Temps | A-01 |
| R12 | CAC supérieur à la contribution (hausse des enchères au Black Friday, créations faibles) | M | 2 | 4 | Plafond jour ; démarrage après le 30.11 ou plafond réduit ; 2 à 3 créations testées | CAC (7 j) > contribution − 8 CHF | Plafond réduit, puis coupure | Pub | A-10 |
| R13 | Retards de KYC (banque, PSP, fournisseurs, RC) qui décalent le chemin critique | E | 2 | 6 | Lancer B09, B11, B14 et B16 dès J10 ; PSP de repli ; checklist des pièces prête | Un compte non ouvert 7 jours avant le gate qui l'exige | Re-planification ; G3 en REPORT | Temps | H, A-01 |
| R14 | Saisonnalité : stock reçu après le pic, ruptures à Noël, délais fournisseurs allongés | M | 2 | 4 | Commande à J30 au plus tard ; dates limites d'expédition affichées ; réassort anticipé dès S9 | Délai fournisseur > 10 jours ouvrés | Communication des délais réels ; pas de promesse | Extension | A-11 |
| R15 | Usage abusif de la marque Pokémon (logo, personnages, impression d'un statut officiel) | F | 4 | 4 | DA sans personnages ni symboles ; relecture juriste ; « Pokémon » seulement pour désigner les produits | Visuel ou texte non conforme détecté en QA | Retrait immédiat, correction | — | A-06, A-12 |
| R16 | Droits sur les images et textes fournisseurs non obtenus | M | 2 | 4 | Demande écrite dans chaque email (BL-093) | Pas d'accord écrit à la publication | Photos propres (A06) | — | A-02 |
| R17 | Fuite de coûts, marges ou données personnelles (HTML, payloads, prompts) | F | 4 | 4 | Filtre strict des champs publics + test qui échoue en cas de fuite ; vue `public_catalog` sans coûts | Test de fuite rouge ou signalement | Dépublication, correction, revue | — | A-12 |
| R18 | Dépendance à une seule source | M | 3 | 6 | 2e source identifiée avant G3 et active en S7-S12 (BP §13) | Fournisseur principal en rupture ou qui coupe le compte | Bascule sur la 2e source ; achats suspendus | — | A-02 |
| R19 | Temps de la propriétaire sous-estimé (supervision et colis) | E | 2 | 6 | Mesurer le temps (BL-171) ; jours d'expédition fixes ; devis logistique | > 10 h/semaine 2 semaines de suite | Prestataire logistique ou baisse du rythme | — | H, A-05 |
| R20 | Un agent sort du mandat (engagement non autorisé, envoi non sollicité, dépense hors plafond) | F | 3 | 3 | Mandat écrit, plafonds PayPal, journal append-only, niveau 1 par défaut, revue hebdomadaire | Écriture hors plafond ou hors liste dans le journal | Gel de l'agent concerné, retour au niveau 1, revue | Global | GOV, A-12 |
| R21 | Baisse du prix de marché (réimpression, déstockage) sous le coût du stock détenu | M | 2 | 4 | Plafond de 25 % par extension ; rotation suivie ; pas d'achat « spéculatif » sur allocation rare à faible marge (BP §1) | Référence marché en baisse de > 10 % sur une extension en stock | Proposition de démarque ; plus de réassort | Extension, Produit | A-05 |
| R22 | Colis perdu ou abîmé | M | 1 | 2 | Suivi systématique ; emballage protecteur ; provision SAV R | Réclamation | Remplacement ou remboursement selon les CGV ; réclamation au transporteur | — | A-11 |
| R23 | Non-conformité données personnelles (consentements, désinscription) | F | 3 | 3 | Double opt-in ; désinscription propagée (BL-103) ; pas de SMS ni d'email non sollicités | Test de désinscription en échec | Correction avant tout nouvel envoi | — | A-12 |
| R24 | Flux amont en panne ou donnée > 24 h | M | 1 | 2 | Alerte de flux ; blocage voulu des achats et promesses (BP §5) | Donnée > 24 h | Achats et promesses bloqués ; le stock local se vend normalement | — | A-03 |
| R25 | Pression concurrentielle (boutiques spécialisées romandes, boutique physique à Genève, généralistes) | E | 2 | 6 | Différenciation sur la confiance, la sélection et le service (BP §1) ; relevé hebdomadaire des références pilotes | Médiane du marché < notre prix plancher sur une référence | Statut « À REVOIR » ; pas de baisse de marge automatique | Produit | A-02 |
| R26 | URL et contacts du BP non vérifiés à la source (accès web bloqué pendant le build, EC-05) | E | 1 | 3 | Re-vérification BL-021 avant le premier envoi | URL ou adresse invalide au moment de l'envoi | Correction du tracker ; canal de repli (formulaire) | — | A-02 |
| R27 | Fraude au paiement ou rétrofacturation sur des produits recherchés | M | 2 | 4 | 3-D Secure ; contrôle des anomalies (doublons, adresses) ; quantité maximale par client | Rétrofacturation ou commande suspecte | Commande retenue, escalade C18 | — | A-11 |
| R28 | Revendeurs qui vident le stock d'une nouveauté (achats massifs) | M | 1 | 2 | Quantité autorisée par client sur les nouveautés (BP §7) | > 2 unités d'une même nouveauté par foyer | Annulation selon les CGV | — | A-11 |
| R29 | Délais administratifs RC/IDE/TVA plus longs que prévu | M | 2 | 4 | Démarches lancées dès J7 ; dossier B2B en version provisoire « IDE en cours » | IDE non reçu à J14 | Comptes revendeurs différés ; plan recalé | Temps | H |
| R30 | Le BP se fonde sur des hypothèses (marges, CAC, panier) non vérifiées par des devis | E | 2 | 6 | Remplacer chaque hypothèse par un devis ou une facture avant tout achat significatif (BP §14) | Écart facture/estimation > 2 % | Recalcul de la contribution réalisée ; règles ajustées | Produit | A-05 |

## Top 5 à suivre cette semaine (S1)

1. **R09** : réserve de trésorerie, décision C03 attendue à J3.
2. **R01** : acceptation d'une entreprise suisse ; envois J3-J4, relances J8 et J15.
3. **R13 / R29** : délais KYC et IDE ; démarches à lancer en S1-S2.
4. **R02** : position concurrentielle d'un distributeur suisse ; décision C05 sur Carletto.
5. **R03** : flux automatisable ; exemple de fichier demandé dans chaque email.

## Historique des revues

| Date | Changements | Par |
|---|---|---|
| 4.10.2026 | Création (30 risques) | Agent pilotage-marche-sourcing (build) |

## Validation humaine requise

- [ ] Relire les probabilités et impacts des risques de score ≥ 6 et corriger ceux qui ne correspondent pas à sa situation (temps disponible, apport possible).
- [ ] Décider des mesures qui exigent de l'argent ou un engagement : financement des charges d'avant ouverture (R09), BFR (R10), prestataire logistique (R19).
- [ ] Confirmer le seuil de « 10 h par semaine » qui déclenche R19.
