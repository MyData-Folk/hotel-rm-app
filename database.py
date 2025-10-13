from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration de la base de données avec Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://supabase.e-hotelmanager.com')
SUPABASE_DB_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@db.supabase.co:5432/postgres')

# Utiliser la variable d'environnement si disponible, sinon la valeur par défaut
DATABASE_URL = os.getenv('DATABASE_URL', SUPABASE_DB_URL)

# Configuration du moteur SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Mettre à True pour le debug SQL
    pool_pre_ping=True,
    pool_recycle=300
)

# Factory de session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_session():
    """Obtenir une session de base de données"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialiser la base de données et créer toutes les tables"""
    try:
        # Créer toutes les tables définies dans les modèles
        SQLModel.metadata.create_all(bind=engine)
        print("Base de données initialisée avec succès")
        return True
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la base de données: {e}")
        return False

def get_db():
    """Décorateur pour obtenir une session de base de données"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Fonctions utilitaires pour le déploiement
def check_database_connection():
    """Vérifier la connexion à la base de données"""
    try:
        with Session(engine) as session:
            # Exécuter une simple requête pour vérifier la connexion
            session.execute("SELECT 1")
            print("Connexion à la base de données réussie")
            return True
    except Exception as e:
        print(f"Erreur de connexion à la base de données: {e}")
        return False

def reset_database():
    """Réinitialiser la base de données (supprimer et recréer les tables)"""
    try:
        # Supprimer toutes les tables
        SQLModel.metadata.drop_all(bind=engine)
        print("Tables supprimées avec succès")
        
        # Recréer toutes les tables
        init_db()
        return True
    except Exception as e:
        print(f"Erreur lors de la réinitialisation de la base de données: {e}")
        return False

# Configuration pour l'environnement de test
TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'sqlite:///./test.db')

def get_test_engine():
    """Obtenir le moteur pour les tests"""
    return create_engine(TEST_DATABASE_URL, echo=False)

# Initialisation automatique au démarrage
if __name__ == "__main__":
    # Vérifier la connexion
    if check_database_connection():
        print("Base de données prête à l'emploi")
    else:
        print("Erreur de connexion à la base de données")
