# Admin Console - HotelManager Pro
Domaine : https://admin.hotelmanager.fr
API : https://api.hotelmanager.fr

## Déploiement (Coolify - Static Site)
1) Déployer ce dossier tel quel sur votre service "Static Site" (admin.hotelmanager.fr)
2) Aucune variable d'environnement requise (front statique).
3) L'API doit être accessible en HTTPS et CORS activé pour admin.hotelmanager.fr.

## Endpoints (rappel)
- GET  /hotels
- POST /hotels
- POST /upload/config?hotel_id=...
- POST /upload/excel?hotel_id=...
- POST /export/simulation
- GET  /hotel/files?hotel_id=...
- GET  /monitor/health
- GET  /activity?limit=20

## Exemples cURL
# Lister les fichiers d’un hôtel
curl -s "https://api.hotelmanager.fr/hotel/files?hotel_id=folkestone-opera" | jq

# Upload d’un fichier config.json
curl -X POST -F "file=@config.json" "https://api.hotelmanager.fr/upload/config?hotel_id=folkestone-opera"

# Upload d’un Excel
curl -X POST -F "file=@tarifs.xlsx" "https://api.hotelmanager.fr/upload/excel?hotel_id=folkestone-opera"

# Générer un export Excel (simulation)
curl -X POST -H "Content-Type: application/json"   -d '{"simulation_info":{"hotel_id":"folkestone-opera"},"results":[],"summary":{}}'   "https://api.hotelmanager.fr/export/simulation"

## Notes
- L'ouverture directe des fichiers Excel dans l'onglet se fait via /hotel/files/download (prévoir l'endpoint backend de téléchargement/stream).
- Pour limiter les CORS, autorisez admin.hotelmanager.fr sur l'API.
