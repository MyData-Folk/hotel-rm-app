# 🛡️ Configuration Supabase pour HotelVision RM v2.0

Ce guide explique comment configurer votre base de données Supabase avec un système d'authentification sécurisé et un accès administrateur robuste pour votre application HotelVision RM.

## 📁 Structure des fichiers

```
supabase/
├── auth_setup.sql              # Configuration de base d'authentification
├── admin_access.sql            # Configuration de l'accès administrateur sécurisé
├── setup_admin.py              # Script Python pour créer les administrateurs
└── README.md                   # Ce guide
```

## 🚀 Étape 1: Exécuter les scripts SQL

### 1.1. Configuration de l'authentification de base

```bash
# Se connecter à votre base de données Supabase
# Vous pouvez utiliser l'interface Supabase SQL Editor ou psql

# Exécuter le script d'authentification
psql "postgresql://[USER]:[PASSWORD]@[HOST]:[PORT]/[DATABASE]" -f supabase/auth_setup.sql
```

**Contenu du script `auth_setup.sql`:**
- Tables pour les profils utilisateurs étendus
- Système de logging des sessions
- Protection contre les attaques par force brute
- Triggers automatiques pour la création de profils
- Fonctions de sécurité avancées
- Vues de monitoring

### 1.2. Configuration de l'accès administrateur

```bash
# Exécuter le script d'accès administrateur
psql "postgresql://[USER]:[PASSWORD]@[HOST]:[PORT]/[DATABASE]" -f supabase/admin_access.sql
```

**Contenu du script `admin_access.sql`:**
- Tables administratives sécurisées
- Système de permissions granulaires
- Audit complet des activités
- Gestion des sessions administratives
- Politiques de sécurité RLS renforcées
- Support du 2FA et tokens de sécurité

## 🛠️ Étape 2: Création des administrateurs

### 2.1. Prérequis

```bash
# Installer les dépendances requises
pip install supabase python-dotenv

# Ou installer depuis le requirements.txt
pip install -r requirements.txt
```

### 2.2. Configuration du script

Le script `setup_admin.py` peut utiliser un fichier de configuration:

```json
{
  "supabase_url": "https://votre-projet.supabase.co",
  "supabase_key": "votre-clé-anonyme",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 2.3. Exécution du script

```bash
# Exécuter le script de configuration
python supabase/setup_admin.py
```

Le script vous guidera à travers:
1. La connexion à votre instance Supabase
2. La configuration des politiques de sécurité
3. La création du super administrateur
4. La création d'autres administrateurs (optionnel)
5. L'export de la configuration

### 2.4. Exemple d'utilisation programmatique

```python
from supabase import create_client
from setup_admin import AdminSetup

# Initialiser le client
supabase_url = "https://votre-projet.supabase.co"
supabase_key = "votre-clé-anonyme"
setup = AdminSetup(supabase_url, supabase_key)

# Créer un super administrateur
result = setup.create_super_admin(
    email="admin@hotelvision.com",
    password="MotDePasseTrèsSécurisé123!",
    full_name="Administrateur Principal"
)

# Lister les administrateurs
admins = setup.list_admin_users()
for admin in admins:
    print(f"{admin['email']} ({admin['role']})")

# Mettre à jour un rôle
setup.update_admin_role(user_id, "super_admin")

# Révoquer l'accès
setup.revoke_admin_access(user_id)
```

## 🔐 Étape 3: Configuration de la sécurité

### 3.1. Politiques de sécurité implémentées

#### Authentification renforcée
- **Limitation des tentatives**: 5 tentatives en 1 heure pour les utilisateurs normaux
- **Protection admin**: 3 tentatives en 1 heure avec verrouillage de 15 minutes
- **2FA Support**: Tokens de sécurité pour l'authentification à deux facteurs
- **Changement de mot de passe**: Obligatoire périodiquement pour les administrateurs

#### Gestion des sessions
- **Timeout d'inactivité**: 30 minutes pour les sessions administratives
- **Durée maximale**: 8 heures par session
- **Révocation immédiate**: Possible pour les comptes compromis
- **Tracking complet**: Logging de toutes les activités

#### Contrôle d'accès granulaire
- **3 niveaux d'administrateurs**:
  - `super_admin`: Accès total au système
  - `admin`: Accès limité aux fonctionnalités administratives
  - `readonly_admin`: Accès en lecture seule

- **Permissions individuelles**:
  - `view_users`: Voir les utilisateurs
  - `manage_users`: Gérer les utilisateurs
  - `view_hotels`: Voir les hôtels
  - `manage_hotels`: Gérer les hôtels
  - `view_reports`: Voir les rapports
  - `generate_reports`: Générer des rapports
  - `manage_security`: Gérer la sécurité
  - `view_audit_logs`: Voir les logs d'audit
  - `manage_system`: Gérer le système

### 3.2. Politiques RLS (Row Level Security)

Le système implémente des politiques RLS strictes:

```sql
-- Exemple de politique pour les profils administrateurs
CREATE POLICY "Super admins can view all admin profiles" ON public.admin_users
    FOR SELECT USING (auth.jwt() ->> 'role' = 'super_admin');

