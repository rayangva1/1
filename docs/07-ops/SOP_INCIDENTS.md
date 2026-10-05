# SOP — Incidents (quarantaine, suspension, notification, correction, test, reprise)

> SOP v0.1 du 4.10.2026, rédigée par l'agent legal-ops.
> Sources : BP §12 workflow incident (« prix anormal, langue ambiguë, flux absent, échec paiement, marge sous seuil ou survente → mise en quarantaine de la référence ou suspension du workflow concerné → notification avec cause et action proposée → correction → test → reprise. Une panne de flux fournisseur ne doit pas effacer du stock local confirmé ») ; §6 (journal, idempotence, file de reprise, arrêt des écritures et retour au dernier état vérifié) ; §13 (« un incident critique rétablit le niveau précédent ») ; `docs/00-pilotage/GATES_GO_NO_GO.md` §1 (définition de l'« erreur critique », stop-loss) ; LPD art. 24 (violation de la sécurité des données).
> Outils : module `pokeshop.incidents` et route `POST /incidents` de l'API (agent integrations, SPEC §2.7 et §2.9) ; journal append-only `audit_log` ; stop-loss `engine/pokeshop/stoploss.py` (agent gouvernance).

## 1. Niveaux de gravité

| Gravité | Définition | Confinement | Notification à la propriétaire | Qui autorise la reprise |
|---|---|---|---|---|
| **S1 critique** | Une des 8 « erreurs critiques » de `GATES_GO_NO_GO.md` §1 (prix public faux ou sous plancher non validé ; stock publié > stock vendable local ; champ interne ou donnée personnelle publics ; double écriture ; promesse sur donnée > 24 h ; commande payée sans réservation ; TVA, devise ou change erroné publié ; écriture réelle non autorisée), **ou** violation de données personnelles, lot suspect, agent hors mandat, stop-loss global | Immédiat et automatique ; **niveau d'autonomie ramené au niveau précédent** (BP §13) | Immédiate (alerte dédiée, pas le digest) | **Propriétaire**, après test |
| **S2 majeur** | Anomalie qui bloque une référence, un flux ou un paiement, sans dommage client constaté | Quarantaine de la référence ou suspension du workflow | Dans l'heure (BL-161) | Agent responsable, après test, si l'action est dans le mandat ; sinon propriétaire |
| **S3 mineur** | Défaut sans effet sur le prix, le stock, l'argent ou les données (faute de frappe, image floue) | Correction directe | Digest quotidien ({{HEURE_DIGEST}}) | Agent responsable |

En cas de doute entre deux niveaux, choisir le plus grave.

## 2. Le workflow en six étapes

| Étape | Ce qui se passe | Qui | Délai | Trace |
|---|---|---|---|---|
| 1. Détection | Contrôle automatique (motifs du moteur de prix, validation d'import, stop-loss, surveillance des flux, tests QA), signalement d'un agent ou d'un client | Système, tout agent | — | Incident créé (`POST /incidents`) avec code INC-xx et gravité |
| 2. Confinement | **Quarantaine** de la référence (non achetable, prix gelé au dernier prix validé, aucune nouvelle promesse) **ou suspension** du workflow concerné. Jamais de suppression de stock local confirmé ; jamais de modification d'une commande conclue | Système, agent responsable | S1 : immédiat ; S2 : < 1 h | `audit_log` : état avant / après |
| 3. Notification | Message au format §4 : cause, périmètre, confinement, impact client, action proposée, décision attendue | Agent 01 (chef de projet) ou agent responsable | S1 : immédiat ; S2 : < 1 h ; S3 : digest | Copie dans l'incident |
| 4. Correction | Corriger la donnée, la règle ou le code ; ne jamais corriger directement en production sans journal | Agent responsable (ou propriétaire si hors mandat) | Selon le cas | Diff ou décision consignée |
| 5. Test | Rejouer en simulation (dry-run) le cas qui a échoué + le cas de recette lié (`RECETTE_AVANT_OUVERTURE.md`) + un cycle de synchronisation complet sans erreur critique ; le test **réussi** n'est attesté au moteur (`POST /incidents/{id}/test`) que par l'agent 12 (`qa-conformite`, ≠ ouvreur) ou la propriétaire, avec le `run_id` d'un cycle `/sync/run` PROPRE, postérieur à l'ouverture, lancé par un autre principal, sur le fournisseur et la référence de l'incident, sur données réelles — un cycle FICTIF n'est admis que pour un incident sur données FICTIVES ou ouvert alors que le moteur est en simulation (`POKESHOP_DRY_RUN=true`) ; moteur en écritures réelles, un incident déclaré « simulation » est traité comme réel (confinement compris) | Agent 12 QA | Avant toute reprise | Résultat du test joint |
| 6. Reprise | Levée de la quarantaine ou reprise du workflow, depuis le dernier état vérifié, avec les clés d'idempotence (pas de double écriture) ; vérification de l'état réel sur le site | Selon §1 | Après test OK | Incident clos ; post-mortem si S1 (§5) |

## 3. Catalogue des incidents

| Code | Incident | Détection type | Confinement | Correction et points de vigilance | Gravité par défaut |
|---|---|---|---|---|---|
| INC-01 | **Prix anormal** : prix fournisseur ×10 ou ÷10, prix zéro, prix public différent du prix validé | Motifs `PRICE_ANOMALY`, `ZERO_PRICE` ; contrôle site vs moteur | Référence en quarantaine ; retour au dernier prix validé (`PriceHistory.rollback`) | Vérifier l'import (unité vs carton, devise, HT/TTC) ; les commandes déjà conclues gardent leur prix | S2 ; **S1** si un prix faux a été publié |
| INC-02 | **Langue ou identité ambiguë** (FR/EN/JP de même nom, contenu différent, GTIN absent) | `LANGUAGE_MISMATCH`, `UNKNOWN_FIELDS`, correspondance ambiguë | Fiche en brouillon ; aucun nouveau prix public | Confirmation écrite du fournisseur ; contrôle à réception | S2 |
| INC-03 | **Flux fournisseur absent** ou donnée de plus de 24 h | Surveillance des flux ; `STALE_OFFER` | Achats et nouvelles promesses (précommandes, disponibilités) bloqués ; **le stock local continue de se vendre** | Relancer le fournisseur ; import assisté si nécessaire (BP §6) | S2 |
| INC-04 | **Échec de paiement** : panne du prestataire, taux de refus anormal, paiement capturé sans commande, versement manquant | Alertes PSP ; rapprochement hebdomadaire | Suspension des campagnes payantes pendant la panne ; aucune relance client automatique | Contacter le PSP ; rapprocher chaque transaction | S2 ; **S1** si commande payée sans réservation |
| INC-05 | **Marge sous seuil** : contribution < 12 % ou < 8 CHF par commande | Motifs `BELOW_HARD_FLOOR`, `BELOW_ORDER_FLOOR_CHF` ; stop-loss produit | Vente et promotion de la référence bloquées (stop-loss produit) | Revoir le coût rendu, le prix ou retirer la référence ; exception seulement par la propriétaire (C18) | S2 |
| INC-06 | **Survente** : commande payée non couverte par le stock local | Réservation impossible ; écart Shopify / moteur | Référence en quarantaine ; workflow de synchronisation suspendu ; niveau d'autonomie précédent | Servir la commande payée la plus ancienne ; pour les autres : excuses, choix entre remboursement intégral et attente d'un réassort confirmé ; analyse de cause (R05) | **S1** |
| INC-07 | **Fuite d'un champ interne** (coût, marge, fournisseur, prix B2B) ou d'une donnée personnelle dans une page, un payload ou un visuel public | Test de fuite de `publish.py` ; revue QA ; signalement | Dépublication immédiate (fiche masquée, thème ou contenu restauré) | Corriger le filtre ; vérifier les autres fiches ; si donnée personnelle : INC-10 | **S1** |
| INC-08 | **Double écriture ou écriture refusée** : reprise non idempotente, API boutique refusée, conflit de concurrence d'inventaire | Journal d'écritures ; erreurs API | Suspension du workflow ; arrêt des écritures et retour au dernier état vérifié (BP §6) | Rejouer depuis la file de reprise avec les mêmes clés d'idempotence | **S1** si double écriture ; S2 sinon |
| INC-09 | **Stop-loss déclenché** : extension, pub, cash, global ou temps (seuils au §6) | Module stop-loss | Effet automatique du stop-loss | Dossier de décision préparé par l'agent 01 | S2 ; **S1** pour le stop-loss global |
| INC-10 | **Violation de la sécurité des données personnelles** (accès non autorisé, envoi au mauvais destinataire, fuite d'un export, compte compromis) | Alerte d'un outil, signalement | Couper l'accès (mots de passe, jetons révoqués, partage retiré) ; conserver les preuves | Procédure §7 (annonce au PFPDT si risque élevé) | **S1** |
| INC-11 | **Lot suspect** : doute d'authenticité à réception ou contestation d'un client | SOP réception (C7) ; SAV-20 | **Tout le lot** en quarantaine physique et logique ; aucune vente | Réclamation fournisseur ; décision de la propriétaire seule | **S1** |
| INC-12 | **Allocation annulée ou compte fournisseur coupé** | Email fournisseur ; échec d'import | Précommandes fermées ; achats suspendus chez ce fournisseur | Remboursement des précommandes non servies ; bascule sur la 2e source (R18) | S2 |
| INC-13 | **Réclamation d'un titulaire de droits** (marque, image, texte) | Email, plateforme | Retrait immédiat du contenu visé | `docs/04-legal/USAGE_MARQUES.md` §6 ; la propriétaire transmet au juriste | S2 |
| INC-14 | **Agent hors mandat** (dépense hors plafond, fournisseur non autorisé, envoi non sollicité) | Journal, plafonds PayPal, revue hebdomadaire | Gel de l'agent concerné ; retour au niveau 1 | Revue du mandat avec la propriétaire (R20) | **S1** |
| INC-15 | **Erreurs de préparation ou pertes en série** (2 erreurs en 30 jours, ou 2 pertes en 30 jours) | Journal SAV | Contrôle renforcé (double scan) ; envoi contre signature | Analyse de cause ; changement de transporteur ou d'emballage si besoin | S2 |
| INC-16 | **Email client inexact** (prix, articles, statut ou date faux dans une confirmation ou une alerte) | Signalement ; recette | Automatisation concernée suspendue | Email rectificatif aux destinataires ; correction du modèle | S2 ; **S1** si un prix faux a été communiqué |

## 4. Modèle de notification

```
[INCIDENT S1|S2|S3] INC-xx — titre court
Détecté le : jj.mm.aaaa hh:mm, par : contrôle automatique / agent / client
Périmètre : références, workflow, commandes touchées (nombre, montant total)
Cause probable : …
Confinement appliqué : quarantaine de … / workflow … suspendu / niveau d'autonomie N → N-1
Impact client : aucun / N commandes (liste dans l'incident, jamais dans un canal public)
Action proposée : …
Décision attendue de la propriétaire : aucune / question fermée (oui/non) — avant jj.mm hh:mm
Prochaine mise à jour : hh:mm
```

## 5. Post-mortem (obligatoire pour S1, 30 minutes)

| Rubrique | Contenu |
|---|---|
| Chronologie | Détection, confinement, notification, correction, test, reprise (heures) |
| Impact | Commandes, clients, montants, données |
| Cause racine | Pourquoi le contrôle n'a pas arrêté l'erreur plus tôt |
| Coût | Remboursements, renvois, temps ; imputé à l'étoile polaire (SAV / charges) |
| Actions | Test ajouté (obligatoire), règle modifiée, SOP modifiée ; responsable et date |

## 6. Stop-loss : rappel des seuils et de ce qui ne s'arrête jamais

Seuils fixés par le modèle d'opération ; le calcul fait foi dans `engine/pokeshop/stoploss.py` et `docs/00-pilotage/STOP_LOSS.md` (agent gouvernance).

| Niveau | Déclencheur | Effet automatique |
|---|---|---|
| Produit | contribution < 12 % ou < 8 CHF par commande | vente et promotion de la référence bloquées |
| Extension | > 25 % du budget stock, ou 45 jours sans vente | plus de réassort ; proposition de démarque |
| Pub | CAC > contribution sur 7 jours glissants, ou plafond jour atteint | campagne coupée |
| Cash | cash disponible < réserve de 1 600 CHF | plus d'achat ni de publicité |
| Global | perte de valeur nette ≥ 20 % du capital engagé de référence (définition unique, `STOP_LOSS.md` §3 ; 840 CHF avec le point zéro recommandé de 4 200 CHF) ; photo non évaluable = toute écriture et toute dépense refusées | tout gelé, retour au niveau d'autonomie 1, alerte ; **réarmement par la propriétaire uniquement** |
| Temps | 60 jours sans atteindre les seuils de validation | dossier continuer / ajuster / arrêter |

**Ce qu'un gel, même global, n'arrête jamais** (obligations envers les clients) :

- l'expédition des commandes **déjà payées** ;
- les remboursements dus (annulations, retours acceptés, allocations réduites, doublons) ;
- les réponses du service client et les décisions de garantie ;
- les demandes liées aux données (accès, effacement, désinscription).

**Point à trancher avec l'agent gouvernance :** pendant un gel global, la vente du stock local **au dernier prix validé**, sans promotion ni publicité, continue-t-elle ? Proposition : oui, sauf décision contraire de la propriétaire, car elle reconstitue du cash sans nouvel engagement.

## 7. Violation de la sécurité des données (INC-10) — procédure

1. **Contenir** (immédiat) : révoquer jetons et mots de passe concernés, retirer le partage, isoler l'outil.
2. **Évaluer** (le jour même) : quelles données, combien de personnes, quel risque (usurpation, fraude, atteinte à la réputation).
3. **Décider** (propriétaire) : si la violation entraîne vraisemblablement un **risque élevé** pour les personnes, l'annoncer au PFPDT **dans les meilleurs délais** (art. 24 LPD), via son formulaire d'annonce en ligne (site du PFPDT) ; informer les personnes concernées si leur protection l'exige.
4. **Documenter** toutes les violations, même non annoncées : faits, effets, mesures prises.
5. **Corriger** et tester (étapes 4 à 6 du workflow), puis post-mortem.

## Validation humaine requise

- [ ] Propriétaire : valider les niveaux de gravité et les délais de notification (§1).
- [ ] Propriétaire et agent gouvernance : trancher la vente du stock local pendant un gel global (§6).
- [ ] Propriétaire : choisir le canal d'alerte immédiate pour les incidents S1 (SMS, notification mobile ou appel) distinct du digest.
- [ ] Agent 12 QA : vérifier que chaque code INC-01 à INC-16 a un test de détection ou une procédure de détection manuelle.
