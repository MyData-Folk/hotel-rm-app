-- Script SQL pour créer les tables de contrôle administratif
-- Architecture avec contrôle total par l'admin

-- Extension de la table User existante pour lier aux admin tables
ALTER TABLE user ADD COLUMN IF NOT EXISTS admin_hotel_id VARCHAR(100);
ALTER TABLE user ADD COLUMN IF NOT EXISTS admin_role VARCHAR(20) DEFAULT 'viewer';

-- Table principale de gestion des utilisateurs par l'admin
CREATE TABLE IF NOT EXISTS admin_user_management (
    hotel_id VARCHAR(100) UNIQUE PRIMARY KEY,
    hotel_name VARCHAR(255) NOT NULL,
    admin_email VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255),
    contact_phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active' -- active, suspended, deleted
);

-- Table des plans tarifaires (Excel/CSV) gérés par l'admin
CREATE TABLE IF NOT EXISTS admin_tariff_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id VARCHAR(100) NOT NULL REFERENCES admin_user_management(hotel_id),
    plan_name VARCHAR(255) NOT NULL,
    plan_data JSONB NOT NULL, -- Contenu des plans tarifaires
    file_name VARCHAR(255),
    file_size BIGINT,
    upload_date TIMESTAMP DEFAULT NOW(),
    uploaded_by VARCHAR(255),
    valid_from DATE,
    valid_to DATE,
    status VARCHAR(20) DEFAULT 'active' -- active, draft, archived
);

-- Table de configuration (JSON) gérée par l'admin
CREATE TABLE IF NOT EXISTS admin_configuration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id VARCHAR(100) NOT NULL REFERENCES admin_user_management(hotel_id),
    config_name VARCHAR(255) NOT NULL,
    config_data JSONB NOT NULL, -- Contenu de la configuration JSON
    file_name VARCHAR(255),
    file_size BIGINT,
    upload_date TIMESTAMP DEFAULT NOW(),
    uploaded_by VARCHAR(255),
    version VARCHAR(50) DEFAULT '1.0',
    status VARCHAR(20) DEFAULT 'active' -- active, draft, archived
);

-- Table d'historique des modifications (audit log)
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id VARCHAR(100) NOT NULL REFERENCES admin_user_management(hotel_id),
    action VARCHAR(100) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    record_id UUID,
    old_values JSONB,
    new_values JSONB,
    performed_by VARCHAR(255),
    performed_at TIMESTAMP DEFAULT NOW()
);

-- Politiques de sécurité RLS pour admin_user_management
ALTER TABLE admin_user_management ENABLE ROW LEVEL SECURITY;

-- Politique : Les admins peuvent accéder à tous les hôtels
CREATE POLICY "Admins can access all hotels" ON admin_user_management
    FOR ALL USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent créer des hôtels
CREATE POLICY "Admins can create hotels" ON admin_user_management
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent modifier les hôtels
CREATE POLICY "Admins can update hotels" ON admin_user_management
    FOR UPDATE USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent supprimer des hôtels
CREATE POLICY "Admins can delete hotels" ON admin_user_management
    FOR DELETE USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politiques de sécurité RLS pour admin_tariff_plans
ALTER TABLE admin_tariff_plans ENABLE ROW LEVEL SECURITY;

-- Politique : Les admins peuvent accéder à tous les plans tarifaires
CREATE POLICY "Admins can access all tariff plans" ON admin_tariff_plans
    FOR ALL USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent créer des plans tarifaires
CREATE POLICY "Admins can create tariff plans" ON admin_tariff_plans
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent modifier les plans tarifaires
CREATE POLICY "Admins can update tariff plans" ON admin_tariff_plans
    FOR UPDATE USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent supprimer des plans tarifaires
CREATE POLICY "Admins can delete tariff plans" ON admin_tariff_plans
    FOR DELETE USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politiques de sécurité RLS pour admin_configuration
ALTER TABLE admin_configuration ENABLE ROW LEVEL SECURITY;

-- Politique : Les admins peuvent accéder à toutes les configurations
CREATE POLICY "Admins can access all configurations" ON admin_configuration
    FOR ALL USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent créer des configurations
CREATE POLICY "Admins can create configurations" ON admin_configuration
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent modifier les configurations
CREATE POLICY "Admins can update configurations" ON admin_configuration
    FOR UPDATE USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les admins peuvent supprimer des configurations
CREATE POLICY "Admins can delete configurations" ON admin_configuration
    FOR DELETE USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politiques de sécurité RLS pour admin_audit_log
ALTER TABLE admin_audit_log ENABLE ROW LEVEL SECURITY;

-- Politique : Les admins peuvent accéder à tout l'historique
CREATE POLICY "Admins can access all audit logs" ON admin_audit_log
    FOR ALL USING (
        auth.jwt() ->> 'role' = 'admin' OR 
        auth.jwt() ->> 'role' = 'super_admin'
    );

-- Politique : Les hôtels peuvent accéder à leur propre configuration (lecture seule)
CREATE POLICY "Hotels can access their configuration" ON admin_configuration
    FOR SELECT USING (
        auth.jwt() ->> 'role' = 'user' AND
        EXISTS (
            SELECT 1 FROM user_hotel_permissions uhp
            WHERE uhp.user_id = auth.uid()::text
            AND uhp.hotel_id = admin_configuration.hotel_id
        )
    );

