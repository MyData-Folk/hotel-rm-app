#!/usr/bin/env python3
"""
Script de configuration des administrateurs pour HotelVision RM v2.0
Ce script permet de créer des utilisateurs administrateurs avec accès sécurisé
"""

import sys
import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

# Ajouter le répertoire parent au path pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import supabase
    from supabase import create_client, Client
except ImportError:
    print("Erreur: Le package supabase n'est pas installé.")
    print("Installez-le avec: pip install supabase")
    sys.exit(1)

class AdminSetup:
    def __init__(self, supabase_url: str, supabase_key: str):
        """
        Initialise le client Supabase
        
        Args:
            supabase_url: URL de votre instance Supabase
            supabase_key: Clé d'API de votre instance Supabase
        """
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.admin_users = []
        
    def create_admin_user(self, email: str, password: str, full_name: str = "", 
                         role: str = "admin", security_level: int = 1) -> Dict:
        """
        Crée un utilisateur administrateur
        
        Args:
            email: Email de l'administrateur
            password: Mot de passe de l'administrateur
            full_name: Nom complet de l'administrateur
            role: Rôle de l'administrateur (super_admin, admin, readonly_admin)
            security_level: Niveau de sécurité (1-5)
            
        Returns:
            Dict: Informations sur l'utilisateur créé
        """
        if role not in ["super_admin", "admin", "readonly_admin"]:
            raise ValueError(f"Rôle invalide: {role}. Doit être super_admin, admin ou readonly_admin")
            
        if not (1 <= security_level <= 5):
            raise ValueError(f"Niveau de sécurité invalide: {security_level}. Doit être entre 1 et 5")
        
        print(f"Création de l'administrateur: {email}")
        
        try:
            # Créer l'utilisateur dans auth.users
            auth_response = self.supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "full_name": full_name
                    }
                }
            })
            
            if auth_response.user:
                user_id = auth_response.user.id
                
                # Vérifier si l'utilisateur existe déjà dans la table admin_users
                existing_admin = self.supabase.table("admin_users").select("*").eq("id", user_id).execute()
                
                if not existing_admin.data:
                    # Ajouter l'utilisateur à la table admin_users
                    admin_data = {
                        "id": user_id,
                        "email": email,
                        "full_name": full_name,
                        "role": role,
                        "security_level": security_level,
                        "created_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat(),
                        "permissions": self._get_default_permissions(role)
                    }
                    
                    admin_response = self.supabase.table("admin_users").insert(admin_data).execute()
                    
                    if admin_response.data:
                        print(f"✅ Administrateur créé avec succès: {email}")
                        self.admin_users.append({
                            "id": user_id,
                            "email": email,
                            "role": role,
                            "security_level": security_level
                        })
                        
                        # Générer un token de sécurité pour la première connexion
                        self._generate_security_token(user_id, "recovery")
                        
                        return {
                            "success": True,
                            "user_id": user_id,
                            "email": email,
                            "role": role
                        }
                    else:
                        raise Exception(f"Échec de l'ajout à la table admin_users: {admin_response}")
                else:
                    print(f"⚠️  L'administrateur {email} existe déjà")
                    return {
                        "success": False,
                        "message": "L'administrateur existe déjà"
                    }
            else:
                raise Exception(f"Échec de la création de l'utilisateur: {auth_response}")
                
        except Exception as e:
            print(f"❌ Erreur lors de la création de l'administrateur: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_default_permissions(self, role: str) -> List[str]:
        """
        Retourne les permissions par défaut pour un rôle
        
        Args:
            role: Rôle de l'administrateur
            
        Returns:
            List[str]: Liste des permissions
        """
        if role == "super_admin":
            return ["view_users", "manage_users", "view_hotels", "manage_hotels", 
                   "view_reports", "generate_reports", "manage_security", 
                   "view_audit_logs", "manage_system"]
        elif role == "admin":
            return ["view_users", "view_hotels", "view_reports", "generate_reports", 
                   "view_audit_logs"]
        else:  # readonly_admin
            return ["view_users", "view_hotels", "view_reports", "view_audit_logs"]
    
    def _generate_security_token(self, user_id: str, token_type: str = "recovery") -> str:
        """
        Génère un token de sécurité pour un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            token_type: Type de token à générer
            
        Returns:
            str: Token généré
        """
        try:
            # Générer un token aléatoire
            token = str(uuid.uuid4())
            
            # Stocker le token hashé dans la base de données
            token_data = {
                "user_id": user_id,
                "token_type": token_type,
                "token_hash": self._hash_token(token),
                "expires_at": (datetime.utcnow() + 
                             (datetime.utcnow() - datetime.utcnow()).replace(days=7)).isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
            
            self.supabase.table("security_tokens").insert(token_data).execute()
            
            print(f"🔐 Token de sécurité généré pour {user_id}")
            return token
            
        except Exception as e:
            print(f"❌ Erreur lors de la génération du token: {str(e)}")
            return ""
    
    def _hash_token(self, token: str) -> str:
        """
        Hash un token de sécurité
        
        Args:
            token: Token à hasher
            
        Returns:
            str: Token hashé
        """
        import hashlib
        import base64
        
        # Générer un salt
        salt = os.urandom(16)
        
        # Hasher le token avec le salt
        key = hashlib.pbkdf2_hmac('sha256', token.encode('utf-8'), salt, 100000)
        
        # Retourner le token hashé avec le salt
        return base64.b64encode(salt + key).decode('utf-8')
    
    def create_super_admin(self, email: str, password: str, full_name: str = "") -> Dict:
        """
        Crée un super administrateur
        
        Args:
            email: Email du super administrateur
            password: Mot de passe du super administrateur
            full_name: Nom complet du super administrateur
            
        Returns:
            Dict: Informations sur le super administrateur créé
        """
        return self.create_admin_user(email, password, full_name, "super_admin", 5)
    
    def list_admin_users(self) -> List[Dict]:
        """
        Liste tous les utilisateurs administrateurs
        
        Returns:
            List[Dict]: Liste des administrateurs
        """
        try:
            response = self.supabase.table("admin_users").select("*").execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"❌ Erreur lors de la liste des administrateurs: {str(e)}")
            return []
    
    def update_admin_role(self, user_id: str, new_role: str) -> Dict:
        """
        Met à jour le rôle d'un administrateur
        
        Args:
            user_id: ID de l'utilisateur
            new_role: Nouveau rôle
            
        Returns:
            Dict: Résultat de la mise à jour
        """
        if new_role not in ["super_admin", "admin", "readonly_admin"]:
            raise ValueError(f"Rôle invalide: {new_role}")
        
        try:
            response = self.supabase.table("admin_users").update({
                "role": new_role,
                "permissions": self._get_default_permissions(new_role),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()
            
            if response.data:
                print(f"✅ Rôle mis à jour avec succès: {new_role}")
                return {"success": True, "role": new_role}
            else:
                raise Exception("Échec de la mise à jour du rôle")
                
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour du rôle: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def revoke_admin_access(self, user_id: str) -> Dict:
        """
        Révoque l'accès administrateur d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Dict: Résultat de la révocation
        """
        try:
            # Supprimer de la table admin_users
            response = self.supabase.table("admin_users").delete().eq("id", user_id).execute()
            
            if response.data:
                print(f"✅ Accès administrateur révoqué pour l'utilisateur: {user_id}")
                
                # Révoquer toutes les sessions
                self._revoke_all_sessions(user_id)
                
                return {"success": True}
            else:
                raise Exception("Échec de la révocation de l'accès")
                
        except Exception as e:
            print(f"❌ Erreur lors de la révocation de l'accès: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _revoke_all_sessions(self, user_id: str) -> None:
        """
        Révoque toutes les sessions d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
        """
        try:
            self.supabase.table("admin_sessions").update({
                "is_revoked": True,
                "is_active": False
            }).eq("user_id", user_id).execute()
            
            print(f"🔄 Sessions révoquées pour l'utilisateur: {user_id}")
            
        except Exception as e:
            print(f"❌ Erreur lors de la révocation des sessions: {str(e)}")
    
    def setup_security_policies(self) -> Dict:
        """
        Configure les politiques de sécurité par défaut
        
        Returns:
            Dict: Résultat de la configuration
        """
        try:
            policies = [
                {
                    "name": "admin_login_attempts",
                    "description": "Limite les tentatives de connexion admin",
                    "policy_type": "login",
                    "rules": {
                        "max_attempts": 3,
                        "lock_duration": "15 minutes",
                        "window": "1 hour"
                    }
                },
                {
                    "name": "admin_session_timeout",
                    "description": "Timeout des sessions admin",
                    "policy_type": "session",
                    "rules": {
                        "inactive_timeout": "30 minutes",
                        "max_session_duration": "8 hours"
                    }
                },
                {
                    "name": "admin_ip_restriction",
                    "description": "Restriction par IP pour admin",
                    "policy_type": "access",
                    "rules": {
                        "allow_multiple_ips": False,
                        "trusted_ips": ["127.0.0.1"]
                    }
                }
            ]
            
            for policy in policies:
                # Vérifier si la politique existe déjà
                existing = self.supabase.table("security_policies").select("*").eq("name", policy["name"]).execute()
                
                if not existing.data:
                    self.supabase.table("security_policies").insert(policy).execute()
                    print(f"✅ Politique de sécurité créée: {policy['name']}")
                else:
                    print(f"⚠️  La politique existe déjà: {policy['name']}")
            
            return {"success": True, "policies_created": len(policies)}
            
        except Exception as e:
            print(f"❌ Erreur lors de la configuration des politiques: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def export_admin_config(self, filename: str = "admin_config.json") -> str:
        """
        Exporte la configuration des administrateurs dans un fichier JSON
        
        Args:
            filename: Nom du fichier de sortie
            
        Returns:
            str: Chemin du fichier créé
        """
        try:
            config = {
                "generated_at": datetime.utcnow().isoformat(),
                "admin_users": self.admin_users,
                "security_policies": self.setup_security_policies(),
                "permissions": {
                    "super_admin": self._get_default_permissions("super_admin"),
                    "admin": self._get_default_permissions("admin"),
                    "readonly_admin": self._get_default_permissions("readonly_admin")
                }
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Configuration exportée dans: {filename}")
            return filename
            
        except Exception as e:
            print(f"❌ Erreur lors de l'export de la configuration: {str(e)}")
            return ""

def main():
    """
    Fonction principale du script
    """
    print("🔧 Script de configuration des administrateurs HotelVision RM v2.0")
    print("=" * 60)
    
    # Configuration par défaut
    config_file = "admin_config.json"
    
    # Charger la configuration existante si elle existe
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                supabase_url = config.get("supabase_url", "")
                supabase_key = config.get("supabase_key", "")
        except:
            supabase_url = ""
            supabase_key = ""
    else:
        supabase_url = input("URL de votre instance Supabase: ").strip()
        supabase_key = input("Clé d'API de votre instance Supabase: ").strip()
        
        # Sauvegarder la configuration
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({
                "supabase_url": supabase_url,
                "supabase_key": supabase_key,
                "created_at": datetime.utcnow().isoformat()
            }, f, indent=2)
    
    if not supabase_url or not supabase_key:
        print("❌ URL et clé Supabase sont requises")
        return
    
    try:
        # Initialiser le setup
        setup = AdminSetup(supabase_url, supabase_key)
        
        # Configuration des politiques de sécurité
        print("\n🔒 Configuration des politiques de sécurité...")
        setup.setup_security_policies()
        
        # Création des administrateurs
        print("\n👥 Création des administrateurs...")
        
        # Demander les informations pour le super administrateur
        super_admin_email = input("Email du super administrateur: ").strip()
        super_admin_password = input("Mot du super administrateur: ").strip()
        super_admin_name = input("Nom complet du super administrateur: ").strip()
        
        if not super_admin_email or not super_admin_password:
            print("❌ Email et mot de passe sont requis")
            return
        
        # Créer le super administrateur
        super_admin_result = setup.create_super_admin(
            super_admin_email, 
            super_admin_password, 
            super_admin_name
        )
        
        if super_admin_result.get("success"):
            print(f"✅ Super administrateur créé: {super_admin_email}")
            
            # Demander de créer d'autres administrateurs
            while True:
                create_more = input("\nCréer un autre administrateur? (y/N): ").strip().lower()
                if create_more not in ['y', 'yes']:
                    break
                
                admin_email = input("Email de l'administrateur: ").strip()
                admin_password = input("Mot de passe de l'administrateur: ").strip()
                admin_name = input("Nom complet de l'administrateur: ").strip()
                admin_role = input("Rôle (admin/readonly_admin) [admin]: ").strip().lower()
                
                if admin_role not in ['admin', 'readonly_admin']:
                    admin_role = 'admin'
                
                if admin_email and admin_password:
                    setup.create_admin_user(
                        admin_email, 
                        admin_password, 
                        admin_name, 
                        admin_role
                    )
                else:
                    print("❌ Email et mot de passe sont requis")
        
        # Lister les administrateurs créés
        print("\n📋 Liste des administrateurs:")
        admin_users = setup.list_admin_users()
        
        if admin_users:
            for admin in admin_users:
                print(f"  • {admin['email']} ({admin['role']})")
        else:
            print("  Aucun administrateur trouvé")
        
        # Exporter la configuration
        export_file = setup.export_admin_config()
        if export_file:
            print(f"\n💾 Configuration exportée: {export_file}")
        
        print("\n🎉 Configuration des administrateurs terminée!")
        
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
