# hotel-rm-app

Application de Revenue Management (RM) pour hôtels construite autour d'une API FastAPI et de deux frontaux statiques (`frontend/` pour les utilisateurs et `admin/` pour la supervision).

## Fonctionnalités principales

- Import de données de planning (Excel / CSV) et de configuration (JSON) par hôtel.
- Gestion multi-hôtels avec activation/désactivation et historique d'activités centralisé.
- Simulation tarifaire avancée incluant remises partenaires, promotions et commissions.
- Consultation des disponibilités par période et type de chambre.
- Export des simulations au format Excel.
- Monitoring de santé de l'API et des fichiers stockés.

## Prérequis

- Python 3.10+
- SQLite (par défaut) ou une base PostgreSQL accessible via `DATABASE_URL`.

## Installation et exécution

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Variables d'environnement utiles :

- `DATABASE_URL` : chaîne de connexion SQLModel (SQLite par défaut).
- `DATA_DIR` : chemin de stockage des fichiers importés (`./data` par défaut).

## Tests manuels

Quelques points à vérifier après modifications :

1. Création d'un hôtel (`POST /hotels`).
2. Import d'un fichier de planning (`POST /upload/excel`).
3. Import d'une configuration (`POST /upload/config`).
4. Simulation tarifaire (`POST /simulate`).
5. Export Excel (`POST /export/simulation`).

## Structure du projet

- `main.py` : API FastAPI, modèles SQLModel et logique métier principale.
- `frontend/` : interface utilisateur statique orientée simulation.
- `admin/` : interface statique simplifiée pour l'administration.
- `requirements.txt` : dépendances Python.
- `Dockerfile` : image de déploiement basée sur Uvicorn/Gunicorn.

## Contribution

Merci de respecter une couverture de tests minimale et de documenter les endpoints ajoutés dans ce fichier.
