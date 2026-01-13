# models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# 1. Departments & Sub-Departments
class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    sub_departments = relationship("SubDepartment", back_populates="department")

class SubDepartment(Base):
    __tablename__ = "sub_departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"))
    department = relationship("Department", back_populates="sub_departments")

# 2. Users
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    employee_id = Column(String, nullable=True)
    designation = Column(String, nullable=True)
    department = Column(String, nullable=True)
    sub_department = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tickets = relationship("Ticket", foreign_keys="[Ticket.user_id]", back_populates="owner")
    assets = relationship("Asset", back_populates="assignee")

# 3. Assets (UPDATED with Financials & Location)
class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, index=True)
    
    # Section A: General Info
    asset_id = Column(String, unique=True, index=True) 
    category = Column(String, nullable=False)
    asset_name = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    serial_number = Column(String, nullable=True)
    asset_tag = Column(String, nullable=True)
    
    # Location & Quantity
    location = Column(String, nullable=True) # NEW
    quantity = Column(Integer, default=1) # NEW
    
    # Financials (NEW)
    purchase_date = Column(DateTime, nullable=True)
    invoice_date = Column(DateTime, nullable=True) 
    invoice_number = Column(String, nullable=True)
    vendor_name = Column(String, nullable=True)
    warranty_expiry = Column(DateTime, nullable=True)
    
    base_amount = Column(Float, default=0.0)
    gst_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    
    ownership = Column(String, default="Company Owned")
    status = Column(String, default="In Stock")
    department = Column(String, nullable=True)
    remarks = Column(Text, nullable=True)
    
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    assignee = relationship("User", back_populates="assets")

    technical_specs = Column(Text, nullable=True) # JSON
    repair_logs = relationship("RepairLog", back_populates="asset")

# 4. Tickets
class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    ticket_uid = Column(String, unique=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String)
    priority = Column(String)
    status = Column(String, default="Open")
    attachment_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolution_notes = Column(Text, nullable=True)
    
    user_id = Column(Integer, ForeignKey("users.id"))
    assigned_admin = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    owner = relationship("User", foreign_keys=[user_id], back_populates="tickets")
    admin = relationship("User", foreign_keys=[assigned_admin])

# 5. Software Licenses (UPDATED)
class SoftwareLicense(Base):
    __tablename__ = "software_licenses"
    id = Column(Integer, primary_key=True, index=True)
    software_name = Column(String, nullable=False)
    license_type = Column(String, nullable=False)
    purchase_date = Column(DateTime, nullable=True)
    activation_date = Column(DateTime, nullable=True) # NEW
    renewal_date = Column(DateTime, nullable=True)
    login_username = Column(String, nullable=True)
    login_password_enc = Column(String, nullable=True)
    product_key_enc = Column(String, nullable=False)
    vendor_name = Column(String, nullable=True)
    cost = Column(String, nullable=True)
    user_strength = Column(Integer, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

# 6. Repair Logs (NEW)
class RepairLog(Base):
    __tablename__ = "repair_logs"
    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"))
    issue_reported = Column(String, nullable=False)
    vendor_name = Column(String, nullable=True)
    repair_cost = Column(Float, default=0.0)
    repair_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="In Progress") # In Progress, Completed
    remarks = Column(Text, nullable=True)
    
    asset = relationship("Asset", back_populates="repair_logs")

# 7. Consumables (NEW)
class Consumable(Base):
    __tablename__ = "consumables"
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, nullable=False) # e.g. HP 12A Toner
    category = Column(String, nullable=False) # Ink, Toner, Battery
    total_quantity = Column(Integer, default=0)
    remaining_quantity = Column(Integer, default=0)
    last_restocked = Column(DateTime, default=datetime.utcnow)
    threshold_limit = Column(Integer, default=5) # Alert if below this

# 8. Audit Logs
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, nullable=True)
    action = Column(String)
    target_entity = Column(String)
    ip_address = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)