CREATE POLICY "Users can view own profile" ON public.profiles
    FOR SELECT USING (auth.uid() = id);
```

## 📊 Étape 4: Monitoring et Audit

### 4.1. Vues de monitoring disponibles

#### Vue des utilisateurs actifs
```sql
-- active_users: Voir tous les utilisateurs actifs et leurs sessions
SELECT * FROM public.active_users;
```

#### Vue des sessions administratives
```sql
-- active_admin_sessions: Voir toutes les sessions admin actives
SELECT * FROM public.active_admin_sessions;
```

#### Vue des activités récentes
```sql
-- recent_admin_activity: Voir les activités administratives des 24 dernières heures
SELECT * FROM public.recent_admin_activity;
```

### 4.2. Fonctions de monitoring

#### Vérifier l'état de sécurité d'un utilisateur
```sql
-- Vérifier les tentatives de connexion
SELECT * FROM public.check_login_attempts('user@email.com', '192.168.1.1');

-- Vérifier les tentatives de connexion admin
SELECT * FROM public.check_admin_login_attempts('admin@hotelvision.com', '192.168.1.1');
```

#### Valider une session administrative
```sql
-- Valider une session admin
SELECT * FROM public.validate_admin_session('session-id');
```

## 🛡️ Étape 5: Bonnes pratiques de sécurité

### 5.1. Gestion des mots de passe

- **Longueur minimale**: 12 caractères
- **Complexité**: Lettres, chiffres, symboles
- **Rotation**: Changement tous les 90 jours pour les administrateurs
- **Historique**: Pas de réutilisation des  5 derniers mots de passe

### 5.2. Protection contre les attaques

- **Force brute**: Protection avec verrouillage progressif
- **SQL Injection**: Utilisation de paramètres préparés
- **XSS**: Validation des entrées et échappement
- **CSRF**: Tokens CSRF pour les requêtes sensibles

### 5.3. Surveillance

- **Logs complets**: Toutes les actions sensibles sont loggées
- **Alertes**: Notification pour activités suspectes
- **Audit régulier**: Revue mensuelle des accès et permissions
- **Backup**: Sauvegardes régulières des données sensibles

## 🔧 Étape 6: Intégration avec l'application

### 6.1. Configuration de l'application

Mettre à jour votre fichier `.env`:

```env
# Configuration Supabase
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_JWT_SECRET=votre-secret-jwt-personnalisé

# Configuration de sécurité
ADMIN_SECURITY_LEVEL=5
SESSION_TIMEOUT=1800  # 30 minutes en secondes
MAX_LOGIN_ATTEMPTS=3
LOGIN_LOCKOUT_DURATION=900  # 15 minutes en secondes
```

### 6.2. Exemple d'utilisation dans FastAPI

```python
from fastapi import Depends, HTTPException, status
from supabase import create_client
from jose import JWTError, jwt

# Configuration Supabase
SUPABASE_URL = "https://votre-projet.supabase.co"
SUPABASE_KEY = "votre-clé-anonyme"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

async def get_current_user_admin(token: str):
    """Vérifier l'accès administrateur"""
    try:
        # Vérifier le token JWT
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide"
            )
        
        # Vérifier les permissions administratives
        admin_user = supabase.table("admin_users").select("*").eq("id", user_id).execute()
        
        if not admin_user.data or admin_user.data[0]["role"] != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé"
            )
        
        return admin_user.data[0]
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide"
        )