-- Politique : Les hôtels peuvent accéder à leur propre plan tarifaire (lecture seule)
CREATE POLICY "Hotels can access their tariff plans" ON admin_tariff_plans
    FOR SELECT USING (
        auth.jwt() ->> 'role' = 'user' AND
        EXISTS (
            SELECT 1 FROM user_hotel_permissions uhp
            WHERE uhp.user_id = auth.uid()::text
            AND uhp.hotel_id = admin_tariff_plans.hotel_id
        )
    );

-- Fonctions utilitaires
-- Fonction pour incrémenter la version
CREATE OR REPLACE FUNCTION increment_version(current_version VARCHAR)
RETURNS VARCHAR AS $$
DECLARE
    major INT;
    minor INT;
BEGIN
    IF current_version IS NULL OR current_version = '' THEN
        RETURN '1.0';
    END IF;
    
    -- Si la version est numérique simple (1, 2, 3...)
    IF current_version ~ '^\d+$' THEN
        RETURN (current_version::INTEGER + 1)::TEXT;
    END IF;
    
    -- Si la version est en format X.Y (1.0, 1.1, 2.0...)
    IF current_version ~ '^\d+\.\d+$' THEN
        major = split_part(current_version, '.', 1)::INTEGER;
        minor = split_part(current_version, '.', 2)::INTEGER;
        RETURN major || '.' || (minor + 1);
    END IF;
    
    -- Format inconnu, retourner 1.0
    RETURN '1.0';
END;
$$ LANGUAGE plpgsql;

-- Fonction pour journaliser les actions
CREATE OR REPLACE FUNCTION log_admin_action(
    p_hotel_id VARCHAR,
    p_action VARCHAR,
    p_table_name VARCHAR,
    p_record_id UUID,
    p_old_values JSONB,
    p_new_values JSONB,
    p_performed_by VARCHAR
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO admin_audit_log (
        hotel_id,
        action,
        table_name,
        record_id,
        old_values,
        new_values,
        performed_by,
        performed_at
    ) VALUES (
        p_hotel_id,
        p_action,
        p_table_name,
        p_record_id,
        p_old_values,
        p_new_values,
        p_performed_by,
        NOW()
    );
END;
$$ LANGUAGE plpgsql;

-- Index pour optimiser les performances
CREATE INDEX IF NOT EXISTS idx_admin_user_management_status ON admin_user_management(status);
CREATE INDEX IF NOT EXISTS idx_admin_tariff_plans_hotel_status ON admin_tariff_plans(hotel_id, status);
CREATE INDEX IF NOT EXISTS idx_admin_configuration_hotel_status ON admin_configuration(hotel_id, status);
CREATE INDEX IF NOT EXISTS idx_admin_audit_log_hotel_action ON admin_audit_log(hotel_id, action);
CREATE INDEX IF NOT EXISTS idx_admin_audit_log_performed_at ON admin_audit_log(performed_at DESC);

-- Insertion d'un hôtel de test pour validation
INSERT INTO admin_user_management (
    hotel_id,
    hotel_name,
    admin_email,
    contact_email,
    contact_phone,
    status
) VALUES (
    'hotel_test',
    'Hôtel de Test',
    'admin@test.com',
    'contact@test.com',
    '+33 1 23 45 67 89',
    'active'
)
ON CONFLICT (hotel_id) DO NOTHING;

-- Insertion des données de test pour les plans tarifaires et configuration
INSERT INTO admin_tariff_plans (
    hotel_id,
    plan_name,
    plan_data,
    file_name,
    status
) VALUES (
    'hotel_test',
    'Plan tarifaire initial',
    '{"rooms": [], "rates": [], "valid_from": "2024-01-01", "valid_to": "2024-12-31"}',
    'tarif_test.xlsx',
    'active'
)
ON CONFLICT (hotel_id) DO NOTHING;

INSERT INTO admin_configuration (
    hotel_id,
    config_name,
    config_data,
    file_name,
    version,
    status
) VALUES (
    'hotel_test',
    'Configuration initiale',
    '{"mapping": {}, "settings": {}}',
    'config_test.json',
    '1.0',
    'active'
)
ON CONFLICT (hotel_id) DO NOTHING;

-- Commentaires explicatifs
COMMENT ON TABLE admin_user_management IS 'Table principale de gestion des utilisateurs/hôtels par l''admin';
COMMENT ON TABLE admin_tariff_plans IS 'Table des plans tarifaires (Excel/CSV) gérés par l''admin';
COMMENT ON TABLE admin_configuration IS 'Table de configuration (JSON) gérée par l''admin';
COMMENT ON TABLE admin_audit_log IS 'Table d''audit pour tracer toutes les modifications';
COMMENT ON COLUMN admin_user_management.hotel_id IS 'Identifiant unique de l''hôtel';
COMMENT ON COLUMN admin_user_management.admin_email IS 'Email de l''administrateur responsable de l''hôtel';
COMMENT ON COLUMN admin_user_management.status IS 'Statut de l''hôtel (active, suspended, deleted)';
COMMENT ON COLUMN admin_tariff_plans.plan_data IS 'Données JSON des plans tarifaires';
COMMENT ON COLUMN admin_configuration.config_data IS 'Données JSON de la configuration';
COMMENT ON COLUMN admin_audit_log.action IS 'Type d''action effectuée (create, update, delete)';
COMMENT ON COLUMN admin_audit_log.performed_by IS 'Email de l''utilisateur ayant effectué l''action';
