# utils.py
import os
from datetime import datetime
from cryptography.fernet import Fernet
from passlib.context import CryptContext
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from models import AuditLog  # Import the new SQL model

load_dotenv()

# --- SECURITY: CRYPTO ---
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("FATAL: ENCRYPTION_KEY is missing in .env")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_password(raw_password: str) -> str:
    return cipher_suite.encrypt(raw_password.encode()).decode()

def decrypt_password(encrypted_token: str) -> str:
    return cipher_suite.decrypt(encrypted_token.encode()).decode()

# --- SECURITY: AUTH HASHING ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# --- AUDIT LOGGING (SQL Version) ---
def log_audit(db: Session, user_id: int, action: str, target: str, ip: str = "Unknown"):
    try:
        log_entry = AuditLog(
            actor_id=user_id,
            action=action,
            target_entity=target,
            ip_address=ip
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"AUDIT LOG FAILED: {e}")

# --- FORMATTING ---
def format_date(dt):
    if not dt: return "-"
    if isinstance(dt, str):
        try: dt = datetime.fromisoformat(dt)
        except: return dt
    return dt.strftime("%d %b %Y")