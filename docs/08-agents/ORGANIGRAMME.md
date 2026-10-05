# Organigramme de la flotte — dépendances, exceptions, RACI

> Déclinaison du BP §11 (« Ordre des dépendances », tableau des 12 rôles) et §12 (workflows), avec le modèle d'opération de la propriétaire. Règles communes : `docs/08-agents/BRIEF_COMMUN.md`. Autonomie : `docs/08-agents/MATRICE_AUTONOMIE.md`.
> Notation : **P** = propriétaire (« la responsable » du BP) ; **A-01 à A-12** = agents du BP §11 (même numérotation que `docs/00-pilotage/PLAN_90_JOURS.md`). Les identifiants A01-A09, B01-B20 et C01-C18 désignent les **interventions humaines** de `docs/00-pilotage/INTERVENTIONS_HUMAINES.md`.

## 1. Vue d'ensemble

```
                         ┌──────────────────────────────────────────┐
                         │ PROPRIÉTAIRE (P)                          │
                         │ A physique · B légal une fois ·           │
                         │ C validations hors mandat + réarmement    │
                         └───────────────▲──────────────────────────┘
               E2 (24 ou 48 h) / E3 (immédiat) │  décisions journalisées
                         ┌───────────────┴──────────────────────────┐
                         │ A-01 CHEF DE PROJET                       │
                         │ backlog · dispatch · boîte dédiée ·       │
                         │ revue des exceptions · fiches de gate     │
                         └──┬───────────┬───────────┬────────────┬──┘
          ┌─────────────────┘           │           │            └──────────────────┐
  ┌───────▼────────┐   ┌────────────────▼───┐  ┌────▼────────────────┐   ┌──────────▼─────────┐
  │ AMONT          │   │ CŒUR CHIFFRÉ       │  │ VITRINE             │   │ AVAL               │
  │ A-02 Sourcing  │──▶│ A-04 Catalogue     │─▶│ A-07 Site & intégr. │──▶│ A-11 Opérations/SAV│
  │ A-03 Données   │   │ A-05 Finance &     │  │ A-08 SEO & rédaction│   │ A-10 Acquisition   │
  │   fournisseurs │   │   pricing (mandat, │  │ A-06 DA             │   │ A-09 Communication │
  │                │   │   étoile polaire)  │  │                     │   │                    │
  └────────────────┘   └────────────────────┘  └─────────────────────┘   └────────────────────┘
          ▲                      ▲                        ▲                         ▲
          └──────────────────────┴──── A-12 QA ET CONFORMITÉ ────────────────────────┘
                     tests · surveillance · stop-loss (peut geler, jamais réarmer)
```

## 2. Ordre des dépendances (BP §11) et gates

| Étape | BP | Agents responsables | Entrées | Sorties | Contrôlé au gate |
|---|---|---|---|---|---|
| 0. Cadre | Modèle d'opération, §13 | P, A-01 | Mandat préparé (agent gouvernance) | Mandat signé, boîte dédiée, coffre, niveau 1 | G0 (J1) |
| 1. Sourcing + cadre fiscal | §2, §4 | A-02, A-05 (+ fiduciaire) | `docs/02-sourcing/PANIER_PILOTE.csv`, `docs/02-sourcing/DOSSIER_B2B.md`, `config/pricing_rules.v1.yaml` | Demandes envoyées, devis, conditions d'export, profil TVA | G1 (J7), G2 (J15) |
| 2. Données fiables | §6 | A-03 | Exemple de fichier réel, devis | Dictionnaire de champs, import daté, quarantaine | G2 (critère 2.3) |
| 3. Catalogue et coûts | §4, §6 | A-04, A-05 | Offres importées | Identité produit, coût rendu, coût de remplacement | G2 (2.4, 2.5) |
| 4. Prix et stock | §5 | A-05, A-11 | Coût rendu, règles versionnées, référence marché | Décisions de prix, stock vendable, quotas de précommande | G3 (3.3, 3.5) |
| 5. Site | §7 | A-07, A-08, A-04 | Catalogue validé, composants DA | Fiches, checkout, 20 synchronisations sans erreur critique | G3 (3.4, 3.6, 3.7) |
| En parallèle dès J1 | §11 | A-06 | BP §8 | Naming, directions, charte | C06, C10 |
| Publication marketing | §11 | A-09, A-10 | Stock reçu **ou** allocation ferme ; composants approuvés | Contenus, emails, campagnes | G4 (J45), G5 (J60) |
| Transverse | §11 | A-12 | Tous les livrables | Tests, recette, surveillance, gel | Tous |
| Pilotage | §11 | A-01 | Rapports, exceptions | Fiches de gate, arbitrages | Tous ; G6, G7 |

