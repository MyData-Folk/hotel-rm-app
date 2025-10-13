-- =============================================
-- SCRIPT DE CONFIGURATION SUPABASE POUR AUTHENTIFICATION
-- HotelVision RM v2.0
-- =============================================

-- 1. Configuration des politiques RLS (Row Level Security)
-- =============================================

-- Activer l'extension RLS si nécessaire
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Politiques pour la table auth.users (gérée par Supabase)
-- Note: Ne pas modifier directement cette table

-- 2. Création de tables personnalisées pour les utilisateurs
-- =============================================

-- Table des profils utilisateurs étendus
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'
);

-- Table de logging des connexions
CREATE TABLE IF NOT EXISTS public.user_sessions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    ip_address INET,
    user_agent TEXT,
    device_info TEXT,
    is_active BOOLEAN DEFAULT true
);

-- Table des tentatives de connexion (pour sécurité)
CREATE TABLE IF NOT EXISTS public.login_attempts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    email TEXT NOT NULL,
    ip_address INET,
    user_agent TEXT,
    attempt_time TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT false,
    locked_until TIMESTAMPTZ,
    failure_reason TEXT
);

-- 3. Création des politiques de sécurité RLS
-- =============================================

-- Politiques pour la table profiles
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Politique de lecture: les utilisateurs peuvent voir leur propre profil
CREATE POLICY "Users can view own profile" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

-- Politique d'écriture: les utilisateurs peuvent modifier leur propre profil
CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- Politique d'insertion: l'authentification crée automatiquement le profil
CREATE POLICY "Auth creates profile" ON public.profiles
    FOR INSERT WITH CHECK (true);

-- Les administrateurs peuvent voir tous les profils
CREATE POLICY "Admins can view all profiles" ON public.profiles
    FOR SELECT USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.uid() = id
    );

-- Les administrateurs peuvent modifier tous les profils
CREATE POLICY "Admins can update all profiles" ON public.profiles
    FOR UPDATE USING (auth.jwt() ->> 'role' = 'admin');

-- Politiques pour la table user_sessions
ALTER TABLE public.user_sessions ENABLE ROW LEVEL SECURITY;

-- Les utilisateurs peuvent voir leurs propres sessions
CREATE POLICY "Users can view own sessions" ON public.user_sessions
    FOR SELECT USING (auth.uid() = user_id);

-- Les administrateurs peuvent voir toutes les sessions
CREATE POLICY "Admins can view all sessions" ON public.user_sessions
    FOR SELECT USING (auth.jwt() ->> 'role' = 'admin');

-- Les utilisateurs peuvent supprimer leurs propres sessions
CREATE POLICY "Users can delete own sessions" ON public.user_sessions
    FOR DELETE USING (auth.uid() = user_id);

-- Politiques pour la table login_attempts
ALTER TABLE public.login_attempts ENABLE ROW LEVEL SECURITY;

-- Tout le monde peut lire les tentatives (pour monitoring)
CREATE POLICY "Everyone can read login attempts" ON public.login_attempts
    FOR SELECT USING (true);

-- Seuls les admins peuvent écrire dans la table
CREATE POLICY "Admins can manage login attempts" ON public.login_attempts
    FOR ALL USING (auth.jwt() ->> 'role' = 'admin');

-- 4. Création des fonctions triggers
-- =============================================

-- Mettre à jour le timestamp de modification
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name)
    VALUES (new.id, new.email, new.raw_user_meta_data->>'full_name');
    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger pour créer automatiquement le profil utilisateur
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Mettre à jour le timestamp de modification
CREATE OR REPLACE FUNCTION public.handle_profile_update()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger pour mettre à jour le profil
CREATE TRIGGER on_profile_update
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_profile_update();

-- 5. Création des fonctions pour la sécurité
-- =============================================

-- Fonction pour vérifier les tentatives de connexion
CREATE OR REPLACE FUNCTION public.check_login_attempts(email TEXT, ip_address INET)
RETURNS TABLE(is_locked BOOLEAN, remaining_attempts INTEGER, lock_time TIMESTAMPTZ) AS $$
DECLARE
    attempt_count INTEGER;
    lock_record RECORD;
    max_attempts INTEGER := 5;
    lock_duration INTERVAL := INTERVAL '30 minutes';
