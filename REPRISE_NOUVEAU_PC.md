# Reprise sur un autre PC

Ce projet contient une PWA statique dans `docs/` et un pipeline Python dans
`pipeline/` pour générer `docs/climat_france_tasmax.json` depuis NASA
NEX-GDDP-CMIP6.

## Ce qui est déjà présent

- App PWA : `docs/index.html`
- Manifeste PWA : `docs/manifest.webmanifest`
- Service worker offline : `docs/sw.js`
- Icônes : `docs/icon-192.png`, `docs/icon-512.png`
- Pipeline : `pipeline/build_tasmax_france.py`
- Dépendances pipeline : `pipeline/requirements.txt`
- JSON actuel : `docs/climat_france_tasmax.json`

Le JSON actuel peut être une fixture de test ou le jeu complet selon le dernier
commit récupéré. Vérifier `docs/climat_france_tasmax.json` : le jeu complet
contient les années 2030 à 2100 tous les 5 ans et environ 1 261 points.

## Installation sur le nouveau PC

Depuis le dossier du projet :

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -r pipeline/requirements.txt
```

## Générer les données complètes

Commande par défaut :

```bash
python3 pipeline/build_tasmax_france.py --output docs/climat_france_tasmax.json
```

Paramètres par défaut :

- Source : NASA NEX-GDDP-CMIP6 v2.0
- Modèle : `ACCESS-CM2`
- Membre : `r1i1p1f1`
- Variable : `tasmax`
- Scénarios : `ssp126`, `ssp245`, `ssp585`
- Années : 2030 à 2100 tous les 5 ans
- Zone : France métropolitaine + Corse

Le pipeline télécharge 45 fichiers NetCDF d'environ 247 Mo chacun, soit environ
11 Go. Les fichiers sont mis en cache dans `data/raw/nex-gddp-cmip6/`, qui est
ignoré par Git. Une relance reprend les fichiers déjà téléchargés.

Pour vérifier le cache sans télécharger :

```bash
python3 pipeline/build_tasmax_france.py --check-files
```

Pour forcer l'utilisation du cache et échouer si un fichier manque :

```bash
python3 pipeline/build_tasmax_france.py --no-download
```

## Lancer l'application localement

```bash
python3 -m http.server 8000 -d docs
```

Puis ouvrir :

```text
http://localhost:8000/
```

La recherche de commune utilise `geo.api.gouv.fr`. Hors ligne, l'app reste
consultable pour la dernière commune chargée si elle a déjà été mise en cache
par le service worker.

L'app propose une vue par année et une vue par fenêtre climatique. Les fenêtres
sont calculées côté navigateur en moyennant les années disponibles du JSON, par
exemple 2030-2050 = 2030, 2035, 2040, 2045 et 2050.

## Déploiement GitHub Pages

Configurer GitHub Pages pour servir le dossier `docs/`.

Après génération complète du JSON :

```bash
git add .gitignore README.md REPRISE_NOUVEAU_PC.md docs pipeline
git commit -m "Add climate commune PWA and tasmax pipeline"
git push
```

Si le dossier n'est pas encore un dépôt Git :

```bash
git init
git add .gitignore README.md REPRISE_NOUVEAU_PC.md docs pipeline scripts outputs
git commit -m "Add climate commune PWA and tasmax pipeline"
git branch -M main
git remote add origin <URL_DU_DEPOT>
git push -u origin main
```

Remplacer `<URL_DU_DEPOT>` par l'URL du dépôt GitHub.