**Règle de blocage :** une étape ne consomme que des sorties au statut `VALIDÉ` (`BRIEF_COMMUN.md` §5). Une sortie `BROUILLON`, `QUARANTAINE` ou `BLOQUÉ` n'alimente pas l'étape suivante.

## 3. Flux des exceptions

```
 Agent (n'importe lequel)                 Moteur / stop-loss
   │ déclencheur (brief §9)                 │ seuil franchi
   ▼                                        ▼
 Fiche EXC dans docs/08-agents/exceptions/  A-12 GÈLE (E3) : quarantaine,
   │ niveau proposé E1/E2/E3                suspension de workflow,
   ▼                                        rétrogradation du niveau
 A-01 TRIE (revue quotidienne, ou immédiat si E3)
   ├── E1 : dans le mandat → A-01 tranche, consigne, renvoie à l'agent
   ├── E2 : hors mandat → dossier de décision (options, chiffres A-05, risques A-12)
   │        → P décide sous 24 h (gate, dépense hors mandat) ou 48 h → sinon STATU QUO SÛR
   └── E3 : alerte immédiate à P (canal d'alerte du mandat) ; le gel tient
   ▼
 Décision journalisée dans la fiche (qui, quand, quoi, conditions)
   ▼
 Agent exécute (si niveau + mandat + stop-loss le permettent) → test A-12 → reprise
```

| Étape | Qui | Délai | Sortie |
|---|---|---|---|
| Ouverture de la fiche | Agent qui constate | Dès le constat | `EXC-AAAAMMJJ-NN` au statut `OUVERTE` |
| Gel conservatoire (E3) | A-12 (ou moteur) | Immédiat | Incident + gel journalisé |
| Triage | A-01 | Revue quotidienne ; immédiat pour E3 | Niveau confirmé, destinataire, échéance |
| Dossier de décision (E2) | A-01, chiffres A-05, risques A-12 | 24 h après triage | Options A/B/C chiffrées par le moteur, recommandation, effet sur l'étoile polaire |
| Décision | P | 24 h pour un gate ou toute dépense hors mandat (le workflow 08 fait expirer la demande) ; 48 h sinon | `APPROUVÉ` / `APPROUVÉ SOUS CONDITIONS` / `REFUSÉ` / `REPORTÉ` |
| Exécution et vérification | Agent concerné, puis A-12 | Selon la décision | Rapport, test, fiche `CLOSE` |

**Statu quo sûr :** sans décision dans le délai, rien n'est engagé, rien n'est publié, la proposition expire ; A-01 relance une fois et l'inscrit à la revue hebdomadaire (BL-162).

## 4. Tableau RACI agents × livrables

R = réalise · **A** = valide et répond du résultat (un seul par ligne) · C = consulté avant · I = informé après. « A/R » : la même partie réalise et valide.

