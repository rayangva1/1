# Emails fournisseurs — prêts à envoyer

> BP §2 « La demande commerciale et technique » et §13 « La première action concrète » : envoyer à trois fournisseurs FR le **même panier pilote**, avec un **exemple de fichier de prix/stock**, puis aux sources de priorité 2.
> Envoi par l'agent 02 depuis l'adresse dédiée, **dans le mandat** (BL-040, BL-041), après G0 et la validation du dossier B2B et du panier (C02). Aucun email n'a été envoyé à ce jour.
> Pièces jointes : `DOSSIER_B2B.md` (partie « À envoyer », en PDF) et `PANIER_PILOTE.csv` (converti en XLSX, colonnes `ref_id` à `remarque`, sans la colonne `statut_vise`).

## 0. Contacts publics et vérification

Vérification du 4.10.2026. L'accès direct aux sites fournisseurs a été **refusé par le proxy** de l'environnement de build (HTTP 403 ; domaine Matoo non résolu). Contrôles faits par **index de recherche web**. La tâche BL-021 rouvre chaque page avant le premier envoi.

| Fournisseur | Canal (BP) | Canal à utiliser | Constat du 4.10.2026 | Écart |
|---|---|---|---|---|
| Asmodee France (prio 1) | https://www.asmodee.fr/contact/ [S1] | Formulaire de création de compte détaillant du site B2B (texte du §2 collé dans le champ message) | Page de contact indexée ; elle renvoie les détaillants vers le site B2B (`shop.asmodee.fr`). Une adresse commerciale générique citée par un résumé de recherche n'a **pas** été vue sur une page officielle : ne pas l'utiliser avant vérification. | EC-04 (territoire) |
| Matoo et Miao (prio 1) | https://wholesale.miao.matoocorp.com/ [S2] | Inscription pro sur le portail + message | Page indexée (« Accueil ») ; grossiste Pokémon FR/JP/CN basé à Joigny selon l'index ; domaine non résolu depuis le build | EC-05 |
| TCG Distribution (prio 1) | https://tcgdistribution.fr/contactez-nous.html [S3] | Formulaire de contact | Page indexée ; grossiste FR/JP/EN/CN | — |
| OtakuWorld (prio 2) | distribuzione@otakuworld.ch [S4] | Email du BP ; repli `info@otakuworld.ch` (indexée) ou formulaire du portail https://b2b.otakuworld.ch/ | L'adresse du BP n'apparaît pas dans l'index ; entreprise tessinoise (italophone) | EC-03 |
| CardCosmos (prio 2) | https://cardcosmos.ch/fr/pages/acces-b2b [S5] | Formulaire d'accès B2B | Index : rattaché à `cardcosmos.de`, expédition depuis l'Allemagne | EC-02 |
| Carletto AG (**hors BP**) | — | `info@carletto.ch` (résumé de recherche, à vérifier) ou formulaire de https://www.carletto.ch/ | Distributeur principal Pokémon en Suisse selon la presse suisse | EC-01 ; envoi seulement après C05 |

## 1. Règles d'envoi