# Utilisation dans un endpoint
@app.get("/admin/dashboard")
async def admin_dashboard(current_user: dict = Depends(get_current_user_admin)):
    return {"message": "Bienvenue dans le tableau de bord admin"}
```

### 6.3. Gestion des sessions

```python
async def create_admin_session(user_id: str):
    """Créer une session administrative"""
    session_data = {
        "user_id": user_id,
        "session_id": str(uuid.uuid4()),
        "session_token": str(uuid.uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(hours=8)).isoformat(),
        "last_activity": datetime.utcnow().isoformat(),
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent"),
        "access_level": 5
    }
    
    result = supabase.table("admin_sessions").insert(session_data).execute()
    return result.data[0] if result.data else None
```

## 🚨 Étape 7: Dépannage et support

### 7.1. Problèmes courants

#### Erreurs de connexion
```bash
# Vérifier la configuration réseau
ping votre-projet.supabase.co

# Vérifier les permissions
psql "postgresql://[USER]:[PASSWORD]@[HOST]:[PORT]/[DATABASE]" -c "\du"
```

#### Problèmes d'authentification
```sql
-- Vérifier les utilisateurs
SELECT * FROM auth.users WHERE email = 'user@example.com';

-- Vérifier les profils
SELECT * FROM public.profiles WHERE email = 'user@example.com';
```

#### Sessions bloquées
```sql
-- Révoquer toutes les sessions d'un utilisateur
UPDATE public.admin_sessions 
SET is_revoked = true, is_active = false 
WHERE user_id = 'user-id';
```

### 7.2. Logs de dépannage

```sql
-- Voir les tentatives de connexion récentes
SELECT * FROM public.login_attempts 
ORDER BY attempt_time DESC LIMIT 100;

-- Voir les activités administratives
SELECT * FROM public.admin_audit_logs 
ORDER BY timestamp DESC LIMIT 100;

-- Voir les erreurs de sécurité
SELECT * FROM public.admin_audit_logs 
WHERE severity IN ('warning', 'error', 'critical')
ORDER BY timestamp DESC LIMIT 50;
```

## 🔍 Étape 8: Maintenance et mise à jour

### 8.1. Mises à jour de sécurité

```bash
# Mettre à jour les politiques de sécurité
psql "postgresql://[USER]:[PASSWORD]@[HOST]:[PORT]/[DATABASE]" -f supabase/admin_access.sql

# Mettre à jour le script de configuration
python supabase/setup_admin.py
```

### 8.2. Sauvegardes

```bash
# Sauvegarde des données administratives
pg_dump -t public.admin_users -t public.admin_sessions -t public.admin_audit_logs hotelvision > admin_backup.sql

# Sauvegarde des politiques de sécurité
pg_dump -t public.security_policies -t public.admin_permissions hotelvision > security_backup.sql
```

### 8.3. Audit régulier

```sql
-- Audit des utilisateurs actifs
SELECT 
    u.email,
    u.role,
    u.last_login,
    COUNT(s.id) as active_sessions,
    COUNT(l.id) as failed_attempts
FROM public.admin_users u
LEFT JOIN public.admin_sessions s ON u.id = s.user_id
LEFT JOIN public.login_attempts l ON u.email = l.email
GROUP BY u.id, u.email, u.role, u.last_login;

-- Audit des permissions
SELECT 
    u.email,
    ap.name as permission,
    up.granted_at,
    up.expires_at
FROM public.user_permissions up
JOIN public.admin_users u ON up.user_id = u.id
JOIN public.admin_permissions ap ON up.permission_id = ap.id
ORDER BY u.email, ap.name;
```

---

## 📝 Documentation complète

Pour plus d'informations sur:
- **Row Level Security**: https://supabase.com/docs/guides/database/postgres/row-level-security
- **Authentification**: https://supabase.com/docs/guides/auth
- **API Reference**: https://supabase.com/docs/reference/javascript

---

## 🆘 Support technique

Pour obtenir de l'aide:
1. Consultez la documentation officielle Supabase
2. Vérifiez les logs d'erreur
3. Contactez l'équipe de développement
4. Ouvrez une issue sur GitHub

---

**⚠️ Attention**: Ce système de sécurité est conçu pour une production. Testez toujours en environnement de développement avant de déployer en production.
