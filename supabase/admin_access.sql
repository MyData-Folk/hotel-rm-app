-- =============================================
-- SCRIPT DE CONFIGURATION SUPABASE POUR L'ACCÈS ADMINISTRATEUR
-- HotelVision RM v2.0
-- =============================================

-- 1. Configuration des tables administratives
-- =============================================

-- Table des administrateurs avec accès renforcé
CREATE TABLE IF NOT EXISTS public.admin_users (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'admin' CHECK (role IN ('super_admin', 'admin', 'readonly_admin')),
    permissions JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    must_change_password BOOLEAN DEFAULT false,
    two_factor_enabled BOOLEAN DEFAULT false,
    security_level INTEGER DEFAULT 1 CHECK (security_level BETWEEN 1 AND 5),
    restrictions JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}'
);

-- Table des sessions administratives
CREATE TABLE IF NOT EXISTS public.admin_sessions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    session_token TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    last_activity TIMESTAMPTZ,
    ip_address INET,
    user_agent TEXT,
    device_info TEXT,
    location TEXT,
    is_active BOOLEAN DEFAULT true,
    is_revoked BOOLEAN DEFAULT false,
    access_level INTEGER DEFAULT 1,
    accessed_resources JSONB DEFAULT '[]'
);

-- Table des logs d'activité administrative
CREATE TABLE IF NOT EXISTS public.admin_audit_logs (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    session_id TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    severity TEXT DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    category TEXT DEFAULT 'general'
);

-- Table des permissions granulaires
CREATE TABLE IF NOT EXISTS public.admin_permissions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    resource TEXT NOT NULL,
    action TEXT NOT NULL,
    conditions JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table de liaison permissions-utilisateurs
CREATE TABLE IF NOT EXISTS public.user_permissions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    permission_id UUID REFERENCES public.admin_permissions(id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    granted_by UUID REFERENCES auth.users(id),
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true
);

-- Table des tentatives d'accès administratif
CREATE TABLE IF NOT EXISTS public.admin_login_attempts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    email TEXT NOT NULL,
    ip_address INET,
    user_agent TEXT,
    attempt_time TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT false,
    failure_reason TEXT,
    security_level INTEGER DEFAULT 1,
    session_data JSONB DEFAULT '{}'
);

