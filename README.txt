# Hotel RM App — Correctifs Monitor & Exports

## Inclus dans ce pack
- `main.py` : CORS regex, exports Excel/PDF, montages statiques `/logs` & `/backups`, logging fichier
- `admin_endpoints.py` : backup DB via `pg_dump`, protection `X-Admin-Token`
- `routes_monitoring.py` : `/monitor/health`, `/monitor/files`, `/monitor/logs/tail`
- `requirements.txt` : + `requests`, `reportlab`
- `Dockerfile` : + `postgresql-client`, dirs runtime, healthcheck
- `admin-monitor.html` : mini UI d’admin pour superviser et lancer les backups

## Déploiement
1. Montez ces répertoires dans Coolify (Directory mounts) :  
   - `/app/data`  ← `/data/coolify/applications/<ID_API>/data`  
   - `/app/backups` ← `/data/coolify/applications/<ID_API>/backups`
2. Variables d’environnement :  
   - `ADMIN_TOKEN=<votre_token>`  
   - `DATABASE_URL=postgresql://user:pass@hotel-db:5432/dbname`  
   - `DATA_DIR=/app/data`
3. Rebuild/Deploy
4. Ouvrir `admin-monitor.html` et tester : santé, fichiers, logs, backup.

## Exports
- Excel : POST `/export/excel` body `{"rows":[{...},...]}`
- PDF : POST `/export/pdf` body `{"rows":[{...},...], "title":"..."}`
