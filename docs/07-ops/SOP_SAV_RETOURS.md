# SOP — Service client (SAV), retours et réclamations

> SOP v0.1 du 4.10.2026, rédigée par l'agent legal-ops. Applique les textes clients (`docs/04-legal/CGV.md`, `LIVRAISON_RETOURS.md`, `PRECOMMANDES.md`) : en cas de divergence, les CGV publiées font foi.
> Sources : BP §11 agent 11 (« litige, fraude ou geste hors règle escaladé »), §12 (« litiges complexes » demandent une personne), §7 (politique volontaire sans supprimer les droits liés aux défauts) ; BACKLOG BL-121 (réponse < 24 h ouvrées), BL-173 ; REGISTRE_RISQUES R22, R27, R28.
> Modèle d'opération : l'agent 11 traite la boîte du service client **dans le mandat écrit** (`docs/00-pilotage/DELEGATION_AUTONOMIE.md`, agent gouvernance). La propriétaire n'intervient que pour le physique (retours, contrôle d'un produit) et les cas escaladés.

## 1. Principes

1. **Réponse dans un délai de {{DELAI_REPONSE_SUPPORT}}**, même si c'est pour dire « nous vérifions ».
2. **La matrice décide, pas l'humeur.** Un cas absent de la matrice, ou un montant au-delà de {{PLAFOND_REMBOURSEMENT_AUTONOME}}, part chez la propriétaire.
3. **Jamais moins que la loi, jamais plus que les CGV sans validation.** La garantie légale (art. 197 ss CO) n'est jamais refusée par un agent : un doute sur un défaut s'escalade.
4. **Toute décision négative** (refus de retour, annulation pour fraude ou limite) indique que le client peut demander qu'une personne la réexamine (art. 21 LPD) ; la demande de réexamen est escaladée.
4 bis. **Une personne sur demande.** Si un client demande qu'une personne lui réponde, reprenne sa demande ou réexamine une réponse, le cas est **toujours** escaladé à la propriétaire (C18) ; l'accusé de réception l'indique, sans promettre de délai autre que {{DELAI_REPONSE_SUPPORT}}. C'est ce que promettent les textes publics (landing, FAQ, confidentialité) ; aucun texte ne doit affirmer qu'« une personne répond » à chaque message.
5. **Identité avant information** : on ne donne le détail d'une commande qu'à l'adresse email de la commande, ou après vérification (nom, numéro de commande, code postal).
6. **Minimisation** : l'IA ne reçoit que le message, le numéro de commande et les données nécessaires ; jamais de données de carte ; aucune donnée client dans un prompt marketing (BP §6).
7. **Pas de reconnaissance de responsabilité** sur un litige, une menace juridique ou une contestation d'authenticité : escalade immédiate.
8. **Chaque cas est journalisé** (§6) : il alimente le coût SAV de l'étoile polaire.

## 2. Matrice de décision

Mouvements de stock : voir `engine/pokeshop/models.py` (`MovementKind`). « Propriétaire » = escalade C18 (INTERVENTIONS_HUMAINES).

