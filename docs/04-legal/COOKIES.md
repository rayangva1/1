# Politique cookies — {{NOM_BOUTIQUE}}

> **À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION**
> Brouillon v0.1 du 4.10.2026, rédigé par l'agent legal-ops. Ce texte n'est pas un avis juridique.
> Base : loi sur les télécommunications, art. 45c (informer sur l'usage des cookies et leur finalité, et indiquer qu'on peut les refuser) [L8] ; LPD (transparence, art. 19) [L5]. Selon les sources indexées le 4.10.2026, le droit suisse n'impose pas en général un consentement préalable, sauf traitement inattendu ou à risque élevé [L8].
> BP §7 : « limiter le suivi à ce qui est configuré légalement ». **Choix proposé ici, plus strict que le minimum légal :** cookies de mesure et de publicité seulement après un clic sur « Accepter ».
> Aucune liste de cookies n'est inventée : le tableau public se remplit à partir d'un relevé réel de la boutique de test (recette R-H03).

<!-- TEXTE_PUBLIC:DEBUT -->
## Cookies

Version en vigueur depuis le {{DATE_VERSION}}.

### Qu'est-ce qu'un cookie ?

Un cookie est un petit fichier enregistré par votre navigateur lorsque vous visitez un site. Il permet par exemple de garder votre panier en mémoire.

### Les cookies que nous utilisons

| Catégorie | À quoi ils servent | Votre choix |
|---|---|---|
| Nécessaires | Panier, paiement, sécurité, mémorisation de vos choix de cookies | Toujours actifs : sans eux, la boutique ne fonctionne pas |
| Mesure d'audience | Compter les visites et comprendre quelles pages sont utiles, de manière agrégée | Activés seulement si vous cliquez sur « Accepter » |
| Publicité | Mesurer l'efficacité de nos publicités sur les réseaux sociaux | Activés seulement si vous cliquez sur « Accepter » |

La liste détaillée (nom du cookie, fournisseur, durée) figure ci-dessous et est mise à jour lorsque nos outils changent.

| Nom | Fournisseur | Catégorie | Finalité | Durée |
|---|---|---|---|---|
| *(relevé de la boutique publiée, à compléter)* | | | | |

Outil de mesure d'audience : {{ST_AUDIENCE}} ({{ST_AUDIENCE_PAYS}}).

### Refuser ou modifier votre choix

- À votre première visite, un bandeau vous propose « Accepter » ou « Refuser ». Refuser est aussi simple qu'accepter.
- Vous pouvez changer d'avis à tout moment avec le lien « Paramètres des cookies » en bas de chaque page.
- Vous pouvez aussi supprimer ou bloquer les cookies dans les réglages de votre navigateur ; la boutique risque alors de ne plus fonctionner correctement (panier, paiement).

### Plus d'informations

Voir notre déclaration de confidentialité ({{URL_CONFIDENTIALITE}}) ou écrivez-nous à {{EMAIL_DONNEES}}.
<!-- TEXTE_PUBLIC:FIN -->

## Partie interne (ne pas publier)

### Mode d'emploi du relevé (agent 07 Site, avant ouverture)

1. Ouvrir la boutique de test dans une fenêtre de navigation privée, sans rien accepter.
2. Outils de développement du navigateur → Stockage → Cookies : noter chaque cookie présent **avant** tout choix (ils doivent tous être « nécessaires »).
3. Cliquer « Refuser », naviguer jusqu'au paiement : aucun cookie de mesure ou de publicité ne doit apparaître (recette R-H03).
4. Recommencer en cliquant « Accepter » : noter les nouveaux cookies (nom, domaine, durée) et les classer.
5. Remplir le tableau public ; dater le relevé ; refaire le relevé à chaque ajout d'application ou de pixel publicitaire.
6. Les noms et durées viennent du relevé et de la documentation officielle de chaque outil, jamais d'une liste recopiée sans vérification.

### Décision à prendre : opt-in ou opt-out

| Option | Conforme ? | Effet sur le pilotage |
|---|---|---|
| **Opt-in** (proposé) : mesure et publicité après « Accepter » | Au-delà du minimum légal suisse selon les sources indexées ; prudent si des visiteurs de l'UE arrivent | Moins de conversions attribuées aux publicités. Le CAC du stop-loss « pub » se calcule donc sur les commandes payées avec un code ou un lien dédié (BP §9), pas sur les seules données du pixel |
| Opt-out : actifs par défaut, refus possible | Minimum légal (art. 45c LTC), à confirmer par le juriste | Meilleure attribution ; risque d'image et de non-conformité si le traitement est jugé « inattendu » |

## Validation humaine requise

- [ ] Propriétaire : choisir opt-in (proposé) ou opt-out, en connaissant l'effet sur la mesure du CAC.
- [ ] Juriste : valider le texte et l'exigence de consentement pour les pixels publicitaires.
- [ ] Agent 07 Site : faire le relevé réel des cookies sur la boutique de test et compléter le tableau (recette R-H03) ; renseigner `ST_AUDIENCE`.