1. **Un fournisseur par email.** Jamais de copie visible à un autre fournisseur ; ne jamais citer les prix ou le nom d'un concurrent.
2. Remplacer tous les `{{…}}` avant l'envoi. En cas d'information inconnue, écrire « en cours », jamais une valeur supposée.
3. Ne jamais envoyer de pièce d'identité ni de document KYC par email : uniquement par le formulaire sécurisé du fournisseur (action B11 de la propriétaire).
4. Aucun engagement : pas d'acceptation de conditions générales, de commande ni de paiement par l'agent. Les propositions engageantes remontent à la propriétaire (C08, C13).
5. Consigner chaque envoi dans `TRACKER_CONTACTS.csv` : `date_premier_contact`, statut `demande envoyée`. Relance 1 à **J+5**, relance 2 à **J+12** (jours calendaires après l'envoi).
6. Statuts du tracker : `non contacté` → `demande envoyée` → `relance 1` → `relance 2` → `réponse reçue` → `compte demandé` → `compte ouvert` → `devis reçu` → `autorisé (mandat)` / `refusé` / `sans suite`.
7. **Transparence (recommandée, à valider) :** la signature mentionne que l'adresse est gérée avec des outils d'assistance et que les engagements sont confirmés par la responsable.
8. **Assemblage :** dans chaque email, remplacer `{{Bloc A}}` et `{{Bloc B}}` par le texte des blocs du §2, mot pour mot (sans les chevrons de citation), et `{{Signature commune}}` par la signature ci-dessous. Relire l'email assemblé avant l'envoi : il ne doit plus contenir aucun `{{`.

### Signature commune

```
{{PRÉNOM NOM}}
{{fonction}} — {{NOM_BOUTIQUE}}
{{RAISON_SOCIALE}} · IDE {{CHE-xxx.xxx.xxx / en cours}}
{{ADRESSE}} · {{NPA}} {{LOCALITÉ}} · Suisse
{{EMAIL_DEDIE}} · {{TÉLÉPHONE}}
Cette adresse est gérée avec l'aide d'outils d'assistance ; tout engagement commercial est confirmé par écrit par {{PRÉNOM NOM}}.
```

## 2. Blocs communs (repris à l'identique dans chaque email)

### Bloc A — Demande commerciale (BP §2)

> **Pour chaque référence du panier pilote joint**, pourriez-vous nous indiquer :
> 1. votre référence (SKU) ;
> 2. le code EAN/GTIN ;
> 3. la langue (nous recherchons exclusivement la **version française**) ;
> 4. l'extension ;
> 5. le conditionnement exact (contenu : boosters, accessoires, cartes promo) ;
> 6. le nombre d'unités par carton ;
> 7. le prix net, **en précisant HT ou TTC**, et la devise ;
> 8. les remises et paliers de quantité ;
> 9. la quantité minimale de commande (par référence et par commande) ;
> 10. la disponibilité actuelle (quantité ou statut) ;
> 11. vos règles d'allocation sur les nouveautés, et la possibilité d'une **allocation ferme** (par exemple pour Méga-Évolution – Règne Delta) ;
> 12. la date de sortie ou de réassort prévue ;
> 13. les frais de port jusqu'à {{NPA}} {{LOCALITÉ}} (Suisse), avec leurs paliers ;
> 14. l'Incoterm proposé ;
> 15. le pays d'expédition réel ;
> 16. les modalités de paiement (prépaiement, délai, moyens acceptés) ;
> 17. la procédure SAV (produit manquant, endommagé ou non conforme) et le délai de réclamation ;
> 18. votre autorisation, ou vos conditions, pour **réutiliser vos descriptions et images** produits sur notre site.
>
> Pour l'export vers la Suisse : établissez-vous une facture sans TVA française, avec les documents d'exportation ? Qui se charge du dédouanement à l'arrivée ?

### Bloc B — Demande technique (BP §2 « Pour l'automatisation »)

> Nous préparons un import automatique de vos prix et de vos stocks. Pourriez-vous nous préciser :
> 1. **le format** : API documentée, fichier CSV, XML ou Excel, téléchargement authentifié ou envoi périodique par email ;
> 2. **la fréquence** de mise à jour des prix et des stocks ;
> 3. si les **identifiants** (SKU, EAN) restent stables d'une mise à jour à l'autre ;
> 4. si le stock est **quantifié** ou exprimé par un simple statut (disponible / rupture) ;
> 5. si les **commandes et accusés de réception** peuvent être échangés électroniquement (EDI, API, email structuré) ;
> 6. les **limites d'usage** (fréquence d'appel, licence d'utilisation des données) ;
> 7. et, surtout, un **exemple de fichier de prix et de stock**, même partiel ou avec des valeurs d'exemple, pour préparer notre import.
>
> Un accès à votre portail web nous sera utile, mais nous cherchons avant tout un **flux de données** : merci de nous dire si un export régulier est possible.

## 3. Asmodee France (priorité 1)

**Canal :** formulaire de demande de création de compte détaillant (site B2B). Coller le texte ci-dessous dans le champ message ; joindre le dossier et le panier si le formulaire le permet, sinon proposer de les envoyer.

**Objet :** Demande de compte revendeur — boutique en ligne suisse de produits Pokémon JCC en français — {{NOM_BOUTIQUE}}

> Madame, Monsieur,
>
> Nous lançons {{NOM_BOUTIQUE}}, une boutique en ligne spécialisée dans les produits Pokémon JCC **officiels et scellés en français**, vendus exclusivement en Suisse depuis notre stock de {{ville}}. Vous trouverez en pièces jointes notre dossier professionnel et notre panier pilote (20 références).
>
> Avant tout, une question de principe : **acceptez-vous l'ouverture d'un compte détaillant pour une entreprise établie en Suisse** et livrez-vous la Suisse ? Si la Suisse relève d'un autre distributeur pour la gamme Pokémon JCC en français, pourriez-vous nous indiquer lequel ?
>
> Si oui, voici les informations dont nous aurions besoin.
>
> {{Bloc A}}
>
> {{Bloc B}}
>
> Nous souhaitons passer une première commande d'environ 3 000 CHF dans les prochaines semaines, puis des réassorts réguliers selon nos ventes. Nous restons à votre disposition pour tout document nécessaire à l'ouverture du compte.
>
> Avec nos meilleures salutations,
>
> {{Signature commune}}

**Relance J+5 — Objet :** Re : Demande de compte revendeur — {{NOM_BOUTIQUE}} (Suisse)

> Madame, Monsieur,
>
> Je me permets de revenir vers vous au sujet de notre demande du {{date d'envoi}} (compte détaillant pour une boutique en ligne établie en Suisse, produits Pokémon JCC en français). Pourriez-vous nous confirmer qu'elle a bien été transmise au bon service, ou nous indiquer à qui l'adresser ?
>
> Avec nos meilleures salutations,
> {{Signature commune}}

**Relance J+12 — Objet :** Re : Demande de compte revendeur — dernière relance

> Madame, Monsieur,
>
> Sans nouvelles de votre part, je me permets une dernière relance. Même une réponse partielle nous serait très utile :
> 1. acceptez-vous une entreprise établie en Suisse, ou devons-nous nous adresser à un autre distributeur pour la Suisse ?
> 2. si oui, pouvez-vous nous transmettre votre tarif revendeur actuel et vos conditions de livraison vers la Suisse ?
>
> Sans réponse d'ici le {{date J+19}}, nous considérerons que notre demande ne peut pas aboutir pour le moment ; vous pourrez bien entendu nous recontacter.
>
> Avec nos meilleures salutations,
> {{Signature commune}}

## 4. Matoo et Miao (priorité 1)

**Canal :** inscription professionnelle sur le portail wholesale, puis message (ou formulaire de contact du portail).

**Objet :** Ouverture de compte professionnel — boutique en ligne suisse Pokémon JCC FR — {{NOM_BOUTIQUE}}

> Madame, Monsieur,
>
> Nous lançons {{NOM_BOUTIQUE}}, une boutique en ligne de produits Pokémon JCC **officiels et scellés en français**, qui vend exclusivement en Suisse depuis {{ville}}. Votre offre Pokémon en français a retenu notre attention. Notre dossier professionnel et notre panier pilote (20 références) sont joints.
>
> Nos premières questions portent sur **l'export vers la Suisse** (livraison, facturation, pays d'expédition), **vos prix nets**, **la disponibilité réelle en français** et **la possibilité d'un flux de données automatisable**. Plus précisément :
>
> {{Bloc A}}
>
> {{Bloc B}}
>
> Nous prévoyons une première commande d'environ 3 000 CHF, puis des réassorts réguliers selon nos ventes. Merci d'avance pour votre retour.
>
> Avec nos meilleures salutations,
>
> {{Signature commune}}

**Relance J+5 — Objet :** Re : Ouverture de compte professionnel — {{NOM_BOUTIQUE}} (Suisse)

> Bonjour,
>
> Je reviens vers vous au sujet de notre demande du {{date d'envoi}} (compte professionnel, livraison en Suisse, produits Pokémon JCC en français). Notre inscription sur votre portail est-elle complète, ou vous manque-t-il un document ?
>
> Belle journée,
> {{Signature commune}}

**Relance J+12 — Objet :** Re : Ouverture de compte professionnel — dernière relance

> Bonjour,
>
> Dernière relance de notre part. Trois réponses courtes nous suffiraient pour avancer :
> 1. livrez-vous la Suisse, avec une facture d'export ?
> 2. pouvez-vous nous envoyer votre tarif revendeur en français ?
> 3. existe-t-il un export de vos prix et stocks (fichier ou API) ?
>
> Sans réponse d'ici le {{date J+19}}, nous classerons notre demande ; vous pourrez bien sûr nous recontacter.
>
> Belle journée,
> {{Signature commune}}

## 5. TCG Distribution (priorité 1)

**Canal :** formulaire de contact (https://tcgdistribution.fr/contactez-nous.html) et inscription professionnelle.

**Objet :** Compte revendeur et livraison en Suisse — Pokémon JCC FR — {{NOM_BOUTIQUE}}

> Madame, Monsieur,
>
> Nous lançons {{NOM_BOUTIQUE}}, boutique en ligne de produits Pokémon JCC **officiels et scellés en français**, avec des ventes exclusivement en Suisse. Nous avons consulté votre catalogue Pokémon FR et souhaitons ouvrir un compte professionnel. Notre dossier et notre panier pilote (20 références) sont joints.
>
> Nos questions prioritaires : **livrez-vous en Suisse**, avec une **facture d'export** ? Quels sont **vos tarifs** sur ce panier ? Proposez-vous **une API ou un fichier CSV** de prix et de stock ? Le détail :
>
> {{Bloc A}}
>
> {{Bloc B}}
>
> Nous envisageons une première commande d'environ 3 000 CHF, puis des réassorts réguliers.
>
> Avec nos meilleures salutations,
>
> {{Signature commune}}

**Relance J+5 — Objet :** Re : Compte revendeur et livraison en Suisse — {{NOM_BOUTIQUE}}

> Bonjour,
>
> Je me permets de relancer notre demande du {{date d'envoi}} concernant l'ouverture d'un compte professionnel avec livraison en Suisse. Pouvez-vous nous indiquer si elle a été reçue et dans quel délai vous pourriez nous répondre ?
>
> Belle journée,
> {{Signature commune}}

**Relance J+12 — Objet :** Re : Compte revendeur Suisse — dernière relance

> Bonjour,
>
> Dernière relance de notre part. Même partielle, votre réponse nous aide :
> 1. livrez-vous la Suisse, avec quelle facture et quel port ?
> 2. pouvez-vous nous transmettre votre tarif revendeur pour le panier joint ?
> 3. existe-t-il un fichier CSV ou une API de prix et de stock ?
>
> Sans retour d'ici le {{date J+19}}, nous classerons notre demande.
>
> Belle journée,
> {{Signature commune}}

## 6. OtakuWorld (priorité 2)

**Canal :** `distribuzione@otakuworld.ch` (BP), à confirmer (BL-021) ; repli `info@otakuworld.ch` ou formulaire du portail B2B.

**Objet :** Accès revendeur — produits Pokémon JCC en français — {{NOM_BOUTIQUE}} (Genève)

> Madame, Monsieur,
>
> Nous lançons {{NOM_BOUTIQUE}}, boutique en ligne suisse de produits Pokémon JCC **officiels et scellés en français**, basée à {{ville}}. Votre portail B2B nous intéresse, d'autant que vous êtes établis en Suisse. Notre dossier professionnel et notre panier pilote (20 références) sont joints.
>
> Nos questions prioritaires :
> - proposez-vous **régulièrement** les produits Pokémon **en français**, et dans quelles quantités ?
> - l'accès au portail est-il possible **sans numéro de TVA**, si notre entreprise n'est pas encore assujettie ? (statut actuel : {{assujetti / non assujetti / en cours d'examen}})
> - comment fonctionnent **vos allocations** sur les nouveautés, et proposez-vous un **flux** de prix et de stock ?
>
> {{Bloc A}}
>
> {{Bloc B}}
>
> Nous pouvons échanger en français ou en italien, selon votre préférence.
>
> Meilleures salutations,
>
> {{Signature commune}}

**Version italienne courte (option, si aucune réponse en français) — Oggetto :** Richiesta accesso rivenditore — prodotti Pokémon GCC in francese — {{NOM_BOUTIQUE}}

> Gentili Signore e Signori,
>
> stiamo avviando {{NOM_BOUTIQUE}}, negozio online svizzero di prodotti Pokémon GCC **ufficiali e sigillati in lingua francese**, con sede a {{ville}}. Vorremmo accedere al vostro portale B2B. In allegato trovate la nostra presentazione aziendale e il paniere pilota (20 referenze).
>
> Vi chiediamo in particolare: disponibilità regolare dei prodotti **in francese**; accesso possibile **senza numero IVA** (non ancora assoggettati); condizioni di **allocazione**; un **file di esempio** dei prezzi e delle giacenze (CSV, Excel o API).
>
> Possiamo scrivere in italiano o in francese.
>
> Cordiali saluti,
> {{Signature commune}}

**Relance J+5 — Objet :** Re : Accès revendeur — {{NOM_BOUTIQUE}}

> Bonjour,
>
> Je reviens vers vous au sujet de notre demande du {{date d'envoi}} (accès revendeur, produits Pokémon en français). Est-elle bien arrivée à la bonne adresse ? Nous pouvons aussi passer par le formulaire de votre portail si vous le préférez.
>
> Meilleures salutations,
> {{Signature commune}}

**Relance J+12 — Objet :** Re : Accès revendeur — dernière relance

> Bonjour,
>
> Dernière relance de notre part. Deux réponses nous suffiraient : (1) avez-vous du Pokémon en français de façon régulière ? (2) l'accès au portail est-il possible pour une entreprise non assujettie à la TVA ?
>
> Sans retour d'ici le {{date J+19}}, nous classerons notre demande.
>
> Meilleures salutations,
> {{Signature commune}}

## 7. CardCosmos (priorité 2)

**Canal :** formulaire de demande d'accès B2B (https://cardcosmos.ch/fr/pages/acces-b2b ; équivalent indexé : https://cardcosmos.de/pages/b2b-zugang). Coller le texte ci-dessous dans le champ « informations sur l'entreprise et les canaux de vente ».

**Objet :** Accès B2B — boutique en ligne suisse Pokémon JCC FR — {{NOM_BOUTIQUE}}

> Madame, Monsieur,
>
> Nous lançons {{NOM_BOUTIQUE}}, boutique en ligne de produits Pokémon JCC **officiels et scellés en français**, avec des ventes exclusivement en Suisse depuis {{ville}}. Nous souhaitons accéder à vos tarifs revendeur. Notre dossier et notre panier pilote (20 références) sont joints, ou disponibles sur simple demande.
>
> Nos questions prioritaires :
> - disposez-vous de **stock en français**, et dans quelle profondeur ?
> - **depuis quel pays** expédiez-vous les commandes vers la Suisse, et sous quelles **conditions** (facture, TVA, dédouanement, délai) ?
> - votre **catalogue est-il exportable** (fichier ou API) ?
>
> {{Bloc A}}
>
> {{Bloc B}}
>
> Avec nos meilleures salutations,
>
> {{Signature commune}}

**Relance J+5 — Objet :** Re : Accès B2B — {{NOM_BOUTIQUE}} (Suisse)

> Bonjour,
>
> Nous avons soumis une demande d'accès B2B le {{date d'envoi}}. Pouvez-vous nous confirmer qu'elle est en cours d'examen, ou nous dire s'il manque une information ?
>
> Meilleures salutations,
> {{Signature commune}}

**Relance J+12 — Objet :** Re : Accès B2B — dernière relance

> Bonjour,
>
> Dernière relance de notre part. Pourriez-vous au moins nous indiquer : (1) le pays d'expédition vers la Suisse ; (2) si vous avez du stock Pokémon en français ; (3) si un export de catalogue est possible ?
>
> Sans retour d'ici le {{date J+19}}, nous classerons notre demande.
>
> Meilleures salutations,
> {{Signature commune}}

## 8. Carletto AG (HORS BP — envoi seulement après la décision C05)

**Pourquoi :** la presse suisse présente Carletto AG comme le distributeur principal des cartes Pokémon en Suisse (écart EC-01). **Canal :** à confirmer (BL-021).

**Objet :** Compte revendeur — produits Pokémon JCC en français pour la Suisse romande — {{NOM_BOUTIQUE}}

> Madame, Monsieur,
>
> Nous lançons {{NOM_BOUTIQUE}}, une boutique en ligne de produits Pokémon JCC **officiels et scellés en français**, qui vend exclusivement en Suisse depuis {{ville}}. Nous savons que vous assurez la distribution des cartes Pokémon en Suisse et aimerions savoir si nous pouvons devenir revendeur.
>
> Nos questions prioritaires :
> - distribuez-vous **la version française** aux revendeurs de Suisse romande, y compris aux boutiques **en ligne** ?
> - quelles sont les **conditions d'ouverture** d'un compte (documents, minimum de commande, paiement) ?
> - comment fonctionnent **les allocations** sur les nouveautés ?
>
> {{Bloc A}}
>
> {{Bloc B}}
>
> Nous pouvons échanger en français ou en allemand.
>
> Avec nos meilleures salutations,
>
> {{Signature commune}}

**Version allemande courte (option) — Betreff :** Händlerkonto — Pokémon-Sammelkartenspiel auf Französisch für die Romandie — {{NOM_BOUTIQUE}}

> Sehr geehrte Damen und Herren
>
> Wir eröffnen {{NOM_BOUTIQUE}}, einen Online-Shop für **offizielle, versiegelte Pokémon-Sammelkartenspiel-Produkte in französischer Sprache**, mit Verkauf ausschliesslich in der Schweiz ab {{ville}}. Gerne möchten wir Händler werden.
>
> Uns interessieren insbesondere: Belieferung von **Online-Händlern in der Romandie** mit der **französischen Version**; **Bedingungen** für die Kontoeröffnung (Unterlagen, Mindestbestellung, Zahlung); **Zuteilungen** bei Neuheiten; eine **Beispieldatei** mit Preisen und Lagerbeständen (CSV, Excel oder API).
>
> Unser Firmenprofil und unser Pilotsortiment (20 Artikel) liegen bei.
>
> Freundliche Grüsse
> {{Signature commune}}

**Relance J+5 et J+12 :** reprendre les modèles du §6 (en français), en remplaçant « accès revendeur » par « compte revendeur pour la Suisse romande ».

## 9. Après la réponse

| Réponse | Action de l'agent 02 | Humain |
|---|---|---|
| Accepte, envoie tarif et conditions | Saisie dans `COMPARATEUR_OFFRES.xlsx` ; checklist de due diligence ; demande de l'exemple de fichier s'il manque | B11 création du compte ; C08 autorisation |
| Accepte, sans flux de données | Import assisté (BP §6, priorité 3) ; nouvelle demande d'exemple de fichier | — |
| Renvoie vers un autre distributeur | Nouveau contact ajouté au tracker (statut `non contacté`) ; demande d'autorisation si hors liste | C05 / C08 |
| Refuse l'export vers la Suisse | Statut `refusé` + motif ; risque R01 mis à jour | — |
| Demande un document KYC | Transmettre la demande à la propriétaire, avec le lien du formulaire sécurisé | B11 |

## Validation humaine requise

- [ ] Valider les textes (C02), en particulier les engagements, le montant indicatif de 3 000 CHF et la mention de transparence de la signature.
- [ ] Remplir les champs `{{…}}` de la signature et des emails.
- [ ] Autoriser ou non la piste Carletto AG (C05) avant tout envoi du §8.
- [ ] Faire elle-même les créations de compte et les envois de pièces KYC (B11) ; les agents s'occupent des envois d'information et des relances.