| # | Livrable | BP | P | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L01 | Plan 90 jours, backlog, échéances | §9, §13 | A | R | C |  |  | C |  |  |  |  |  |  | C |
| L02 | Plan de dispatch et revue quotidienne | §11 | I | A/R |  |  |  |  |  |  |  |  |  |  | C |
| L03 | Revue hebdomadaire des exceptions | §11, §12 | A | R |  |  |  | C |  |  |  |  |  |  | C |
| L04 | Fiches de gate G0 à G7 | §13 | A | R |  |  |  | C |  |  |  |  |  |  | C |
| L05 | Registre des risques et des écarts BP | §11 | A | R |  |  |  | C |  |  |  |  |  |  | C |
| L06 | Dossier stop-loss « temps » (continuer, ajuster, arrêter) | §13 | A | R |  |  |  | C |  |  |  |  |  |  | C |
| L07 | Catalogue des modèles d'emails approuvés | §2 | A | R | C |  |  |  |  |  |  | C |  | C | C |
| L08 | Boîte dédiée : tri, brouillons, envoi des modèles approuvés | §2 | I | A/R | C |  |  |  |  |  |  |  |  |  | C |
| L09 | Activation ou rétrogradation d'un niveau d'autonomie | §13 | A | R |  |  |  | C |  | C |  |  |  |  | C |
| L10 | Ajout d'un fournisseur au mandat, changement de plafond | §2 | A | R | C |  |  | C |  |  |  |  |  |  | C |
| L11 | Dossier B2B | §2, §13 | A | C | R |  |  | C |  |  |  |  |  |  |  |
| L12 | Demandes, relances, négociation non engageante | §2 | I | A/R | R |  |  | C |  |  |  |  |  |  |  |
| L13 | Tracker des contacts | §2 |  | A | R |  |  |  |  |  |  |  |  |  | I |
| L14 | Due diligence fournisseur | §2 | A |  | R | C |  | C |  |  |  |  |  |  | C |
| L15 | Comparaison des offres, note de choix des sources | §2, §13 | A | C | R | C |  | C |  |  |  |  |  |  |  |
| L16 | Autorisation de réutiliser textes et images | §2, §7 | I |  | R |  | C |  | C |  | C |  |  |  | A |
| L17 | Dictionnaire de champs par fournisseur | §2, §6 |  |  | C | R | C |  |  |  |  |  |  |  | A |
| L18 | Connecteurs, imports, historique des imports | §6, §12 |  | I |  | R |  | C |  | C |  |  |  |  | A |
| L19 | Quarantaine et incidents de flux | §12 | I | A |  | R | C | C |  |  |  |  |  |  | C |
| L20 | Normalisation SKU, GTIN, langue, format, contenu | §6 |  |  |  | C | R |  |  |  |  |  |  |  | A |
| L21 | Règle de catégorie (1re publication d'une catégorie) | §6 | A |  |  |  | R | C |  |  | C |  |  |  | C |
| L22 | Fiches produit conformes suivantes | §6, §7 |  |  |  |  | R | C |  |  | C |  |  |  | A |
| L23 | Règles de prix et paramètres fiscaux (versions) | §4, §5 | A |  |  |  |  | R |  |  |  |  |  |  | C |
| L24 | Coût rendu, prix plancher, décision de prix | §4, §5 | I |  |  |  | I | A/R |  |  |  |  |  |  | C |
| L25 | Coût historique (réception, facture, justificatif d'import) | §4, §12 |  |  |  |  |  | A/R |  |  |  |  |  | C | C |
| L26 | Trésorerie 13 semaines | §3 | A | C |  |  |  | R |  |  |  |  |  |  |  |
| L27 | Étoile polaire hebdomadaire | Modèle d'opération | A | C |  |  |  | R |  |  |  |  |  |  | C |
| L28 | Registre du mandat (dépenses contre plafonds) | Modèle d'opération | A | I |  |  |  | R |  |  |  |  |  |  | C |
| L29 | Paiements dans le mandat (PayPal) | Modèle d'opération | I | I |  |  |  | A/R |  |  |  |  |  |  | C |
| L30 | Rapprochements paiements, remboursements, versements | §12 | I |  |  |  |  | R |  |  |  |  |  |  | A |
| L31 | Naming (3 pistes) | §8 | A |  |  |  |  |  | R |  |  |  |  |  | C |
| L32 | Directions visuelles, logo, charte | §8 | A |  |  |  |  |  | R | C |  | C |  |  |  |
| L33 | Composants et templates dans la charte validée | §8 |  | A |  |  |  |  | R | C |  | C |  |  | C |
| L34 | Packaging chiffré au coût réel | §8 | A |  |  |  |  | C | R |  |  |  |  | C |  |
| L35 | Thème, collections, pages, checkout | §7 | A |  |  |  |  |  | C | R | C |  |  |  | C |
| L36 | Client Shopify et publication filtrée | §6 |  |  |  |  | C | C |  | R |  |  |  |  | A |
| L37 | API moteur, workflows n8n, passerelles mail et paiement | §6, §12 |  |  |  | C |  | C |  | R |  |  |  | C | A |
| L38 | Tableau de bord interne | §12 | I | A |  |  |  | C |  | R |  |  |  |  | C |
| L39 | Landing (présentation + alertes) | §1 | A |  |  |  |  |  | C | R |  | C |  |  | C |
| L40 | Textes de fiches, catégories, métadonnées | §7 |  |  |  |  | A |  |  |  | R |  |  |  | C |
| L41 | Guides et pages d'extension | §8, §9 |  | A |  |  |  |  |  |  | R | C |  |  | C |
| L42 | Calendrier éditorial et ton | §8, §9 | A |  |  |  |  |  | C |  | C | R | C |  |  |
| L43 | Publications et déclinaisons (prix et stock contrôlés) | §9 | I | A |  |  | C |  | C |  |  | R |  |  | C |
| L44 | Emails transactionnels et automatisations (textes) | §9 | A |  |  |  |  |  | C | C |  | R |  | C | C |
| L45 | Alertes de réassort et récapitulatif hebdomadaire | §9 |  | A |  |  |  |  |  |  |  | R |  | C | C |
| L46 | Plan du test publicitaire | §9 | A | C |  |  |  | C | C |  |  | C | R |  |  |
| L47 | Exécution et coupure des campagnes | §9 | I | I |  |  |  | C |  |  |  |  | A/R |  | C |
| L48 | Bilan CAC | §9 | A |  |  |  |  | C |  |  |  |  | R |  | C |
| L49 | Collaboration avec un créateur TCG | §9 | A |  | C |  |  | C |  |  |  | C | R |  |  |
| L50 | SOP réception, colis, SAV, retours, incidents | §12 | A |  |  |  |  | C |  |  |  |  |  | R | C |
| L51 | Traitement des commandes (réservation, bon, étiquette, suivi) | §12 | I |  |  |  |  |  |  | C |  |  |  | A/R | C |
| L52 | SAV de niveau 1 (FAQ, suivi) | §11 |  | I |  |  |  |  |  |  |  | C |  | A/R |  |
| L53 | Litiges, fraude, gestes hors règle | §11 | A | C |  |  |  | C |  |  |  |  |  | R | C |
| L54 | Propositions de réassort | §5 | A |  | C |  |  | C |  |  |  |  |  | R | C |
| L55 | Achat d'emballages et de matériel | §3 | I |  |  |  |  | A | C |  |  |  |  | R |  |
| L56 | Tests du moteur et non-régression | §13 |  |  |  |  |  | C |  | C |  |  |  |  | A/R |
| L57 | Recette du parcours et 20 synchronisations | §7, §13 | A |  |  |  |  |  |  | C |  |  |  | C | R |
| L58 | Surveillance des stop-loss et gel | Modèle d'opération | I | I |  |  |  | C |  |  |  |  | C |  | A/R |
| L59 | Réarmement du stop-loss global | Modèle d'opération | A/R | I |  |  |  | C |  |  |  |  |  |  | C |
| L60 | Sauvegardes, restauration, accès, journal | §6 | I |  |  |  |  |  |  | C |  |  |  |  | A/R |
| L61 | Conformité : consentements, données, brouillons légaux | §7 | A |  |  |  |  |  |  | C |  | C |  |  | R |

Lecture rapide de la charge de la propriétaire : elle est **A** sur 32 lignes. Douze sont des validations **faites une seule fois** (dossier B2B L11, nom et DA L31-L32, packaging L34, thème et landing L35, L39, SOP L50, textes L44, calendrier et ton L42, règles v1 L23, première règle de catégorie L21, conformité L61). Le reste porte sur l'argent (L26 à L28, L46, L48, L49, L54), le cadre (L01, L03 à L07, L09, L10, L14, L15, L57) et le risque (L53, L59). Tout le reste est validé par A-01 (intra-mandat) ou A-12 (contrôle).

## 5. Passations entre agents

| De | Vers | Artefact transmis | Condition de passage |
|---|---|---|---|
| A-02 | A-03 | Fichier ou tarif reçu, date et canal de réception | Pièce archivée hors dépôt (`$POKESHOP_DOCS_PRIVES`), référence dans le tracker |
| A-02 | A-05 | Devis structuré (lignes, conditions, frais, devise) | Chaque montant a une source datée ; inconnus marqués « inconnu » |
| A-03 | A-04 | Offres importées hors quarantaine | Import complet, devise et HT/TTC connus, < 24 h |
| A-04 | A-05 | Produits à identité confirmée | Clé GTIN + langue + extension + format + contenu + état complète |
| A-05 | A-07 | Décisions de prix `OK` (ou `REVIEW` validées par P) | `rules_version` et `inputs_hash` présents |
| A-04, A-08 | A-07 | Fiche (données + textes) | Statut `VALIDÉ`, droits d'image confirmés |
| A-07 | A-12 | Aperçu de publication (`/publish/preview`) | Mode simulation ; aucun champ interne |
| A-12 | A-07 | Feu vert de publication ou blocage motivé | Tests verts ; aucun stop-loss actif |
| A-11 | A-05 | Réception (quantités, dommages), proposition de réassort | Contrôle physique fait par P (interventions A03, A04) |
| A-05 | A-10 | Contribution par commande avant acquisition | Calcul du moteur, période indiquée |
| A-10 | A-12 | CAC 7 jours glissants | Commandes payées nettes d'annulations et de remboursements |
| Tous | A-01 | Rapports, fiches d'exception | Format standard (`BRIEF_COMMUN.md` §6) |

## Validation humaine requise

- [ ] Valider le RACI, en particulier les 32 lignes où la propriétaire est **A** : chaque ligne déplacée vers A-01 ou A-12 réduit sa charge.
- [ ] Choisir le **canal d'alerte E3** (SMS, appel, notification) et l'inscrire au mandat : les agents n'en ont pas encore.
- [ ] Confirmer les délais (24 h pour un gate ou toute dépense hors mandat, 48 h pour les autres décisions) et le principe du statu quo sûr à l'expiration.
- [ ] Désigner l'emplacement documentaire **hors dépôt** des pièces fournisseurs réelles (`POKESHOP_DOCS_PRIVES`) : prix B2B et contrats n'entrent pas dans git.
