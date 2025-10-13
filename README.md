# HotelVision RM v2.0

Système de gestion tarifaire et de réservation hôtelière multi-tenant avec simulation tarifaire avancée.

## 🚀 Caractéristiques

- **Gestion multi-tenant** avec architecture sécurisée
- **Simulation tarifaire** avancée avec commission et remises
- **Gestion des disponibilités** en temps réel
- **Authentification JWT** via Supabase
- **Interface web moderne** avec TailwindCSS
- **Import/Export** des données depuis Excel/CSV
- **Gestion des permissions** granulaire

## 📋 Prérequis

- Python 3.9+
- PostgreSQL 15+
- Docker (optionnel)
- Node.js (pour le développement frontend)

## 🛠️ Installation

### 1. Cloner le dépôt

```bash
git clone https://votre-repo/application_z_12102025.git
cd application_z_12102025
```

### 2. Configuration

#### Environnement

```bash
# Créer le fichier .env
cp .env.example .env

# Éditer le fichier .env avec vos configurations
nano .env
```

Exemple de configuration :
```env
DATABASE_URL=postgresql://user:password@localhost/hotelvision
DATA_DIR=/app/data
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_JWT_SECRET=votre-secret-jwt-personnalisé
PORT=8000
```

#### Base de données

```bash
# Créer la base de données PostgreSQL
createdb hotelvision

# Exécuter les migrations (si nécessaire)
python -c "from database import init_db; init_db()"
```

### 3. Installation des dépendances

```bash
pip install -r requirements.txt
```

### 4. Lancement de l'application

#### Développement

```bash
python main.py
```

#### Production avec Docker

```bash
docker-compose up -d
```

L'application sera accessible à `http://localhost:8000`

## 📊 Structure des données

### Fichiers de configuration JSON

Chaque hôtel nécessite deux fichiers de configuration :

#### 1. Configuration des données (`{hotel_id}_data.json`)

Structure attendue :
```json
{
  "report_generated_at": "Source des données",
  "rooms": {
    "Chambre Standard": {
      "stock": {
        "2024-01-01": 10,
        "2024-01-02": 8
      },
      "plans": {
        "Tarif Standard": {
          "2024-01-01": 120.00,
          "2024-01-02": 125.00
        },
        "Tarif Partenaire": {
          "2024-01-01": 115.00,
          "2024-01-02": 120.00
        }
      }
    }
  },
  "dates_processed": ["2024-01-01", "2024-01-02"]
}
```

#### 2. Configuration des partenaires (`{hotel_id}_config.json`)

Structure attendue :
```json
{
  "partners": {
    "Agence A": {
      "commission": 10,
      "defaultDiscount": {
        "percentage": 5,
        "excludePlansContaining": ["promo", "special"]
      },
      "codes": ["AGENCE_A", "PART_A"]
    },
    "Agence B": {
      "commission": 15,
      "defaultDiscount": {
        "percentage": 0
      }
    }
  },
  "displayOrder": {
    "rooms": ["Chambre Standard", "Chambre Deluxe", "Suite"]
  }
}
```

### Import de données depuis Excel/CSV

1. Accédez à l'interface d'administration
2. Sélectionnez l'hôtel cible
3. Uploadez votre fichier Excel/CSV
4. Les données seront automatiquement parsées et validées

## 🔐 Configuration de Supabase

1. Créez un projet Supabase
2. Récupérez l'URL et la clé anonyme
3. Configurez les variables d'environnement dans `.env`
4. (Optionnel) Configurez les tables utilisateurs dans Supabase

## 📱 Utilisation

### Connexion

1. Accédez à `http://localhost:8000/login`
2. Connectez-vous avec vos identifiants Supabase

### Tableau de bord principal

1. Après connexion, sélectionnez un hôtel
2. Les outils de simulation et de disponibilité sont activés
3. Configurez vos simulations avec différents partenaires et plans tarifaires

### Administration

1. Les administrateurs peuvent accéder à `/admin`
2. Gérer les hôtels
3. Accorder/révoquer des permissions utilisateur

## 🔧 API Endpoints

### Authentification
- `POST /api/verify-token` - Vérifier un token JWT

### Hôtels
- `GET /api/hotels/` - Lister les hôtels accessibles
- `POST /api/hotels/` - Créer un hôtel (admin)
- `DELETE /api/hotels/{hotel_id}` - Supprimer un hôtel (admin)

### Permissions
- `GET /api/permissions/` - Lister les permissions (admin)
- `POST /api/permissions/` - Créer une permission (admin)
- `DELETE /api/permissions/` - Révoquer une permission (admin)

### Simulations
- `POST /api/simulations/simulate` - Effectuer une simulation
- `GET /api/simulations/plans/partner` - Lister les plans par partenaire
- `POST /api/simulations/availability` - Vérifier les disponibilités

### Uploads
- `POST /api/uploads/excel` - Uploader des données Excel/CSV
- `POST /api/uploads/config` - Uploader une configuration JSON
- `GET /api/uploads/data` - Récupérer les données d'un hôtel
- `GET /api/uploads/config` - Récupérer la configuration d'un hôtel

## 🚀 Déploiement en production

### 1. Préparation

```bash
# Configurer les variables d'environnement
export DATABASE_URL="postgresql://user:password@db-host/db-name"
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_JWT_SECRET="your-production-secret"

# Configurer le reverse proxy (Nginx)
# Configuration SSL/TLS
```

### 2. Déploiement avec Docker

```bash
# Construire les images
docker-compose build

# Lancer les services
docker-compose up -d

# Vérifier les logs
docker-compose logs -f
```

### 3. Déploiement manuel

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer l'application
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 🔧 Maintenance

### Sauvegardes

```bash
# Sauvegarde de la base de données
pg_dump hotelvision > backup_$(date +%Y%m%d_%H%M%S).sql

# Sauvegarde des fichiers de données
tar -czf data_backup_$(date +%Y%m%d_%H%M%S).tar.gz /app/data
```

### Mises à jour

```bash
# Mettre à jour le code
git pull origin main

# Mettre à jour les dépendances
pip install -r requirements.txt --upgrade

# Appliquer les migrations
python -c "from database import init_db; init_db()"
```

## 🐛 Dépannage

### Problèmes courants

1. **Erreurs de connexion à la base de données**
   - Vérifier la configuration `DATABASE_URL`
   - S'assurer que PostgreSQL est en cours d'exécution

2. **Erreurs d'authentification**
   - Vérifier la configuration Supabase
   - S'assurer que les secrets sont corrects

3. **Problèmes de permissions**
   - Vérifier le rôle utilisateur
   - S'assurer que les permissions sont actives

### Logs

```bash
# Logs de l'application
docker-compose logs -f hotelvision-api

# Logs de la base de données
docker-compose logs -f db
```

## 📝 Licence

Ce projet est sous licence MIT.

## 🤝 Contribuer

1. Forkez le dépôt
2. Créez une branche pour votre fonctionnalité
3. Faites un commit de vos changements
4. Poussez vers votre branche
5. Créez une Pull Request

## 📞 Support

Pour toute question ou assistance :
- Ouvrez une issue sur GitHub
- Contactez l'équipe de développement