| ID | Situation | Preuves à demander | Décision par défaut (agent, dans la matrice) | Mouvement de stock | Escalade à la propriétaire si… | Modèle |
|---|---|---|---|---|---|---|
| SAV-01 | « Où est ma commande ? », pas encore expédiée, dans le délai | — | Donner le délai d'expédition et les jours de dépôt | — | Délai {{DELAI_EXPEDITION}} dépassé | SAV-M01 |
| SAV-02 | Colis en transit, suivi qui avance | — | Envoyer le lien de suivi | — | — | SAV-M01 |
| SAV-03 | Suivi sans mouvement depuis {{SEUIL_COLIS_BLOQUE}} | Numéro de commande | Ouvrir une demande de recherche auprès du transporteur (preuve de dépôt) ; informer le client | — | — | SAV-M03 |
| SAV-04 | Perte confirmée par le transporteur | Réponse du transporteur | Au choix du client : renvoi de l'article (si stock) ou remboursement intégral (article + port) ; réclamation d'indemnisation au transporteur | Renvoi : nouvelle réservation ; remboursement : `REFUND_NO_RETURN` | Montant > {{PLAFOND_REMBOURSEMENT_AUTONOME}} ; 2e perte du même client en 12 mois | SAV-M04, SAV-M10 |
| SAV-05 | Livré selon le suivi mais « pas reçu » | Vérifier boîte aux lettres, voisins, avis de passage ; preuve de distribution du transporteur | Enquête transporteur ; attendre sa réponse | — | **Toujours** si l'enquête conclut à une livraison (risque de fraude) ; envoi contre signature dépassant le seuil | SAV-M03 |
| SAV-06 | Colis abîmé, contenu intact | Photos | Excuses ; aucun remboursement ; photos transmises au transporteur | — | — | SAV-M02 |
| SAV-07 | Article endommagé à réception, signalé dans le délai de {{DELAI_SIGNALEMENT}} | Photos du colis, de l'emballage et de l'article | Remplacement (si stock) ou remboursement de l'article ; retour de l'article endommagé avec étiquette prépayée **seulement** si sa valeur dépasse le coût du retour ; réclamation au transporteur | Retour : `RETURN_DAMAGED` ; sans retour : `REFUND_NO_RETURN` | Montant > plafond ; photos ambiguës | SAV-M02, SAV-M10 |
| SAV-08 | Article endommagé signalé **après** le délai | Photos ; date de réception | Ne pas refuser seul : examiner comme défaut possible (SAV-11) | — | **Toujours** (droits légaux possibles) | SAV-M02 |
| SAV-09 | Erreur de préparation (mauvais article, mauvaise langue, mauvaise extension) | Photo de l'article reçu | Envoi du bon article à nos frais + étiquette de retour prépayée pour l'article reçu ; si le bon article manque : remboursement | Retour : `RETURN_RESTOCK` (scellé intact) | Erreur répétée (2e en 30 jours) : incident INC-15 | SAV-M05 |
| SAV-10 | Article manquant dans le colis | Photo du contenu reçu ; poids si connu | Comparer avec la photo de préparation (P6) : si l'article manque sur la photo, envoi complémentaire ; sinon, réclamation transporteur (colis ouvert ?) | Envoi : nouvelle réservation | Photo de préparation montrant l'article complet | SAV-M02 |
| SAV-11 | Défaut de fabrication (garantie légale, 2 ans) : contenu incomplet, défaut d'impression grave | Photos, vidéo d'ouverture si disponible | Proposer le remplacement par un article identique ; à défaut, remboursement ; recours auprès du fournisseur ou du fabricant | Retour : `RETURN_DAMAGED` | **Toujours** si la demande porte sur un produit ouvert ou si le client demande réduction ou annulation de l'achat | SAV-M02 |
| SAV-12 | « Pas de carte rare », contenu décevant | — | Expliquer le contenu aléatoire (CGV ch. 2.3) ; aucun geste | — | Client qui conteste par écrit une seconde fois | SAV-M13 |
| SAV-13 | Retour volontaire dans le délai de {{DELAI_RETOUR_VOLONTAIRE}}, article non ouvert | Numéro de commande, article concerné | Accepter ; envoyer instructions et `ADRESSE_RETOURS` ; à réception, propriétaire contrôle le scellé ; remboursement du prix de l'article sous {{DELAI_REMBOURSEMENT}} | À réception conforme : `RETURN_RESTOCK` ; scellé abîmé : refus (SAV-14) | — | SAV-M08, SAV-M10 |
| SAV-14 | Retour volontaire hors délai, ou article ouvert / scellé abîmé | Photos si l'article est déjà renvoyé | Refus poli, rappel de la garantie légale, offre de réexamen humain ; article déjà reçu : renvoyé au client à ses frais | — | Le client invoque un défaut (→ SAV-11) ou demande un réexamen | SAV-M09 |
| SAV-15 | Annulation d'une commande en stock local, avant expédition | — | Statut « non préparée » : annulation et remboursement intégral. Déjà préparée ou expédiée : appliquer le retour volontaire (SAV-13) | `CANCEL` (réservation libérée) | — | SAV-M10 |
| SAV-16 | Précommande : annulation, report, allocation réduite, contenu modifié | Numéro de commande | Appliquer `PRECOMMANDES.md` (annulation gratuite {{DELAI_ANNULATION_PRECOMMANDE}} ; report > {{SEUIL_REPORT_PRECOMMANDE}} : annulation possible ; allocation réduite : ordre de paiement) | `CANCEL` | Plus de 5 commandes annulées sur une même référence | SAV-M06, SAV-M07, SAV-M10 |
| SAV-17 | Paiement en double, commande en double | Relevé ou capture | Vérifier dans le PSP ; rembourser le doublon et annuler la commande en double | `CANCEL` sur la commande en double | Doublon non visible dans le PSP | SAV-M10 |
| SAV-18 | Soupçon de fraude ou contournement de la limite par foyer (adresses multiples, même moyen de paiement, signal de risque du PSP) | — (ne pas accuser) | **Retenir** la commande (pas d'étiquette) ; réduire à la limite (CGV ch. 4.4) ; jamais d'annulation pour fraude sans décision humaine | Réduction : `CANCEL` partiel | **Toujours** pour une annulation pour fraude | SAV-M11 |
| SAV-19 | Rétrofacturation (chargeback) ou litige ouvert auprès du PSP | Dossier : commande, preuve de dépôt, suivi, preuve de distribution, échanges | Constituer le dossier dans le délai du PSP ; ne pas rembourser en parallèle (double remboursement) | — | **Toujours** (montant, réponse au PSP) | — |
| SAV-20 | Le client affirme avoir reçu une contrefaçon | Photos détaillées ; ne pas ouvrir d'autres unités | Accusé de réception ; mettre le **lot** en quarantaine préventive ; incident INC-11 | Lot bloqué | **Toujours, le jour même** | SAV-M02 |
| SAV-21 | Demande d'accès, de rectification, d'effacement ou de portabilité des données (LPD) | Vérification d'identité proportionnée | Accusé de réception ; préparer l'export ou l'effacement (sauf pièces comptables à conserver 10 ans) ; réponse gratuite sous 30 jours | — | Envoi de la réponse validé par la propriétaire ; demande d'un tiers ou d'une autorité | SAV-M12 |
| SAV-22 | Désinscription, plainte pour email non sollicité | — | Désinscrire **sans délai** dans tous les outils (emailing, statut marketing Shopify) ; confirmer ; vérifier la preuve de consentement | — | Plainte formelle ou mention d'une autorité | SAV-M01 |
| SAV-23 | Colis non retiré, refusé, adresse erronée (retour à l'expéditeur) | — | Contacter le client : nouvel envoi à ses frais ou remboursement des articles moins les frais d'envoi et de retour effectifs (CGV ch. 6.6) | Retour conforme : `RETURN_RESTOCK` | Client injoignable 14 jours : décision de la propriétaire | SAV-M01 |
| SAV-24 | Erreur de prix manifeste détectée sur une commande | Capture de la fiche au moment de la commande (historique des prix) | Informer sous 2 jours ouvrés ; le client choisit prix correct ou annulation remboursée (CGV ch. 3.5) | `CANCEL` si annulation | **Toujours** avant d'écrire au client (invoquer l'erreur est une décision) | SAV-M14 |
| SAV-25 | Demande hors périmètre : livraison à l'étranger, cartes à l'unité, rachat de cartes, estimation de valeur, retrait sur place | — | Réponse factuelle selon la FAQ ; aucune estimation de valeur | — | — | SAV-M01 |
| SAV-26 | Menace juridique, avocat, médias, réclamation d'un titulaire de droits, insulte ou harcèlement | — | Accusé de réception neutre, sans engagement ni reconnaissance | — | **Toujours, le jour même** | — |

## 3. Matrice résumée « qui décide »

| Décision | Agent 11 seul | Propriétaire |
|---|---|---|
| Information, suivi, recherche transporteur | Oui | |
| Remboursement ou renvoi prévu par la matrice, jusqu'à {{PLAFOND_REMBOURSEMENT_AUTONOME}} | Oui | |
| Remboursement au-delà du plafond, geste commercial hors CGV | | Oui |
| Refus d'un retour volontaire hors conditions (avec offre de réexamen) | Oui | Réexamen sur demande |
| Refus d'une demande de garantie, annulation pour fraude, erreur de prix | | Oui |
| Contrôle physique d'un retour (scellé, état) | | Oui (physique) |
| Contestation d'authenticité, litige PSP, menace juridique | | Oui |

## 4. Modèles de réponses (ton : précis, chaleureux, sans jargon, sans fausse urgence)

Variables propres au cas entre crochets ; champs du registre entre accolades doubles. Signature commune : « L'équipe {{NOM_BOUTIQUE}} — {{EMAIL_SUPPORT}} ».

**SAV-M01 — Information et suivi**
> Bonjour [PRENOM],
> Merci pour votre message. Votre commande [NUMERO_COMMANDE] est [STATUT : en préparation / expédiée le [DATE]]. [Suivi : [LIEN_SUIVI].] Nous déposons les colis selon ce rythme : {{JOURS_EXPEDITION}}, dans un délai de {{DELAI_EXPEDITION}} après le paiement.
> Nous restons à votre disposition.

**SAV-M02 — Demande de photos**
> Bonjour [PRENOM],
> Nous sommes désolés de ce problème avec votre commande [NUMERO_COMMANDE]. Pour le traiter rapidement, pouvez-vous nous envoyer en réponse à cet email : une photo du colis, une photo de l'emballage de l'article et une photo de l'article concerné ? Merci de garder l'emballage jusqu'à la fin du traitement.
> Nous revenons vers vous dès réception.

**SAV-M03 — Recherche ouverte auprès du transporteur**
> Bonjour [PRENOM],
> Le suivi de votre colis [NUMERO_SUIVI] n'avance plus. Nous venons d'ouvrir une recherche auprès de {{TRANSPORTEUR}}. Nous vous écrivons dès que nous avons sa réponse, et au plus tard le [DATE_RELANCE]. Si le colis est perdu, vous choisirez entre un nouvel envoi et un remboursement intégral.

**SAV-M04 — Perte confirmée**
> Bonjour [PRENOM],
> {{TRANSPORTEUR}} nous confirme la perte de votre colis. Nous en sommes désolés. Vous avez le choix : (1) un nouvel envoi de [ARTICLES], sans frais, ou (2) le remboursement intégral de [MONTANT] CHF sur votre moyen de paiement. Dites-nous simplement « 1 » ou « 2 ».

**SAV-M05 — Erreur de préparation**
> Bonjour [PRENOM],
> Vous avez raison : nous vous avons envoyé [ARTICLE_RECU] au lieu de [ARTICLE_COMMANDE]. Toutes nos excuses. Le bon article part le [DATE] (suivi par email). Vous trouverez ci-joint une étiquette de retour prépayée pour l'article reçu par erreur : il suffit de le remettre dans son emballage et de déposer le colis.

**SAV-M06 — Report d'une précommande**
> Bonjour [PRENOM],
> Notre fournisseur nous informe que la sortie de [PRODUIT] est reportée au [NOUVELLE_DATE] (date estimée). Votre précommande [NUMERO_COMMANDE] reste réservée au même prix. [Si report > {{SEUIL_REPORT_PRECOMMANDE}} : Comme ce report dépasse {{SEUIL_REPORT_PRECOMMANDE}}, vous pouvez annuler et être remboursé intégralement : répondez simplement « annuler ».] Nous vous tiendrons informé.

**SAV-M07 — Allocation réduite**
> Bonjour [PRENOM],
> Notre fournisseur nous a livré moins de [PRODUIT] que la quantité confirmée. Les précommandes ont été servies dans l'ordre de leur paiement et, malheureusement, la vôtre ([NUMERO_COMMANDE]) ne peut pas l'être. Nous l'avons annulée et vous remboursons [MONTANT] CHF, crédités sur votre moyen de paiement dans un délai de {{DELAI_REMBOURSEMENT}} au plus. Nous sommes désolés de cette déception.

**SAV-M08 — Retour volontaire accepté**
> Bonjour [PRENOM],
> Votre retour de [ARTICLE] est accepté. Merci de l'envoyer non ouvert, film et scellé intacts, dans un emballage protecteur, à : {{ADRESSE_RETOURS}}. Indiquez le numéro [NUMERO_COMMANDE] dans le colis. Le retour est à vos frais ; nous recommandons un envoi avec suivi. Dès réception et contrôle, nous remboursons [MONTANT] CHF dans un délai de {{DELAI_REMBOURSEMENT}}.

**SAV-M09 — Retour non accepté**
> Bonjour [PRENOM],
> Merci pour votre demande. Notre politique de retour volontaire s'applique aux articles non ouverts, avec film et scellé intacts, dans un délai de {{DELAI_RETOUR_VOLONTAIRE}} ([RAISON : délai dépassé / article ouvert]). Nous ne pouvons donc pas accepter ce retour. Si l'article présente un défaut, la garantie légale s'applique : décrivez-nous le problème avec des photos. Vous pouvez aussi demander qu'une personne de notre équipe réexamine cette réponse.

**SAV-M10 — Remboursement effectué**
> Bonjour [PRENOM],
> Nous avons remboursé [MONTANT] CHF pour [MOTIF] sur le moyen de paiement utilisé pour la commande [NUMERO_COMMANDE]. Le délai de crédit dépend ensuite de votre banque ou de votre émetteur de carte.

**SAV-M11 — Commande retenue ou réduite (limite par foyer)**
> Bonjour [PRENOM],
> Pour permettre au plus grand nombre de collectionneurs d'acheter les nouveautés, la quantité est limitée à {{LIMITE_PAR_CLIENT}} (CGV ch. 4.4). Votre commande [NUMERO_COMMANDE] dépasse cette limite : nous l'avons ramenée à [QUANTITE] et remboursons l'excédent, soit [MONTANT] CHF. Si vous pensez qu'il s'agit d'une erreur, répondez à cet email : une personne de notre équipe réexaminera la situation.

**SAV-M12 — Demande liée aux données personnelles**
> Bonjour [PRENOM],
> Nous avons bien reçu votre demande concernant vos données personnelles, le [DATE]. Pour protéger vos données, merci de nous confirmer [ELEMENT_DE_VERIFICATION : le numéro d'une de vos commandes et le code postal de livraison]. Nous vous répondrons gratuitement, dans un délai de 30 jours au plus.

**SAV-M13 — Contenu aléatoire**
> Bonjour [PRENOM],
> Nous comprenons votre déception. Le contenu des boosters est aléatoire et déterminé par le fabricant : ni nous ni aucun revendeur ne pouvons garantir une carte précise ou un niveau de rareté. Nous n'ouvrons, ne pesons et ne trions jamais nos produits scellés. Si un produit vous semble incomplet par rapport au contenu annoncé sur l'emballage, envoyez-nous des photos : nous l'examinerons.

**SAV-M14 — Erreur de prix manifeste** *(envoi après validation de la propriétaire)*
> Bonjour [PRENOM],
> Une erreur s'est glissée dans le prix de [PRODUIT] au moment de votre commande [NUMERO_COMMANDE] : il était affiché à [PRIX_AFFICHE] CHF au lieu de [PRIX_CORRECT] CHF. Nous vous prions de nous en excuser. Vous pouvez soit confirmer la commande au prix correct, soit l'annuler : dans ce cas, nous remboursons intégralement [MONTANT] CHF dans un délai de {{DELAI_REMBOURSEMENT}}. Merci de nous indiquer votre choix.

## 5. Contrôle physique d'un retour (propriétaire, 15 min)

- [ ] R1. Photographier le colis retour fermé (état, étiquette), puis ouvert.
- [ ] R2. Vérifier que l'article correspond à la commande citée par l'agent (référence, GTIN, langue).
- [ ] R3. Retour volontaire (SAV-13) : film d'origine intact, scellé non ouvert, aucun enfoncement. Un doute = pas de remise en stock.
- [ ] R4. Article signalé endommagé ou défectueux (SAV-07, SAV-11) : ranger au bac ENDOMMAGÉ, photographier le défaut.
- [ ] R5. Indiquer le résultat à l'agent 11 : « conforme » (mouvement `RETURN_RESTOCK`, remboursement déclenché) ou « non conforme » avec photos (refus avec modèle SAV-M09, article renvoyé au client à ses frais).
- [ ] R6. Ne jamais remettre en vente un article dont l'authenticité est douteuse : lot en quarantaine (INC-11).

## 6. Journal SAV (une ligne par cas)

| Champ | Contenu |
|---|---|
| Date d'ouverture / de clôture | jj.mm.aaaa |
| Commande | numéro |
| Cas | SAV-01 à SAV-26 |
| Décision | texte court ; qui a décidé (agent / propriétaire) |
| Montant remboursé (CHF) | 0 si aucun |
| Coût logistique supplémentaire (CHF) | renvoi, étiquette de retour |
| Récupéré auprès du transporteur ou du fournisseur (CHF) | à la clôture de la réclamation |
| Mouvement de stock | code `MovementKind` |
| Temps passé (min) | pour la valorisation du temps |

Chaque semaine, l'agent 11 calcule : nombre de cas par type, coût SAV net par commande (à comparer à la provision R de 1 CHF par commande, hypothèse BP §4) et délai moyen de première réponse. Les chiffres alimentent le tableau de bord (`ROUTINES_PILOTAGE.md`).

## Validation humaine requise

- [ ] Propriétaire : valider le plafond de remboursement autonome (`PLAFOND_REMBOURSEMENT_AUTONOME`) et l'aligner sur le mandat écrit (agent gouvernance).
- [ ] Propriétaire : valider la règle « pas de retour d'un article endommagé de faible valeur » (SAV-07).
- [ ] Juriste : relire les modèles SAV-M09, SAV-M11 et SAV-M14 (refus, réduction, erreur de prix).
- [ ] Propriétaire : désigner une personne de remplacement pour les contrôles physiques des retours pendant ses absences.