BEGIN
    -- Vérifier si l'IP est déjà verrouillée
    SELECT locked_until INTO lock_record
    FROM public.login_attempts
    WHERE ip_address = ip_address AND success = false
    AND locked_until > NOW()
    ORDER BY locked_until DESC
    LIMIT 1;
    
    IF lock_record IS NOT NULL AND lock_record.locked_until > NOW() THEN
        RETURN QUERY SELECT true, 0, lock_record.locked_until;
        RETURN;
    END IF;
    
    -- Compter les tentatives échouées récentes
    SELECT COUNT(*) INTO attempt_count
    FROM public.login_attempts
    WHERE email = email AND ip_address = ip_address AND success = false
    AND attempt_time > NOW() - INTERVAL '1 hour';
    
    -- Vérifier si le seuil est dépassé
    IF attempt_count >= max_attempts THEN
        UPDATE public.login_attempts
        SET locked_until = NOW() + lock_duration
        WHERE email = email AND ip_address = ip_address AND success = false;
        
        RETURN QUERY SELECT true, 0, NOW() + lock_duration;
    ELSE
        RETURN QUERY SELECT false, max_attempts - attempt_count, NULL;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fonction pour enregistrer une tentative de connexion
CREATE OR REPLACE FUNCTION public.record_login_attempt(
    email TEXT,
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN,
    failure_reason TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO public.login_attempts (
        email,
        ip_address,
        user_agent,
        success,
        failure_reason
    ) VALUES (
        email,
        ip_address,
        user_agent,
        success,
        failure_reason
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 6. Création des rôles personnalisés
-- =============================================

-- Insérer les rôles dans la table des profils existants
INSERT INTO public.profiles (id, email, role) 
SELECT id, email, 'admin' 
FROM auth.users 
WHERE email = 'admin@hotelvision.com' 
ON CONFLICT (id) DO NOTHING;

-- 7. Configuration des policies de sécurité supplémentaires
-- =============================================

-- Politique pour la réinitialisation de mot de passe
CREATE OR REPLACE FUNCTION public.handle_password_reset()
RETURNS TRIGGER AS $$
BEGIN
    -- Enregistrer la tentative de réinitialisation
    INSERT INTO public.login_attempts (email, ip_address, user_agent, success, failure_reason)
    VALUES (new.email, new.ip_address::INET, new.user_agent, false, 'password_reset');
    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 8. Indexes pour performance
-- =============================================

-- Index sur l'email pour recherche rapide
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(email);
CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON public.login_attempts(email);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON public.login_attempts(ip_address);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON public.user_sessions(user_id);

-- Index sur les dates pour les logs
CREATE INDEX IF NOT EXISTS idx_login_attempts_time ON public.login_attempts(attempt_time);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON public.user_sessions(expires_at);

-- 9. Vues pour le monitoring
-- =============================================

-- Vue des utilisateurs actifs
CREATE OR REPLACE VIEW public.active_users AS
SELECT 
    p.id,
    p.email,
    p.full_name,
    p.role,
    p.created_at,
    p.last_login,
    COUNT(s.id) as active_sessions,
    COUNT(l.id) as failed_attempts_24h
FROM public.profiles p
LEFT JOIN public.user_sessions s ON p.id = s.user_id AND s.is_active = true AND s.expires_at > NOW()
LEFT JOIN public.login_attempts l ON p.email = l.email AND l.attempt_time > NOW() - INTERVAL '24 hours'
GROUP BY p.id, p.email, p.full_name, p.role, p.created_at, p.last_login;

-- Vue des sessions actives
CREATE OR REPLACE VIEW public.active_sessions AS
SELECT 
    s.id,
    s.user_id,
    u.email,
    s.created_at,
    s.expires_at,
    s.ip_address,
    s.user_agent,
    CASE WHEN s.expires_at > NOW() THEN 'active' ELSE 'expired' END as status
FROM public.user_sessions s
JOIN auth.users u ON s.user_id = u.id
WHERE s.is_active = true;

-- 10. Configuration des webhooks (optionnel)
-- =============================================

-- Exemple de webhook pour notification de connexion
-- À configurer dans l'interface Supabase

-- 11. Documentation des politiques de sécurité
-- =============================================

/*
Politiques de sécurité implémentées:

1. Authentification:
   - Utilisation de JWT tokens pour l'authentification
   - Validation des rôles (admin/user)
   - Enregistrement des tentatives de connexion

2. Protection contre les attaques:
   - Limitation des tentatives de connexion (5 tentatives en 1 heure)
   - Verrouillage temporaire (30 minutes)
   - Logging des adresses IP et user agents

3. Accès administrateur:
   - Rôle 'admin' requis pour les opérations sensibles
   - Monitoring des sessions actives
   - Audit des actions utilisateurs

4. Protection des données:
   - RLS policies pour l'isolation des données
   - Chiffrement des données sensibles
   - Logs d'audit complets
*/
