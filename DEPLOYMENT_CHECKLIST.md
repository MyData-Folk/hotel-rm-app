# Checklist de Déploiement HotelVision RM v2.0

## Phase 1 : Préparation du Déploiement GitHub

### ✅ Étape 1.1 : Configuration du Repository
- [ ] Créer un nouveau repository GitHub pour l'application
- [ ] Ajouter un fichier `.gitignore` approprié (Python, Node.js, etc.)
- [ ] Configurer les secrets GitHub :
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `JWT_SECRET_KEY`
  - `DATABASE_URL`
  - `API_KEYS`
- [ ] Configurer les GitHub Actions pour les tests automatisés
- [ ] Définir les règles de protection de branche (main branch protection)

### ✅ Étape 1.2 : Documentation du Code
- [ ] Mettre à jour le README.md avec :
  - Description complète de l'application
  - Instructions d'installation
  - Documentation des API
  - Guide de déploiement
- [ ] Ajouter la documentation de l'architecture
- [ ] Créer un fichier CONTRIBUTING.md
- [ ] Documenter les environnements de développement et production

### ✅ Étape 1.3 : Qualité du Code
- [ ] Exécuter les tests unitaires et d'intégration
- [ ] Vérifier la couverture de code (minimum 80%)
- [ ] Linting du code avec flake8/black pour Python
- [ ] Vérifier la sécurité des dépendances (`pip-audit` ou `npm audit`)
- [ ] Optimiser les performances de l'application

## Phase 2 : Configuration Coolify

### ✅ Étape 2.1 : Prérequis Coolify
- [ ] Avoir un serveur VPS/Réseau privé virtuel configuré
- [ ] Installer Coolify sur le serveur
- [ ] Configurer le domaine principal pour l'application
- [ ] Configurer les DNS pour les sous-domaines
- [ ] Créer les certificats SSL/TLS

### ✅ Étape 2.2 : Configuration des Services

#### Service Principal (Backend API)
- [ ] Configurer le service principal Python :
  - Image Docker : `python:3.11-slim`
  - Commande : `python main.py`
  - Port : `8000`
  - Variables d'environnement :
    - `SUPABASE_URL`
    - `SUPABASE_ANON_KEY`
    - `SUPABASE_SERVICE_ROLE_KEY`
    - `JWT_SECRET_KEY`
    - `DATABASE_URL`
    - `API_KEYS`
  - Répertoire de travail : `/app`
  - Build Command : `pip install -r requirements.txt`
  - Health Check : `/health`

#### Service Frontend (Interface Utilisateur)
- [ ] Configurer le service frontend :
  - Build Command : `npm install && npm run build`
  - Publish Directory : `build/`
  - Port : `80`
  - Domaine : `hotelvision.e-hotelmanager.com`
  - Force SSL : Activé

#### Service Administration
- [ ] Configurer le service d'administration :
  - Build Command : `npm install`
  - Publish Directory : `./`
  - Port : `80`
  - Domaine : `admin-hv.e-hotelmanager.com`
  - Force SSL : Activé

#### Service Supabase (Base de données)
- [ ] Configurer Supabase :
  - Utiliser l'instance Supabase existante
  - Configurer les connexions sécurisées
  - Configurer les répliques de base de données
  - Configurer les sauvegardes automatiques

### ✅ Étape 2.3 : Configuration des Réseaux
- [ ] Créer un réseau privé interne entre les services
- [ ] Configurer les règles de pare-feu :
  - Autoriser les communications internes
  - Restreindre l'accès externe aux ports nécessaires
  - Configurer les règles de sécurité
- [ ] Configurer les load balancers si nécessaire
- [ ] Mettre en place un proxy inversé (Nginx)

### ✅ Étape 2.4 : Configuration de la Sécurité
- [ ] Configurer les certificats SSL/TLS pour tous les domaines
- [ ] Mettre en place des règles de sécurité :
  - Limiter les taux de requêtes
  - Configurer la sécurité des headers
  - Mettre en place le HSTS
- [ ] Configurer les backups automatiques :
  - Backup quotidien de la base de données
  - Backup hebdomadaire des fichiers
  - Stockage sécurisé des backups

## Phase 3 : Déploiement et Monitoring

### ✅ Étape 3.1 : Déploiement Initial
- [ ] Déployer le backend API
- [ ] Vérifier que l'API est accessible
- [ ] Déployer le frontend principal
- [ ] Vérifier que l'interface utilisateur fonctionne
- [ ] Déployer l'interface d'administration
- [ ] Tester toutes les fonctionnalités

### ✅ Étape 3.2 : Configuration du Monitoring
- [ ] Configurer le monitoring avec UptimeRobot ou similaire
- [ ] Mettre en place des alertes :
  - Erurs critiques
  - Disponibilité inférieure à 99%
  - Utilisation CPU/Mémoire élevée
- [ ] Configurer les logs centraux (ELK Stack ou similaire)
- [ ] Mettre en place des dashboards de monitoring

### ✅ Étape 3.3 : Tests Post-Déploiement
- [ ] Effectuer des tests de charge
- [ ] Vérifier la sécurité avec OWASP ZAP ou similaire
- [ ] Tester la récupération d'urgence
- [ ] Vérifier les backups
- [ ] Tester la mise à jour de l'application

## Phase 4 : Maintenance et Mises à Jour

### ✅ Étape 4.1 : Configuration des Mises à Jour Automatisées
- [ ] Configurer les GitHub Actions pour le déploiement automatisé
- [ ] Mettre en place un pipeline CI/CD
- [ ] Configurer les tests automatisés avant déploiement
- [ ] Configurer les rollbacks automatiques en cas d'échec

### ✅ Étape 4.2 : Documentation de Production
- [ ] Créer une documentation technique de production
- [ ] Documenter les procédures d'intervention
- [ ] Créer un plan de reprise après sinistre
- [ ] Documenter les performances attendues

### ✅ Étape 4.3 : Suivi et Amélioration
- [ ] Mettre en place des alertes proactives
- [ ] Configurer les rapports de performance
- [ ] Planifier les audits de sécurité réguliers
- [ ] Mettre à jour régulièrement les dépendances

## Checklist Finale

### ✅ Vérification Définitive
- [ ] Tous les services sont-ils accessibles ?
- [ ] Tous les domaines fonctionnent-ils correctement ?
- [ ] La sécurité est-elle configurée ?
- [ ] Les backups fonctionnent-ils ?
- [ ] Le monitoring est-il actif ?
- [ ] Tous les tests passent-ils ?
- [ ] La documentation est-elle à jour ?

## Ressources Requises

### Outils nécessaires :
- [ ] GitHub Enterprise (ou GitHub Pro)
- [ ] Coolify (self-hosted ou cloud)
- [ ] Serveur VPS (minimum 4GB RAM, 2CPU)
- [ ] Domaine principal et sous-domaines
- [ ] Certificats SSL/TLS
- [ ] Service de monitoring
- [ ] Service de backup

### Coûts estimés :
- [ ] Hébergement VPS : ~$20-50/mois
- [ ] Noms de domaine : ~$15-30/an
- [ ] Certificats SSL : Optionnel (Let's Encrypt gratuit)
- [ ] Monitoring : ~$10-30/mois
- [ ] Backup : ~$10-20/mois

### Durée estimée :
- [ ] Configuration GitHub : 2-4 heures
- [ ] Configuration Coolify : 4-6 heures
- [ ] Tests et validation : 4-8 heures
- [ ] Documentation : 2-4 heures
- [ ] Total : 12-22 heures

---

**Date de création :** 12/10/2025
**Version :** 1.0
**Dernière mise à jour :** 12/10/2025
