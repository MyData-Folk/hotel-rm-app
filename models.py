from sqlmodel import SQLModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    SUPER_ADMIN = "super_admin"

class User(SQLModel, table=True):
    id: str = Field(primary_key=True)  # UUID de Supabase
    email: str
    role: UserRole = Field(default=UserRole.USER)
    admin_hotel_id: Optional[str] = Field(default=None)  # Lien vers l'hôtel géré par l'admin
    admin_role: Optional[str] = Field(default="viewer")  # Rôle admin pour l'hôtel
    created_at: datetime = Field(default_factory=datetime.now)

class Hotel(SQLModel, table=True):
    hotel_id: str = Field(primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=datetime.now)

class UserHotelPermission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    user_email: str
    hotel_id: str = Field(foreign_key="hotel.hotel_id")
    access_expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.now)

# Tables de contrôle administratif
class AdminUserManagement(SQLModel, table=True):
    hotel_id: str = Field(primary_key=True)
    hotel_name: str
    admin_email: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    status: str = Field(default="active")  # active, suspended, deleted

class AdminTariffPlans(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=lambda: str(__import__('uuid').uuid4()))
    hotel_id: str = Field(foreign_key="admin_user_management.hotel_id")
    plan_name: str
    plan_data: Dict[str, Any]  # JSONB équivalent
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    upload_date: datetime = Field(default_factory=datetime.now)
    uploaded_by: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    status: str = Field(default="active")  # active, draft, archived

class AdminConfiguration(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=lambda: str(__import__('uuid').uuid4()))
    hotel_id: str = Field(foreign_key="admin_user_management.hotel_id")
    config_name: str
    config_data: Dict[str, Any]  # JSONB équivalent
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    upload_date: datetime = Field(default_factory=datetime.now)
    uploaded_by: Optional[str] = None
    version: str = Field(default="1.0")
    status: str = Field(default="active")  # active, draft, archived

class AdminAuditLog(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=lambda: str(__import__('uuid').uuid4()))
    hotel_id: str = Field(foreign_key="admin_user_management.hotel_id")
    action: str
    table_name: str
    record_id: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    performed_by: Optional[str] = None
    performed_at: datetime = Field(default_factory=datetime.now)
