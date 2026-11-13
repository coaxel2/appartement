# Recherche d'appartement à Bordeaux

Projet de veille automatique des annonces de location sur Bordeaux Métropole, piloté par une tâche planifiée Claude.

## Site web

Le dossier `site/` est un site statique déployé sur Vercel : il affiche les annonces trouvées avec leurs photos, les critères appliqués, et permet de noter chaque annonce (intéressant, contacté, visite prévue, refusé). Ce suivi est enregistré dans le navigateur. Vercel redéploie le site à chaque push de la recherche automatique.

## Dernier rapport

Voir [rapports/DERNIER.md](rapports/DERNIER.md). Chaque exécution ajoute aussi un rapport daté dans `rapports/`.

## Critères actuels

- Location, 700 € charges comprises maximum (les annonces jusqu'à 750 € sont signalées à part)
- T2 ou T3, 35 m² minimum
- Extérieur obligatoire : balcon, terrasse, loggia ou jardin
- Parking obligatoire : place, box ou garage
- Bordeaux et métropole, à 40 minutes maximum en transports en commun de chacun des deux lieux de travail :
  - 136 quai des Chartrons, Bordeaux
  - 127 rue de Turenne, Bordeaux

Pour modifier un critère, éditer `config/criteres.json`. Les temps de trajet estimés par commune sont dans `config/zones.json`.

## Fonctionnement

1. `outils/collecte_locservice.py` lit les pages publiques de LocService pour chaque commune et ouvre les fiches retenues.
2. Claude interroge la recherche web sur une vingtaine de sites (Leboncoin, SeLoger, PAP, Bien'ici, Logic-Immo, Le Figaro Immobilier, ParuVendu, Foncia, Orpi, Century 21, Laforêt, Square Habitat, 123loger, etc.) et lit les fiches accessibles.
3. `outils/annonces.py` fusionne les résultats dans `data/annonces.json`, retire les doublons publiés sur plusieurs sites, classe chaque annonce et produit le rapport.

Les sites protégés par un anti robot (Leboncoin, SeLoger, PAP, Logic-Immo) ne sont jamais contournés : seules les informations visibles dans les résultats de recherche sont utilisées. Leur fiche reste à ouvrir à la main depuis le lien du rapport.

## Classement des annonces

- **Correspond** : tous les critères sont confirmés. Le trajet peut rester une estimation à confirmer.
- **A vérifier** : une seule information manque ou dépasse légèrement (loyer entre 700 et 750 €, extérieur non précisé...).
- **Incomplète** : plusieurs informations manquent.
- **Ecartée** : au moins un critère n'est pas respecté.

## Lancer à la main

```bash
python3 outils/collecte_locservice.py /tmp/locservice.json
python3 outils/annonces.py ajouter /tmp/locservice.json
python3 outils/annonces.py rapport
```
