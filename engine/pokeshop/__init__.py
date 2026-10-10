"""pokeshop — moteur coûts / prix / stock et intégrations de la boutique Pokémon JCC FR (Suisse).

Modules du cœur (agent core-engine) :

* :mod:`pokeshop.models`  — types partagés (Decimal, immuables) ;
* :mod:`pokeshop.errors`  — exceptions métier ;
* :mod:`pokeshop.pricing` — coût rendu, prix plancher, arrondi, contribution, décisions ;
* :mod:`pokeshop.costs`   — coût historique (CMP), coût de remplacement, historique des prix ;
* :mod:`pokeshop.stock`   — vendable, précommandes, péremption, réservations, réassort ;
* :mod:`pokeshop.rules`   — règles versionnées ``config/pricing_rules.vN.yaml``.

Le paquet n'importe aucun sous-module à l'import : ``from pokeshop.pricing import decide_price``.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
