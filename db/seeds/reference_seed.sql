-- reference_seed.sql — données de référence RÉELLES et sourcées (aucune donnée commerciale).
--
-- * Extensions : copie de data/extensions_aliases.yaml (sources consultées le 4.10.2026) ;
--   tests/test_db_migrations.py vérifie que les deux listes restent identiques.
-- * Fournisseurs : les cinq PISTES du BP §2. Statut PISTE = aucun compte, aucun contact
--   envoyé, aucun tarif, aucun accès automatisé. Aucun contact nominatif.
-- À appliquer après db/migrations/*.sql (voir db/README.md).

BEGIN;

INSERT INTO pokeshop.extensions (code, name_fr, release_date_fr, official_code, source_urls) VALUES
    ('ME02.5', 'Méga-Évolution – Héros Transcendants', '2026-01-30', true, ARRAY[
        'https://www.pokemon.com/us/pokemon-news/get-the-new-pokemon-tcg-expansion-mega-evolution-ascended-heroes-on-january-30-2026',
        'https://leblogdewilly.fr/calendrier-sorties-jcc-pokemon-2026-30-ans-mega-evolutions/',
        'https://blog.cardzia.fr/chaos-ascendant-me04-tout-savoir/']),
    ('ME03', 'Méga-Évolution – Équilibre Parfait', '2026-03-27', true, ARRAY[
        'https://lecoindesbarons.com/calendrier-des-sorties-de-cartes-jcc-pokemon-2026-2027/',
        'https://icv2.com/articles/news/view/61079/pokemon-tcg-2026-product-calendar',
        'https://blog.cardzia.fr/chaos-ascendant-me04-tout-savoir/']),
    ('ME04', 'Méga-Évolution – Chaos Ascendant', '2026-05-22', true, ARRAY[
        'https://tcg.pokemon.com/fr-fr/expansions/chaos-rising/',
        'https://www.pokebip.com/news/7257/jcc-pokemon-nouvelle-extension-mega-evolution-chaos-ascendant']),
    ('ME05', 'Méga-Évolution – Nuit Noire', '2026-07-17', true, ARRAY[
        'https://www.pokemon.com/fr/actualites/produits-mega-evolution-nuit-noire-du-jcc-pokemon',
        'https://www.pokekalos.fr/news/actualites-nouvelle-extension-du-jcc-annoncee-me05-nuit-noire-2727.html',
        'https://www.play-in.com/fr/articles/3-pokemon/tout-savoir-sur-l-extension-me05-mega-evolution-nuit-noire']),
    ('ME06', 'Méga-Évolution – Règne Delta', '2026-11-06', true, ARRAY[
        'https://www.pokebip.com/news/7489/jcc-pokemon-nouvelle-extension-mega-evolution-regne-delta',
        'https://www.pokemon.com/fr/actualites/participez-a-un-evenement-davant-premiere-pour-lextension-mega-evolution-regne-delta-du-jcc-pokemon',
        'https://www.play-in.com/fr/articles/3-pokemon/tout-savoir-sur-l-extension-pokemon-me06-mega-evolution-regne-delta']),
    ('ANNIV30', '30ᵉ Anniversaire', '2026-09-16', false, ARRAY[
        'https://www.pokemon.com/fr/actualites/jcc-pokemon-produits-30-anniversaire',
        'https://www.pokemon.com/fr/actualites/decouvrez-tous-les-produits-du-jcc-pokemon-qui-sortiront-en-septembre-2026',
        'https://www.nintendo-town.fr/2026/09/16/la-nouvelle-extension-du-jcc-30%E1%B5%89-anniversaire-sort-aujourdhui-pour-celebrer-30-ans-de-pokemon/']);

INSERT INTO pokeshop.suppliers (supplier_id, name, country, website, priority, status, access_mode, mapping_version, source_ref) VALUES
    ('asmodee_fr', 'Asmodee France', 'FR', 'https://www.asmodee.fr/contact/', 1, 'PISTE', 'AUCUN',
     'asmodee_fr-template-2026-10-04', 'BP §2 [S1], consulté le 4.10.2026'),
    ('matoo_miao', 'Matoo et Miao', NULL, 'https://wholesale.miao.matoocorp.com/', 1, 'PISTE', 'AUCUN',
     'matoo_miao-template-2026-10-04', 'BP §2 [S2], consulté le 4.10.2026'),
    ('tcg_distribution', 'TCG Distribution', NULL, 'https://tcgdistribution.fr/contactez-nous.html', 1, 'PISTE', 'AUCUN',
     'tcg_distribution-template-2026-10-04', 'BP §2 [S3], consulté le 4.10.2026'),
    ('otakuworld', 'OtakuWorld', 'CH', 'https://b2b.otakuworld.ch/', 2, 'PISTE', 'AUCUN',
     'otakuworld-template-2026-10-04', 'BP §2 [S4] (portail pro suisse), consulté le 4.10.2026'),
    ('cardcosmos', 'CardCosmos', NULL, 'https://cardcosmos.ch/fr/pages/acces-b2b', 2, 'PISTE', 'AUCUN',
     'cardcosmos-template-2026-10-04', 'BP §2 [S5], consulté le 4.10.2026 ; pays réel d''expédition à obtenir');

COMMIT;
