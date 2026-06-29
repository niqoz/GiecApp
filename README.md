# Climat Commune — tasmax CMIP6

PWA statique pour consulter, par commune française, le maximum mensuel des
températures maximales journalières simulées (`tasmax`) dans NASA
NEX-GDDP-CMIP6 v2.0.

## Données

- Source : NASA NEX-GDDP-CMIP6 v2.0.
- Modèle MVP : `ACCESS-CM2`, membre `r1i1p1f1`.
- Variable : `tasmax`, convertie de Kelvin en degrés Celsius.
- Scénarios : `ssp126`, `ssp245`, `ssp585`.
- Années prévues : 2030 à 2100 tous les 5 ans.
- Zone prévue : France métropolitaine + Corse.

Le navigateur ne télécharge jamais de NetCDF. Le pipeline Python pré-calcule un
JSON statique `docs/climat_france_tasmax.json`, ensuite mis en cache par le
service worker.

L'application propose deux lectures :

- **Année** : le maximum mensuel des `tasmax` journaliers pour une année simulée.
- **Fenêtre** : la moyenne, mois par mois, des années disponibles dans la fenêtre
  choisie. Comme le JSON est échantillonné tous les 5 ans, la fenêtre 2030-2050
  moyenne les années 2030, 2035, 2040, 2045 et 2050.

## Générer le JSON complet

Installer les dépendances du pipeline :

```bash
python3 -m pip install -r pipeline/requirements.txt
```

Vérifier les fichiers attendus dans le cache local :

```bash
python3 pipeline/build_tasmax_france.py --check-files
```

Télécharger/cache les NetCDF annuels puis produire le JSON final :

```bash
python3 pipeline/build_tasmax_france.py --output docs/climat_france_tasmax.json
```

Les NetCDF sont stockés sous `data/raw/nex-gddp-cmip6/`, ignoré par Git. Pour
forcer une exécution sans téléchargement réseau :

```bash
python3 pipeline/build_tasmax_france.py --no-download
```

Recréer la fixture depuis le CSV existant :

```bash
python3 pipeline/build_tasmax_france.py \
  --sample-from-csv outputs/santa_maria_poggio_2035_tasmax_monthly_max.csv \
  --output docs/climat_france_tasmax.json \
  --pretty
```

## App et limites

La recherche de commune appelle côté client :

```text
https://geo.api.gouv.fr/communes?nom=<query>&fields=nom,code,centre,departement&boost=population&limit=8&format=json&geometry=centre
```

L'app choisit ensuite le point NEX le plus proche par distance haversine. Une
commune est donc approximée par une grille 0,25° (environ 25 km), et plusieurs
communes voisines peuvent partager le même point. Le MVP utilise un seul modèle :
ce n'est pas une moyenne multi-modèles.

## Déploiement GitHub Pages

Servir le dossier `docs/` depuis GitHub Pages. En local :

```bash
python3 -m http.server 8000 -d docs
```

Puis ouvrir `http://localhost:8000/`. Après un premier chargement, l'app shell,
les icônes et le JSON climatique sont disponibles hors-ligne via `sw.js`.
