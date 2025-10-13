# Guide Simple pour Exécuter les Scripts SQL avec Supabase Local

## 📋 Introduction

Ce guide explique comment exécuter les scripts SQL de votre projet HotelVision RM v2.0 avec **Supabase Local** (pas de cloud, utilisation des schémas).

## 🎯 Fichiers SQL à Exécuter

### **Fichiers Principaux**
- `supabase/auth_setup.sql` - Configuration de l'authentification
- `supabase/admin_access.sql` - Permissions administratives
- `supabase/admin_control_tables.sql` - Tables de contrôle

---

## 🔧 Méthode 1 : Via Supabase CLI (Recommandé)

### Étape 1 : Démarrer Supabase Local
```bash
# Si vous avez déjà un projet Supabase local
npx supabase start

# Si vous voulez créer un nouveau projet local
npx supabase init
# Suivre les instructions, puis :
npx supabase start
```

### Étape 2 : Accéder à l'éditeur SQL
```bash
# Ouvrir l'éditeur SQL dans votre terminal
npx supabase db shell
```

### Étape 3 : Exécuter les fichiers SQL (un par un)
Dans le shell SQL :

```sql
-- Charger et exécuter le premier fichier
\i supabase/auth_setup.sql

-- Attendre la fin de l'exécution, puis :
\i supabase/admin_access.sql

-- Attendre la fin de l'exécution, puis :
\i supabase/admin_control_tables.sql

-- Quitter le shell
\q
```

---

## 🐍 Méthode 2 : Via Script Python (Automatisé)

### Étape 1 : Prérequis
```bash
# Installer les dépendances
pip install supabase python-dotenv

# Démarrer Supabase local
npx supabase start
```

### Étape 2 : Configurer les variables d'environnement
Créez un fichier `.env` :
```env
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU
SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
```

### Étape 3 : Exécuter le script
```bash
python supabase/setup_admin.py
```

### Étape 4 : Vérifier l'exécution
Le script affichera :
```
✅ Auth setup exécuté avec succès
✅ Admin access configuré avec succès  
✅ Control tables créées avec succès
🎉 Toutes les configurations sont prêtes !
```

---

## 💻 Méthode 3 : Via Ligne de Commande Directe

### Pour Linux/macOS :

```bash
# Démarrer Supabase local
npx supabase start

# Exécuter chaque fichier dans le shell
npx supabase db shell -c "\i supabase/auth_setup.sql"
npx supabase db shell -c "\i supabase/admin_access.sql"  
npx supabase db shell -c "\i supabase/admin_control_tables.sql"
```

### Pour Windows :

```bash
# Démarrer Supabase local
npx supabase start

# Exécuter via PowerShell
npx supabase db shell
# Dans le shell SQL :
\i supabase/auth_setup.sql
\i supabase/admin_access.sql
\i supabase/admin_control_tables.sql
\q
```

---

## 🛡️ Méthode 4 : Via Interface Graphique (Facile)

### Utiliser Supabase Studio :

1. **Démarrer Supabase local** :
   ```bash
   npx supabase start
   ```

2. **Ouvrir Supabase Studio** :
   ```bash
   npx supabase studio
   ```

3. **Exécuter les scripts** :
   - Aller dans l'onglet **SQL**
   - Cliquer sur **New query**
   - Copier/coller chaque fichier SQL
   - Cliquer sur **Run** pour chaque fichier

**Ordre important** :
1. `auth_setup.sql`
2. `admin_access.sql`
3. `admin_control_tables.sql`

---

## 🔍 Vérification des Résultats

### Après exécution, vérifiez :

#### 1. **Schémas créés** :
```sql
-- Lister tous les schémas
SELECT schema_name FROM information_schema.schemata 
WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'public');
```

#### 2. **Tables créées** :
```sql
-- Lister les tables dans le schéma admin
SELECT tablename FROM pg_tables 
WHERE schemaname = 'admin' 
ORDER BY tablename;
```

#### 3. **Vérifier les permissions** :
```sql
-- Vérifier les rôles
SELECT rolname FROM pg_roles WHERE rolname LIKE 'admin_%';

-- Vérifier les politiques
SELECT policyname, tablename FROM pg_policies 
WHERE tablename IN ('admin.hotels', 'admin.tariff_plans', 'admin.configurations');
```

#### 4. **Tester l'accès** :
```sql
-- Essayer d'insérer un test (devrait échouer sans droits)
INSERT INTO admin.admin_user_management (hotel_id, hotel_name, admin_email) 
VALUES ('test', 'Test Hotel', 'test@example.com');
```

---

## ⚠️ Erreurs Courantes et Solutions

### Erreur 1 : "Schema does not exist"
**Cause** : Schéma non créé
**Solution** : S'assurer d'exécuter `auth_setup.sql` en premier

