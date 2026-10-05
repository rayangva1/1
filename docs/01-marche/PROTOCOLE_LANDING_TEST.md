# Protocole de test de la page de présentation (landing)

> BP §1 : « Tester une page de présentation avec inscription aux alertes. Aucun faux stock et aucune précommande encaissée sans allocation. » BP §9 (J1-15) : « page présentation et inscriptions ».
> Construction : agent 07 (`site/landing/`, BL-031). Publication : GO de la propriétaire (BL-032, C07). Suivi : agent 10 (BL-034).
> Période de test : de la publication (cible J10, 14.10.2026) à l'ouverture douce (cible J38, 11.11.2026). La landing devient ensuite la page d'accueil de la boutique.

## 1. Ce que l'on veut apprendre

| Hypothèse | Mesure | Décision qu'elle éclaire |
|---|---|---|
| H1. Une boutique suisse spécialisée en Pokémon FR intéresse assez de monde pour une ouverture douce | Inscriptions **confirmées** (double opt-in) | Volume de l'ouverture douce ; besoin d'autres canaux (G4) |
| H2. Certains formats sont plus demandés que d'autres | Répartition des préférences de formats cochées | Répartition du budget stock (`ASSORTIMENT_PILOTE.md`) |
| H3. La demande vient surtout de Romandie | Répartition par canton (champ facultatif) | Ciblage des contenus et de la publicité |
| H4. Certains canaux recrutent mieux | Inscriptions confirmées par source (UTM) | Allocation du temps de communication |

## 2. Ce que la page montre, et ce qu'elle ne montre jamais

| Autorisé | Interdit |
|---|---|
| La promesse (BP §1) : Pokémon JCC en français, expédié depuis la Suisse, disponibilité lisible, produits correctement identifiés, service fiable | Tout stock, compteur, « bientôt épuisé », « dernières pièces », minuterie ou fausse urgence |
| Les **formats** prévus (displays, ETB, bundles, coffrets, accessoires), décrits sans prix | Tout prix, même indicatif, tant que les coûts réels ne sont pas validés (SPEC §0.5) |
| « Ouverture prévue en {{mois}} », sans date ferme | Une date d'ouverture ferme avant la réception du stock |
| Un formulaire d'alerte (email + préférences) | Une précommande, un acompte, une réservation ou tout encaissement |
| Le nom de la boutique validé et la DA approuvée | Le logo ou les personnages Pokémon ; toute impression de statut officiel (BP §8) |
| L'identité, l'adresse et l'email de contact de l'exploitant (BP §7, [S11]) ; un lien vers la notice de confidentialité | Un coût, une marge, un fournisseur ou une donnée interne dans le HTML (SPEC §0.2) |

## 3. Formulaire d'inscription

| Champ | Type | Obligatoire | Remarque |
|---|---|---|---|
| Email | email | Oui | Double opt-in : rien n'est envoyé avant la confirmation |
| Prénom | texte | Non | Salutation des emails |
| « Ce qui m'intéresse » | cases à cocher | Non | Displays · ETB · Bundles et tripacks · Coffrets cadeaux · Accessoires · Nouveautés ; ciblage des alertes et H2 (agrégé) |
| Budget habituel par achat | choix | Non | Tranches de CHF (préférence déclarée, pas un prix) ; H2 (agrégé) |
| Pour qui | choix | Non | Moi (collection) · Moi (jeu) · Cadeau ou enfant ; H2 (agrégé) |
| Canton | liste | Non | Pour H3 (agrégé) ; « Hors de Suisse » affiche « livraison en Suisse uniquement » |
| Origine (utm_source, utm_medium, utm_campaign) | champs cachés | — | Pour H4 (agrégé) ; lus dans le lien suivi |
| Consentement | case **non pré-cochée** | Oui | Texte exact : celui de `site/landing/index.html` (version `alertes-v1-2026-10-04`) + lien vers la notice |

**Chaque champ et chaque usage (y compris les usages agrégés H2 à H4) figure dans la notice de la landing** (`docs/04-legal/CONFIDENTIALITE_LANDING.md`) et dans l'aide sous la case de consentement : aucun texte ne dit que les données servent « uniquement » aux envois. Un champ ajouté au formulaire sans être déclaré dans la notice fait échouer `site/outils/verifier_site.py`.

Email de confirmation (double opt-in) : objet « Confirmez votre alerte {{NOM_BOUTIQUE}} » ; un seul bouton « Confirmer » ; rappel de ce qui sera envoyé ; lien de désinscription.

## 4. Proposition de textes (à adapter au ton validé)

- **Titre :** « Pokémon JCC en français, expédié depuis la Suisse. »
- **Sous-titre :** « Displays, coffrets et nouveautés officiels, avec un stock affiché tel qu'il est et un service qui répond. Ouverture prévue en {{mois}}. »
- **Bouton :** « Être prévenu(e) de l'ouverture »
- **Réassurance (3 points) :** « Produits scellés officiels en français » · « Stock réel, pas de promesse en l'air » · « Expédition depuis {{ville}} »
- **Mention :** « {{NOM_BOUTIQUE}} est une boutique indépendante. Pokémon est une marque de ses propriétaires respectifs. »

