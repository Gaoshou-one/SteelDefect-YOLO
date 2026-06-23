# database/models.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class UserRole(Enum):
    ADMIN = 'admin'
    OPERATOR = 'operator'
    VIEWER = 'viewer'

@dataclass
class User:
    id: int = None
    username: str = ''
    password_hash: str = ''
    role: str = UserRole.OPERATOR.value
    real_name: str = ''
    department: str = ''
    email: str = ''
    phone: str = ''
    created_at: datetime = None
    last_login: datetime = None
    is_active: bool = True

@dataclass
class DetectionRecord:
    id: int = None
    user_id: int = None
    username: str = ''
    image_path: str = ''
    result_image_path: str = ''
    source_type: str = ''
    total_detections: int = 0
    detections_json: str = ''
    inference_time: float = 0.0
    confidence_threshold: float = 0.25
    created_at: datetime = None
    class_counts: str = ''

@dataclass
class SystemLog:
    id: int = None
    user_id: int = None
    username: str = ''
    action: str = ''
    details: str = ''
    ip_address: str = ''
    created_at: datetime = None