# hotel-rm-app

Application de Revenue Management pour hôtels.

## Modules clés

### API d'administration
- Endpoints regroupés sous `/admin` avec vérification du header `X-Admin-Token`.
- Le jeton doit être fourni via la variable d'environnement `ADMIN_TOKEN` avant de lancer l'application.
- Opérations disponibles : sauvegarde PostgreSQL, consultation des logs, exécution SQL en lecture et déclenchement d'un redeploy Coolify.

### API de monitoring
- Router monté sous `/monitor` pour exposer les stubs de supervision (liste d'hôtels, statut des fichiers, simulation tarifaire).
- Permet de brancher facilement des implémentations métier quand elles seront prêtes.

### Interfaces web
- `admin/index.html` : tableau de bord principal avec accès rapide au module monitoring.
- `admin/monitor.html` : interface dédiée aux outils admin/monitoring reposant sur les routes ci-dessus.

## Démarrer l'application localement

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_TOKEN="votre_token_admin"
uvicorn main:app --host 0.0.0.0 --port 8000
```

Les endpoints sont ensuite disponibles sur `http://localhost:8000`. Le module admin nécessite systématiquement l'en-tête `X-Admin-Token` avec la valeur du jeton configuré.
