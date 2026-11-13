# Recherche d'appartement à Bordeaux

Ce dépôt est piloté par une tâche planifiée Claude. A chaque exécution, Claude cherche de nouvelles annonces de location correspondant aux critères, les enregistre, puis publie un rapport.

## Règles de rédaction

- Rédiger en français.
- Ne jamais utiliser de tiret cadratin ni de tiret demi cadratin.
- Mise en forme sobre : titres, sous titres, listes classiques, pas de séparateurs graphiques.
- Toujours citer la source (lien vers l'annonce) et inclure un maximum de photos.

## Fichiers

- `config/criteres.json` : critères de recherche (source de vérité, les lire à chaque exécution).
- `config/zones.json` : temps de trajet estimés par commune ou quartier vers les deux lieux de travail.
- `config/sites.json` : sites à couvrir, requêtes types, communes à balayer.
- `data/annonces.json` : toutes les annonces déjà vues (ne pas éditer à la main, passer par l'outil).
- `outils/annonces.py` : fusion, dédoublonnage, évaluation, rapport.
- `rapports/DERNIER.md` et `rapports/AAAA-MM-JJ.md` : rapports générés.

## Procédure d'une exécution

1. Lire `config/criteres.json`, `config/sites.json` et lancer `python3 outils/annonces.py stats`.
2. Collecte directe : `python3 outils/collecte_locservice.py /tmp/locservice.json` puis `python3 outils/annonces.py ajouter /tmp/locservice.json`. Relire les extraits `exterieur` et `parking` des annonces retenues et corriger si l'outil s'est trompé.
3. Recherche large avec WebSearch : pour chaque site de `config/sites.json` et chaque commune de la liste, combiner les requêtes types (au moins 25 requêtes au total, en variant T2 / T3, balcon / terrasse / jardin, parking / garage, et en ajoutant le mois en cours pour favoriser les annonces récentes). Ajouter quelques requêtes sans site imposé pour découvrir d'autres sources (agences locales, sites de particuliers, résidences).
4. Ecarter tout de suite les résultats manifestement hors critères (vente, colocation, loyer nettement trop élevé, studio, commune trop éloignée).
5. Pour chaque candidat restant non présent dans `data/annonces.json` : ouvrir la page avec WebFetch (ou `curl` si WebFetch échoue) et extraire loyer, charges, surface, pièces, adresse ou quartier, extérieur, parking, disponibilité, date de publication, toutes les URLs de photos, contact. Si la page est inaccessible (site protégé par un anti robot comme Leboncoin, SeLoger, PAP), utiliser uniquement les informations de l'extrait de recherche et laisser les champs inconnus à null. Ne jamais contourner une protection anti robot, un captcha ou une API non publique.
6. Pour les annonces en zone `limite` ou hors table de zones, estimer le trajet réel vers les deux adresses de travail (recherche web d'itinéraire TBM ou connaissance du réseau tram), renseigner `ville`, `quartier` et `code_postal` le plus précisément possible, et si le trajet a pu être établi, le noter dans `trajet_verifie_min` (le plus long des deux trajets).
7. Ecrire les annonces dans un fichier JSON temporaire (liste d'objets au format décrit en tête de `outils/annonces.py`) puis lancer `python3 outils/annonces.py ajouter <fichier>`.
8. Si une annonce déjà connue n'existe plus (page 404 ou mention louée), la marquer `"expiree": true` en la réajoutant avec ce champ.
9. Lancer `python3 outils/annonces.py rapport`.
10. Commit des fichiers `data/` et `rapports/` avec un message du type `Recherche du AAAA-MM-JJ : N nouvelles annonces pertinentes`, puis push.
11. Terminer par un résumé court : nombre d'annonces nouvelles qui correspondent, les 3 meilleures avec lien, loyer, surface, ville, et une photo chacune.