## 5. Trafic : sources autorisées

Jusqu'au gate G4, **aucune publicité payante** : le test pub n'intervient qu'entre J46 et J60 (BP §9).

| Source | Lien suivi (UTM `utm_source`) | Qui |
|---|---|---|
| Réseau personnel de la propriétaire (messages individuels) | `reseau` | Propriétaire |
| Bio et publications Instagram / TikTok de la boutique | `instagram`, `tiktok` | Agent 09 |
| Clubs et lieux TCG (affiche ou QR code, avec l'accord du lieu) | `club-{nom}` | Propriétaire (physique) |
| Questionnaire (message de fin) | `questionnaire` | Agent 09 |
| Entretiens (proposé en clôture) | `entretien` | Propriétaire |

Interdits : achat de listes, messages non sollicités de masse, SMS, inscription d'un tiers sans son accord (BP §9).

## 6. Mesure

Outil de mesure d'audience sans cookie tiers, ou avec bandeau de consentement. Comptage serveur ou outil respectueux de la vie privée de préférence.

| KPI | Définition | Fréquence |
|---|---|---|
| Visiteurs uniques | Visiteurs distincts sur la période | Hebdo |
| Inscriptions démarrées | Formulaires envoyés | Hebdo |
| **Inscriptions confirmées** | Double opt-in validé (KPI principal) | Hebdo |
| Taux de conversion | Confirmées / visiteurs uniques | Hebdo |
| Taux de confirmation | Confirmées / démarrées (< 60 % : vérifier la délivrabilité) | Hebdo |
| Préférences de formats | % de chaque case cochée | Hebdo |
| Répartition géographique | % Romandie / autres cantons / non renseigné | Hebdo |
| Inscriptions par source | Confirmées par UTM | Hebdo |
| Désinscriptions et plaintes | Nombre | Hebdo |

## 7. Lecture des résultats

Le BP vise **30 commandes payées en 60 jours** (§1). La liste d'alertes n'en fournira qu'une partie. Ordre de grandeur des inscrits confirmés nécessaires si la liste devait, à elle seule, produire ces 30 commandes :

| Part des inscrits qui commandent en 60 jours (**hypothèse**, à mesurer) | Inscrits confirmés nécessaires |
|---|---|
| 5 % | 600 |
| 10 % | 300 |
| 20 % | 150 |

Lecture : avec moins de 150 inscrits confirmés à J38, l'ouverture douce ne suffira pas à elle seule, et le test publicitaire (G4) ou les contenus devront porter l'essentiel. Ces taux ne sont pas des prévisions : la mesure réelle (commandes des inscrits / inscrits) remplace l'hypothèse dès J_V1 + 14.

**Seuils de signal proposés (hypothèse, BL-016) :**

| Signal à J38 | VERT | ORANGE | ROUGE |
|---|---|---|---|
| Inscrits confirmés | ≥ 150 | 50 à 149 | < 50 |
| Taux de conversion visite → inscription confirmée | ≥ 8 % | 3 à 8 % | < 3 % |

Un signal ROUGE ne bloque pas un gate à lui seul. Il est porté au dossier G3 (« la demande existe-t-elle ? ») et au plan de communication.

## 8. Checklist avant publication (agent 12, puis GO C07)

- [ ] Aucun prix, stock, compteur ni bouton d'achat ou de précommande.
- [ ] Aucun logo ni personnage Pokémon ; mention d'indépendance présente.
- [ ] Identité, adresse et email de contact de l'exploitant visibles ; notice de confidentialité de la landing (`CONFIDENTIALITE_LANDING.md`) en lien, relue par le juriste (relecture express) et datée (`DATE_VERSION_LANDING`).
- [ ] `python site/outils/publication.py etat` : les champs de la liste fermée sont tous `valide` (aucun ne dépend de la boutique, du paiement, du transporteur ni de la relecture complète J28).
- [ ] Case de consentement non pré-cochée ; double opt-in testé ; désinscription testée en un clic.
- [ ] Aucune donnée interne dans le code source (coûts, fournisseurs, notes).
- [ ] Mesure d'audience conforme (consentement si cookies).
- [ ] Affichage mobile et ordinateur vérifié ; temps de chargement raisonnable.
- [ ] Liens UTM générés pour chaque source du §5.

## 9. Rapport hebdomadaire (modèle)

```markdown
# Landing — semaine du {{lundi}}
Visiteurs uniques : … | Démarrées : … | Confirmées : … (cumul …) | Conversion : … % | Confirmation : … %
Formats préférés : Displays …% · ETB …% · Bundles/tripacks …% · Coffrets …% · Accessoires …% · Nouveautés …%
Géographie : Romandie …% · autres cantons …% · non renseigné …%
Meilleure source : … (… confirmées) | Désinscriptions : … | Plaintes : …
Signal vs seuils : VERT / ORANGE / ROUGE — action proposée : …
```

## Validation humaine requise

- [ ] Donner le GO de publication après la checklist du §8 (C07).
- [ ] Valider les seuils de signal du §7 (hypothèses) ou les remplacer.
- [ ] Diffuser le lien dans son réseau et, avec leur accord, dans les clubs : les agents ne contactent pas de particuliers.