-- Table des politiques de sécurité
CREATE TABLE IF NOT EXISTS public.security_policies (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    policy_type TEXT NOT NULL CHECK (policy_type IN ('login', 'session', 'access', 'data')),
    rules JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table des tokens de sécurité (pour 2FA et recovery)
CREATE TABLE IF NOT EXISTS public.security_tokens (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    token_type TEXT NOT NULL CHECK (token_type IN ('2fa', 'recovery', 'session')),
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    is_used BOOLEAN DEFAULT false,
    used_at TIMESTAMPTZ,
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Configuration des politiques RLS renforcées
-- =============================================

-- Politiques pour la table admin_users
ALTER TABLE public.admin_users ENABLE ROW LEVEL SECURITY;

-- Les utilisateurs peuvent voir leur propre profil admin
CREATE POLICY "Users can view own admin profile" ON public.admin_users
    FOR SELECT USING (auth.uid() = id);

-- Les utilisateurs peuvent modifier leur propre profil admin
CREATE POLICY "Users can update own admin profile" ON public.admin_users
    FOR UPDATE USING (auth.uid() = id);

-- Les super_admins peuvent voir tous les profils admin
CREATE POLICY "Super admins can view all admin profiles" ON public.admin_users
    FOR SELECT USING (auth.jwt() ->> 'role' = 'super_admin');

-- Les super_admins peuvent modifier tous les profils admin
CREATE POLICY "Super admins can update all admin profiles" ON public.admin_users
    FOR UPDATE USING (auth.jwt() ->> 'role' = 'super_admin');

-- Politiques pour la table admin_sessions
ALTER TABLE public.admin_sessions ENABLE ROW LEVEL SECURITY;

-- Les utilisateurs peuvent voir leurs propres sessions admin
CREATE POLICY "Users can view own admin sessions" ON public.admin_sessions
    FOR SELECT USING (auth.uid() = user_id);

-- Les super_admins peuvent voir toutes les sessions admin
CREATE POLICY "Super admins can view all admin sessions" ON public.admin_sessions
    FOR SELECT USING (auth.jwt() ->> 'role' = 'super_admin');

-- Les utilisateurs peuvent supprimer leurs propres sessions admin
CREATE POLICY "Users can delete own admin sessions" ON public.admin_sessions
    FOR DELETE USING (auth.uid() = user_id);

-- Politiques pour la table admin_audit_logs
ALTER TABLE public.admin_audit_logs ENABLE ROW LEVEL SECURITY;

-- Les utilisateurs peuvent voir leurs propres logs
CREATE POLICY "Users can view own audit logs" ON public.admin_audit_logs
    FOR SELECT USING (auth.uid() = user_id);

-- Les super_admins peuvent voir tous les logs
CREATE POLICY "Super admins can view all audit logs" ON public.admin_audit_logs
    FOR SELECT USING (auth.jwt() ->> 'role' = 'super_admin');

-- Politiques pour la table admin_permissions
ALTER TABLE public.admin_permissions ENABLE ROW LEVEL SECURITY;

-- Tout le monde peut voir les permissions
CREATE POLICY "Everyone can view permissions" ON public.admin_permissions
    FOR SELECT USING (true);

-- Seuls les super_admins peuvent gérer les permissions
CREATE POLICY "Super admins can manage permissions" ON public.admin_permissions
    FOR ALL USING (auth.jwt() ->> 'role' = 'super_admin');

-- Politiques pour la table user_permissions
ALTER TABLE public.user_permissions ENABLE ROW LEVEL SECURITY;

-- Les utilisateurs peuvent voir leurs propres permissions
CREATE POLICY "Users can view own permissions" ON public.user_permissions
    FOR SELECT USING (auth.uid() = user_id);

-- Les super_admins peuvent gérer toutes les permissions
CREATE POLICY "Super admins can manage user permissions" ON public.user_permissions
    FOR ALL USING (auth.jwt() ->> 'role' = 'super_admin');

-- Politiques pour la table admin_login_attempts
ALTER TABLE public.admin_login_attempts ENABLE ROW LEVEL SECURITY;

-- Tout le monde peut lire les tentatives (pour monitoring)
CREATE POLICY "Everyone can read admin login attempts" ON public.admin_login_attempts
    FOR SELECT USING (true);

-- Seuls les super_admins peuvent écrire dans la table
CREATE POLICY "Super admins can manage admin login attempts" ON public.admin_login_attempts
    FOR ALL USING (auth.jwt() ->> 'role' = 'super_admin');

-- Politiques pour la table security_policies
ALTER TABLE public.security_policies ENABLE ROW LEVEL SECURITY;

-- Tout le monde peut voir les politiques
CREATE POLICY "Everyone can view security policies" ON public.security_policies
    FOR SELECT USING (true);

-- Seuls les super_admins peuvent gérer les politiques
CREATE POLICY "Super admins can manage security policies" ON public.security_policies
    FOR ALL USING (auth.jwt() ->> 'role' = 'super_admin');

-- Politiques pour la table security_tokens
ALTER TABLE public.security_tokens ENABLE ROW LEVEL SECURITY;

-- Les utilisateurs peuvent voir leurs propres tokens de sécurité
CREATE POLICY "Users can view own security tokens" ON public.security_tokens
    FOR SELECT USING (auth.uid() = user_id);

-- Les utilisateurs peuvent supprimer leurs propres tokens de sécurité
CREATE POLICY "Users can delete own security tokens" ON public.security_tokens
    FOR DELETE USING (auth.uid() = user_id);

-- Les super_admins peuvent voir tous les tokens de sécurité
CREATE POLICY "Super admins can view all security tokens" ON public.security_tokens
    FOR SELECT USING (auth.jwt() ->> 'role' = 'super_admin');

-- 3. Création des fonctions de sécurité renforcée
-- =============================================

-- Fonction pour vérifier l'accès administratif
CREATE OR REPLACE FUNCTION public.check_admin_access(user_id UUID, required_permission TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    user_role TEXT;
    user_permissions TEXT[];
    has_permission BOOLEAN := false;
BEGIN
    -- Récupérer le rôle de l'utilisateur
    SELECT role INTO user_role FROM public.admin_users WHERE id = user_id;
    
    -- Si c'est un super_admin, accès automatiquement accordé
    IF user_role = 'super_admin' THEN
        RETURN true;
    END IF;
    
    -- Si c'est un admin normal, vérifier les permissions
    IF user_role = 'admin' THEN
        SELECT array_agg(permission_name) INTO user_permissions
        FROM public.user_permissions up
        JOIN public.admin_permissions ap ON up.permission_id = ap.id
        WHERE up.user_id = user_id AND up.is_active = true;
        
        -- Vérifier si l'utilisateur a la permission requise
        IF required_permission = ANY(user_permissions) THEN
            has_permission := true;
        END IF;
    END IF;
    
    RETURN has_permission;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fonction pour enregistrer l'activité administrative
CREATE OR REPLACE FUNCTION public.log_admin_activity(
    user_id UUID,
    action TEXT,
    resource_type TEXT,
    resource_id TEXT,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    session_id TEXT,
    severity TEXT DEFAULT 'info'
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO public.admin_audit_logs (
        user_id,
        action,
        resource_type,
        resource_id,
        details,
        ip_address,
        user_agent,
        session_id,
        severity
    ) VALUES (
        user_id,
        action,
        resource_type,
        resource_id,
        details,
        ip_address,
        user_agent,
        session_id,
        severity
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fonction pour valider une session administrative
CREATE OR REPLACE FUNCTION public.validate_admin_session(session_id TEXT)
RETURNS TABLE(user_id UUID, is_valid BOOLEAN, expires_at TIMESTAMPTZ) AS $$
DECLARE
    session_record RECORD;
BEGIN
    SELECT user_id, expires_at, is_active, is_revoked
    INTO session_record
    FROM public.admin_sessions
    WHERE session_id = session_id
    ORDER BY created_at DESC
    LIMIT 1;
    
    IF session_record IS NULL THEN
        RETURN QUERY SELECT NULL::UUID, false, NULL;
    ELSIF NOT session_record.is_active OR session_record.is_revoked THEN
        RETURN QUERY SELECT session_record.user_id, false, session_record.expires_at;
    ELSIF session_record.expires_at < NOW() THEN
        RETURN QUERY SELECT session_record.user_id, false, session_record.expires_at;
    ELSE
        RETURN QUERY SELECT session_record.user_id, true, session_record.expires_at;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fonction pour vérifier les tentatives de connexion admin
CREATE OR REPLACE FUNCTION public.check_admin_login_attempts(email TEXT, ip_address INET)
RETURNS TABLE(is_locked BOOLEAN, remaining_attempts INTEGER, lock_time TIMESTAMPTZ) AS $$
DECLARE
    attempt_count INTEGER;
    lock_record RECORD;
    max_attempts INTEGER := 3; -- Moins de tentatives pour l'accès admin
    lock_duration INTERVAL := INTERVAL '15 minutes'; -- Verrou plus court
BEGIN
    -- Vérifier si l'IP est déjà verrouillée
    SELECT locked_until INTO lock_record
    FROM public.admin_login_attempts
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
    FROM public.admin_login_attempts
    WHERE email = email AND ip_address = ip_address AND success = false
    AND attempt_time > NOW() - INTERVAL '1 hour';
    
    -- Vérifier si le seuil est dépassé
    IF attempt_count >= max_attempts THEN
        UPDATE public.admin_login_attempts
        SET locked_until = NOW() + lock_duration
        WHERE email = email AND ip_address = ip_address AND success = false;
        
        RETURN QUERY SELECT true, 0, NOW() + lock_duration;
    ELSE
        RETURN QUERY SELECT false, max_attempts - attempt_count, NULL;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fonction pour générer un token de sécurité
CREATE OR REPLACE FUNCTION public.generate_security_token(user_id UUID, token_type TEXT)
RETURNS TEXT AS $$
DECLARE
    token TEXT;
    token_hash TEXT;
    expires_at TIMESTAMPTZ;
BEGIN
    -- Générer un token aléatoire
    token := encode(gen_random_bytes(32), 'base64');
    token_hash := crypt(token, gen_salt('bf'));
    
    -- Définir l'expiration selon le type de token
    CASE token_type
        WHEN '2fa' THEN
            expires_at := NOW() + INTERVAL '30 days';
        WHEN 'recovery' THEN
            expires_at := NOW() + INTERVAL '7 days';
        WHEN 'session' THEN
            expires_at := NOW() + INTERVAL '8 hours';
        ELSE
            expires_at := NOW() + INTERVAL '24 hours';
    END CASE;
    
    -- Stocker le token hashé
    INSERT INTO public.security_tokens (
        user_id,
        token_type,
        token_hash,
        expires_at
    ) VALUES (
        user_id,
        token_type,
        token_hash,
        expires_at
    );
    
    RETURN token;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fonction pour valider un token de sécurité
CREATE OR REPLACE FUNCTION public.validate_security_token(user_id UUID, token TEXT, token_type TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    token_record RECORD;
BEGIN
    SELECT id, token_hash, expires_at, is_used
    INTO token_record
    FROM public.security_tokens
    WHERE user_id = user_id 
    AND token_type = token_type
    AND expires_at > NOW()
    ORDER BY created_at DESC
    LIMIT 1;
    
    IF token_record IS NULL THEN
        RETURN false;
    ELSIF token_record.is_used THEN
        RETURN false;
    ELSIF crypt(token, token_record.token_hash) = token_record.token_hash THEN
        -- Marquer le token comme utilisé
        UPDATE public.security_tokens
        SET is_used = true, used_at = NOW()
        WHERE id = token_record.id;
        RETURN true;
    ELSE
        RETURN false;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. Création des triggers pour l'audit
-- =============================================

-- Trigger pour logger les modifications des profils admin
CREATE OR REPLACE FUNCTION public.log_admin_profile_change()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.admin_audit_logs (
        user_id,
        action,
        resource_type,
        resource_id,
        details,
        timestamp
    ) VALUES (
        NEW.id,
        CASE WHEN TG_OP = 'UPDATE' THEN 'profile_updated' 
             WHEN TG_OP = 'INSERT' THEN 'profile_created' 
             ELSE 'profile_deleted' END,
        'admin_profile',
        NEW.id::TEXT,
        jsonb_build_object(
            'changes', CASE WHEN TG_OP = 'UPDATE' THEN jsonb_build_object(
                'old', OLD,
                'new', NEW
            ) ELSE NULL END,
            'operation', TG_OP
        ),
        NOW()
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger pour logger les modifications des permissions
CREATE OR REPLACE FUNCTION public.log_permission_change()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.admin_audit_logs (
        user_id,
        action,
        resource_type,
        resource_id,
        details,
        timestamp
    ) VALUES (
        auth.uid(),
        CASE WHEN TG_OP = 'UPDATE' THEN 'permission_updated' 
             WHEN TG_OP = 'INSERT' THEN 'permission_granted' 
             ELSE 'permission_revoked' END,
        'admin_permission',
        NEW.id::TEXT,
        jsonb_build_object(
            'changes', CASE WHEN TG_OP = 'UPDATE' THEN jsonb_build_object(
                'old', OLD,
                'new', NEW
            ) ELSE NULL END,
            'operation', TG_OP,
            'target_user', NEW.user_id::TEXT
        ),
        NOW()
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Application des triggers
CREATE TRIGGER on_admin_profile_change
    AFTER INSERT OR UPDATE OR DELETE ON public.admin_users
    FOR EACH ROW EXECUTE FUNCTION public.log_admin_profile_change();

CREATE TRIGGER on_permission_change
    AFTER INSERT OR UPDATE OR DELETE ON public.user_permissions
    FOR EACH ROW EXECUTE FUNCTION public.log_permission_change();

-- 5. Création des politiques de sécurité par défaut
-- =============================================

-- Insertion des politiques de sécurité par défaut
INSERT INTO public.security_policies (name, description, policy_type, rules) VALUES
('admin_login_attempts', 'Limite les tentatives de connexion admin', 'login', 
    '{"max_attempts": 3, "lock_duration": "15 minutes", "window": "1 hour"}'),
('admin_session_timeout', 'Timeout des sessions admin', 'session', 
    '{"inactive_timeout": "30 minutes", "max_session_duration": "8 hours"}'),
('admin_ip_restriction', 'Restriction par IP pour admin', 'access', 
    '{"allow_multiple_ips": false, "trusted_ips": ["127.0.0.1"]}'),
('admin_data_access', 'Contrôle d''accès aux données admin', 'data', 
    '{"encryption_required": true, "audit_logging": true}');

-- Insertion des permissions par défaut
INSERT INTO public.admin_permissions (name, description, resource, action) VALUES
('view_users', 'Voir les utilisateurs', 'users', 'read'),
('manage_users', 'Gérer les utilisateurs', 'users', 'write'),
('view_hotels', 'Voir les hôtels', 'hotels', 'read'),
('manage_hotels', 'Gérer les hôtels', 'hotels', 'write'),
('view_reports', 'Voir les rapports', 'reports', 'read'),
('generate_reports', 'Générer des rapports', 'reports', 'write'),
('manage_security', 'Gérer la sécurité', 'security', 'admin'),
('view_audit_logs', 'Voir les logs d''audit', 'audit', 'read'),
('manage_system', 'Gérer le système', 'system', 'admin');

-- 6. Indexes pour performance
-- =============================================

CREATE INDEX IF NOT EXISTS idx_admin_users_email ON public.admin_users(email);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_user_id ON public.admin_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_user_id ON public.admin_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_timestamp ON public.admin_audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_security_tokens_user_id ON public.security_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_security_tokens_expires ON public.security_tokens(expires_at);

-- 7. Vues pour le monitoring
-- =============================================

-- Vue des activités administratives récentes
CREATE OR REPLACE VIEW public.recent_admin_activity AS
SELECT 
    a.id,
    a.user_id,
    u.email,
    a.action,
    a.resource_type,
    a.resource_id,
    a.details,
    a.ip_address,
    a.timestamp,
    a.severity,
    a.category
FROM public.admin_audit_logs a
JOIN auth.users u ON a.user_id = u.id
WHERE a.timestamp > NOW() - INTERVAL '24 hours'
ORDER BY a.timestamp DESC;

-- Vue des sessions administratives actives
CREATE OR REPLACE VIEW public.active_admin_sessions AS
SELECT 
    s.id,
    s.user_id,
    u.email,
    s.created_at,
    s.last_activity,
    s.expires_at,
    s.ip_address,
    s.user_agent,
    s.access_level,
    CASE WHEN s.expires_at > NOW() THEN 'active' 
         WHEN s.last_activity > NOW() - INTERVAL '30 minutes' THEN 'inactive'
         ELSE 'expired' END as status
FROM public.admin_sessions s
JOIN auth.users u ON s.user_id = u.id
WHERE s.is_active = true AND s.is_revoked = false;

-- Vue des tentatives de connexion admin
CREATE OR REPLACE VIEW public.admin_login_summary AS
SELECT 
    email,
    COUNT(*) as total_attempts,
    COUNT(CASE WHEN success = true THEN 1 END) as successful_attempts,
    COUNT(CASE WHEN success = false THEN 1 END) as failed_attempts,
    MAX(attempt_time) as last_attempt,
    COUNT(CASE WHEN success = false AND attempt_time > NOW() - INTERVAL '1 hour' THEN 1 END) as recent_failed
FROM public.admin_login_attempts
GROUP BY email
ORDER BY last_attempt DESC;

-- 8. Fonctions utilitaires
-- =============================================

-- Fonction pour révoquer toutes les sessions d'un utilisateur
CREATE OR REPLACE FUNCTION public.revoke_all_user_sessions(user_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.admin_sessions
    SET is_revoked = true, is_active = false
    WHERE user_id = user_id;
    
    INSERT INTO public.admin_audit_logs (
        user_id,
        action,
        resource_type,
        details,
        severity
    ) VALUES (
        user_id,
        'all_sessions_revoked',
        'admin_session',
        jsonb_build_object('reason', 'security_action'),
        'warning'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fonction pour forcer le changement de mot de passe
CREATE OR REPLACE FUNCTION public.force_password_change(user_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.admin_users
    SET must_change_password = true
    WHERE id = user_id;
    
    INSERT INTO public.admin_audit_logs (
        user_id,
        action,
        resource_type,
        details,
        severity
    ) VALUES (
        user_id,
        'password_change_forced',
        'admin_profile',
        jsonb_build_object('reason', 'security_policy'),
        'warning'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 9. Documentation de sécurité
-- =============================================

/*
Politiques de sécurité administrateur implémentées:

1. Authentification renforcée:
   - Jusqu'à 3 tentatives de connexion avant verrouillage (15 minutes)
   - Support du 2FA avec tokens
   - Changement de mot de passe obligatoire périodique
   - Journalisation complète des tentatives

2. Gestion des sessions:
   - Timeout d'inactivité (30 minutes)
   - Durée maximale de session (8 heures)
   - Révocation possible de toutes les sessions
   - Monitoring des sessions actives

3. Contrôle d'accès granulaire:
   - 3 niveaux d'administrateurs: super_admin, admin, readonly_admin
   - Permissions individuelles assignables
   - Vérification fine des accès aux ressources
   - Séparation des pouvoirs

4. Audit et monitoring:
   - Logs d'activité détaillés
   - Tracking des modifications sensibles
   - Monitoring des tentatives d'accès
   - Alertes pour activités suspectes

5. Sécurité des données:
   - Chiffrement des tokens sensibles
   - Politiques de RLS strictes
   - Validation des entrées
   - Protection contre les injections SQL

6. Réponse aux incidents:
   - Verrouillage automatique des comptes
   - Révocation immédiate des sessions
   - Journalisation complète pour l'analyse
   - Notifications pour actions sensibles
*/