### Erreur 2 : "Permission denied"
**Cause** : Mauvaise configuration des rôles
**Solution** : Vérifier que les scripts de permissions sont exécutés

### Erreur 3 : "Connection failed"
**Cause** : Supabase local non démarré
**Solution** : Exécuter `npx supabase start`

### Erreur 4 : "File not found"
**Cause** : Chemin incorrect vers les fichiers SQL
**Solution** : Vérifier que vous êtes dans le bon répertoire

### Erreur 5 : "Duplicate table"
**Cause** : Tables déjà créées
**Solution** : Ignorer l'erreur ou supprimer d'abord :
```sql
DROP SCHEMA admin CASCADE;
```

---

## 🎯 Conseils Importants

### 1. **Démarrer Supabase Local**
```bash
# À la racine de votre projet
npx supabase init
# Suivre les instructions (choisir les options par défaut)
npx supabase start
```

### 2. **Ordre d'exécution CRUCIAL**
NE JAMAIS changer cet ordre :
1. **`auth_setup.sql`** → Crée les schémas et rôles
2. **`admin_access.sql`** → Configure les permissions
3. **`admin_control_tables.sql`** → Crée les tables

### 3. **Vérifier l'état de Supabase Local**
```bash
# Vérifier si les services sont démarrés
npx supabase status

# Arrêter les services (si nécessaire)
npx supabase stop
```

### 4. **Gérer les services**
```bash
# Redémarrer les services
npx supabase restart

# Voir les logs
npx supabase logs db
```

---

## 🚀 Prochaines Étapes

### Après exécution réussie :

1. **Démarrer l'application** :
   ```bash
   python main.py
   ```

2. **Tester l'interface locale** :
   - Aller sur `http://localhost:3000` (frontend)
   - Aller sur `http://localhost:3001` (admin)

3. **Créer un hôtel test** :
   ```sql
   INSERT INTO admin.admin_user_management 
   VALUES ('hotel_test', 'Hôtel Test', 'admin@test.com');
   ```

4. **Vérifier les logs** :
   ```bash
   npx supabase logs db
   ```

---

## 📞 Dépannage Avancé

### Problème 1 : Les schémas ne sont pas créés
```sql
-- Vérifier les schémas existants
SELECT * FROM information_schema.schemata;

-- Créer manuellement si nécessaire
CREATE SCHEMA IF NOT EXISTS admin;
CREATE SCHEMA IF NOT EXISTS auth;
```

### Problème 2 : Les permissions ne fonctionnent pas
```sql
-- Vérifier les politiques existantes
SELECT * FROM pg_policies WHERE schemaname = 'admin';

-- Réinitialiser les permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA admin REVOKE ALL ON TABLES FROM PUBLIC;
GRANT ALL ON ALL TABLES IN SCHEMA admin TO admin_user;
```

### Problème 3 : L'application ne se connecte pas
```python
# Vérifier la configuration dans database.py
print("URL de base de données:", os.getenv('DATABASE_URL'))
print("URL Supabase:", os.getenv('SUPABASE_URL'))
```

### Problème 4 : Supabase Local ne démarre pas
```bash
# Vérifier les dépendances
node --version
npm --version

# Nettoyer et redémarrer
npx supabase stop
npx supabase start --debug
```

---

## 🔄 Réinitialisation Complète

Si vous voulez tout recommencer :

```bash
# Arrêter et nettoyer
npx supabase stop
npx supabase db reset

# Supprimer les volumes Docker
docker volume rm supabase_db_data supabase_storage_data

# Recréer tout
npx supabase start
# Puis exécuter les scripts SQL dans le bon ordre
```

---

## 🎯 Bonnes Pratiques

### 1. **Sauvegardes régulières**
```sql
-- Créer une sauvegarde des schémas
CREATE TABLE backup_admin_timestamp AS 
SELECT * FROM admin.admin_user_management LIMIT 0;
```

### 2. **Développement isolé**
```bash
# Créer un environnement de test
mkdir test-hotelvision
cd test-hotelvision
npx supabase init
```

### 3. **Monitoring**
```sql
-- Voir l'activité récente
SELECT query, state, duration 
FROM pg_stat_activity 
WHERE query LIKE '%INSERT%' OR query LIKE '%CREATE%';
```

---

## 📞 Support Supabase Local

### Documentation officielle :
- https://supabase.com/docs/guides/local-development

### Commandes utiles :
```bash
# Aide
npx supabase --help

# Documentation locale
npx supabase docs open

# Forum communauté
https://supabase.com/discuss
```

---

**Date du guide** : 13/10/2025
**Version** : 1.0
**Dernière mise à jour** : 13/10/2025
**Cible** : Supabase Local (sans cloud)
