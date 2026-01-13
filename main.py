import os
import io
import shutil
import logging
import random
import string
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

# FastAPI
from fastapi import FastAPI, Request, Form, Depends, status, Response, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Auth & DB
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from captcha.image import ImageCaptcha 

# Local Modules
from database import engine, Base, get_db
# UPDATED IMPORTS: Including RepairLog, Consumable, AuditLog
from models import User, Department, SubDepartment, Asset, Ticket, SoftwareLicense, RepairLog, Consumable, AuditLog
from utils import encrypt_password, decrypt_password, log_audit, format_date, hash_password, verify_password

load_dotenv()

# --- APP CONFIG ---
app = FastAPI(title="EMCITOne - SQL Edition")

# Create Database Tables
Base.metadata.create_all(bind=engine)

# Ensure Upload Directory Exists
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Static & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["date"] = format_date

# --- AUTH CONFIG ---
SECRET_KEY = os.environ.get("SUPABASE_KEY", "fallback-secret-key")
ALGORITHM = "HS256"
captcha_generator = ImageCaptcha(width=280, height=90)

# --- AUTH HELPER FUNCTIONS ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=8)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token: return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        if user_email is None: return None
        return db.query(User).filter(User.email == user_email).first()
    except JWTError:
        return None

# ================= ROUTES =================

# --- LOGIN & LOGOUT ---
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, user: User = Depends(get_current_user)):
    if user: return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("auth/login.html", {"request": request})

@app.post("/auth/login")
async def login_action(response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not verify_password(password, user.hashed_password):
        return RedirectResponse(url="/?error=Invalid Credentials", status_code=303)
    
    token = create_access_token(data={"sub": user.email, "role": user.role})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=token, httponly=True)
    return response

@app.get("/auth/logout")
async def logout_action():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response
@app.get("/sop")
async def sop_page(request: Request, user: User = Depends(get_current_user)):
    if not user: return RedirectResponse(url="/")
    return templates.TemplateResponse("sop.html", {"request": request, "user": user})

# --- DASHBOARD ---
@app.get("/dashboard")
async def dashboard(request: Request, user: User = Depends(get_current_user)):
    if not user: return RedirectResponse(url="/")
    if user.role in ['admin', 'super_admin']:
        return RedirectResponse(url="/admin/dashboard")
    return RedirectResponse(url="/user/dashboard")

@app.get("/user/dashboard")
async def user_dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse(url="/")
    return templates.TemplateResponse("user/dashboard.html", {
        "request": request, "user": user,
        "assets": user.assets,
        "tickets": user.tickets
    })

@app.get("/admin/dashboard")
async def admin_dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    
    # KPIs
    kpi_data = {
        "total": db.query(Ticket).count(),
        "open": db.query(Ticket).filter(Ticket.status == "Open").count(),
        "critical": db.query(Ticket).filter(Ticket.priority == "Critical", Ticket.status != "Closed").count(),
        "asset_count": db.query(Asset).count()
    }
    
    # Recent Tickets
    recent = db.query(Ticket).order_by(Ticket.created_at.desc()).limit(10).all()
    
    # Renewal Alert Logic
    today = datetime.utcnow()
    next_month = today + timedelta(days=30)
    expiring_licenses = db.query(SoftwareLicense).filter(
        SoftwareLicense.renewal_date >= today,
        SoftwareLicense.renewal_date <= next_month
    ).all()
    
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "user": user,
        "kpi": kpi_data,
        "recent_tickets": recent,
        "expiring_licenses": expiring_licenses
    })

# --- ASSETS MANAGEMENT (UPDATED) ---
@app.get("/admin/assets")
async def admin_assets(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    return templates.TemplateResponse("admin/assets.html", {
        "request": request, "user": user, 
        "assets": db.query(Asset).all(), 
        "users": db.query(User).all()
    })

@app.post("/admin/assets/create")
async def create_asset(
    request: Request,
    # Section A: General & Location
    category: str = Form(...), asset_name: str = Form(...), brand: str = Form(None),
    model: str = Form(None), serial_number: str = Form(None), asset_tag: str = Form(None),
    location: str = Form(None), quantity: int = Form(1),
    
    # Section B: Financials & Dates
    purchase_date: str = Form(None), invoice_date: str = Form(None), 
    warranty_expiry: str = Form(None), vendor_name: str = Form(None), 
    invoice_number: str = Form(None),
    base_amount: float = Form(0.0), gst_amount: float = Form(0.0),
    
    # Assignment & Status
    department: str = Form(None), assigned_to: int = Form(None), 
    remarks: str = Form(None), status: str = Form("In Stock"),
    
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    
    # 1. Generate Auto Asset ID
    count = db.query(Asset).count() + 1
    auto_id = f"AST-{datetime.now().strftime('%Y')}-{count:04d}"
    
    # 2. Handle Date Conversions
    p_date = datetime.strptime(purchase_date, "%Y-%m-%d") if purchase_date else None
    i_date = datetime.strptime(invoice_date, "%Y-%m-%d") if invoice_date else None
    w_date = datetime.strptime(warranty_expiry, "%Y-%m-%d") if warranty_expiry else None
    
    # 3. Calculate Total Amount
    total_amount = base_amount + gst_amount

    # 4. Handle Dynamic Specs (Section C)
    # We use this intelligent loop to catch all the "Technical Fields" (RAM, Processor, etc)
    # without writing 100 separate variables.
    form_data = await request.form()
    
    # These are the standard columns in the Database, so we ignore them in the JSON Specs
    standard_columns = [
        "category", "asset_name", "brand", "model", "serial_number", "asset_tag", 
        "location", "quantity", "purchase_date", "invoice_date", "warranty_expiry", 
        "vendor_name", "invoice_number", "base_amount", "gst_amount", "department", 
        "assigned_to", "remarks", "status", "total_amount"
    ]
    
    # Everything else is considered a "Technical Spec" and stored in JSON
    technical_specs = {k: v for k, v in form_data.items() if k not in standard_columns and v}

    # 5. Save to Database
    new_asset = Asset(
        asset_id=auto_id, category=category, asset_name=asset_name, brand=brand, model=model,
        serial_number=serial_number, asset_tag=asset_tag, location=location, quantity=quantity,
        purchase_date=p_date, invoice_date=i_date, warranty_expiry=w_date,
        vendor_name=vendor_name, invoice_number=invoice_number,
        base_amount=base_amount, gst_amount=gst_amount, total_amount=total_amount,
        department=department, remarks=remarks, status=status,
        assigned_to=assigned_to if assigned_to else None,
        technical_specs=json.dumps(technical_specs) # Save JSON string
    )
    
    db.add(new_asset)
    db.commit()
    return RedirectResponse(url="/admin/assets", status_code=302)

# --- REPAIR LOGS (NEW FEATURE) ---
@app.get("/admin/repairs")
async def view_repairs(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    
    logs = db.query(RepairLog).order_by(RepairLog.repair_date.desc()).all()
    assets = db.query(Asset).all()
    
    return templates.TemplateResponse("admin/repair_logs.html", {
        "request": request, "user": user, 
        "logs": logs, "assets": assets
    })

@app.post("/admin/repairs/add")
async def add_repair_log(
    asset_id: int = Form(...), issue_reported: str = Form(...), vendor_name: str = Form(None),
    repair_cost: float = Form(0.0), remarks: str = Form(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user: return RedirectResponse(url="/")
    
    new_log = RepairLog(
        asset_id=asset_id, issue_reported=issue_reported, 
        vendor_name=vendor_name, repair_cost=repair_cost, remarks=remarks
    )
    db.add(new_log)
    db.commit()
    return RedirectResponse(url="/admin/repairs", status_code=302)

# --- CONSUMABLES (NEW FEATURE) ---
@app.get("/admin/consumables")
async def view_consumables(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    return templates.TemplateResponse("admin/consumables.html", {
        "request": request, "user": user, 
        "items": db.query(Consumable).all()
    })

@app.post("/admin/consumables/add")
async def add_consumable(
    item_name: str = Form(...), category: str = Form(...), total_quantity: int = Form(...),
    threshold_limit: int = Form(5), user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user: return RedirectResponse(url="/")
    
    new_item = Consumable(
        item_name=item_name, category=category, 
        total_quantity=total_quantity, remaining_quantity=total_quantity, 
        threshold_limit=threshold_limit
    )
    db.add(new_item)
    db.commit()
    return RedirectResponse(url="/admin/consumables", status_code=302)

# --- SOFTWARE VAULT (UPDATED) ---
@app.get("/admin/vault")
async def vault_view(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    return templates.TemplateResponse("admin/vault.html", {
        "request": request, "user": user,
        "licenses": db.query(SoftwareLicense).all()
    })

@app.post("/admin/vault/add")
async def vault_add(
    software_name: str = Form(...), license_type: str = Form(...),
    purchase_date: str = Form(None), activation_date: str = Form(None), renewal_date: str = Form(None),
    login_username: str = Form(None), login_password: str = Form(None),
    product_key: str = Form(...), vendor_name: str = Form(None),
    cost: str = Form(None), user_strength: int = Form(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user: return RedirectResponse(url="/")
    
    p_date = datetime.strptime(purchase_date, "%Y-%m-%d") if purchase_date else None
    a_date = datetime.strptime(activation_date, "%Y-%m-%d") if activation_date else None
    r_date = datetime.strptime(renewal_date, "%Y-%m-%d") if renewal_date else None
    
    new_license = SoftwareLicense(
        software_name=software_name, license_type=license_type,
        purchase_date=p_date, activation_date=a_date, renewal_date=r_date,
        login_username=login_username,
        login_password_enc=encrypt_password(login_password) if login_password else None,
        product_key_enc=encrypt_password(product_key),
        vendor_name=vendor_name, cost=cost, user_strength=user_strength,
        created_by=user.id
    )
    db.add(new_license)
    db.commit()
    return RedirectResponse(url="/admin/vault", status_code=302)

@app.post("/admin/vault/reveal")
async def vault_reveal(
    license_id: int = Form(...), captcha_input: str = Form(...), 
    captcha_token: str = Form(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user or user.role == 'user': return {"error": "Unauthorized"}
    
    try:
        if captcha_input.strip() != decrypt_password(captcha_token):
            return {"error": "Incorrect Captcha! Access Denied."}
    except:
        return {"error": "Invalid Session"}
    
    lic = db.query(SoftwareLicense).filter(SoftwareLicense.id == license_id).first()
    if lic:
        return {
            "product_key": decrypt_password(lic.product_key_enc),
            "password": decrypt_password(lic.login_password_enc) if lic.login_password_enc else "N/A"
        }
    return {"error": "Not Found"}

# --- CAPTCHA API ---
@app.get("/api/captcha")
async def get_captcha(response: Response):
    num1 = random.randint(10, 99)
    num2 = random.randint(1, 9)
    answer = str(num1 + num2)
    
    image = captcha_generator.generate(f"{num1} + {num2} = ?")
    stream = io.BytesIO(image.read())
    token = encrypt_password(answer)
    
    return StreamingResponse(stream, media_type="image/png", headers={"X-Captcha-Token": token})

# --- USER MANAGEMENT ---
@app.get("/admin/users")
async def admin_users(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    return templates.TemplateResponse("admin/users.html", {
        "request": request, "user": user,
        "users_list": db.query(User).order_by(User.created_at.desc()).all(),
        "departments": db.query(Department).all()
    })

@app.post("/admin/users/create")
async def create_user_route(
    full_name: str = Form(...), email: str = Form(...), password: str = Form(...),
    role: str = Form(...), department: str = Form(None), designation: str = Form(None),
    employee_id: str = Form(None), sub_department: str = Form(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    
    new_user = User(
        full_name=full_name, email=email, hashed_password=hash_password(password),
        role=role, department=department, sub_department=sub_department,
        designation=designation, employee_id=employee_id
    )
    try:
        db.add(new_user)
        db.commit()
        return RedirectResponse(url="/admin/users?success=User Created", status_code=302)
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/admin/users?error={str(e)}", status_code=303)

@app.post("/admin/users/update")
async def update_user_route(
    user_id: int = Form(...), full_name: str = Form(...), role: str = Form(...),
    department: str = Form(None), designation: str = Form(None), employee_id: str = Form(None),
    sub_department: str = Form(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user: return RedirectResponse(url="/")
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        target.full_name = full_name
        target.role = role
        target.department = department
        target.sub_department = sub_department
        target.designation = designation
        target.employee_id = employee_id
        db.commit()
    return RedirectResponse(url="/admin/users?success=Updated", status_code=302)

@app.post("/admin/users/delete")
async def delete_user_route(user_id: int = Form(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role != 'super_admin': return RedirectResponse(url="/")
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        db.delete(target)
        db.commit()
    return RedirectResponse(url="/admin/users?success=User Deleted", status_code=302)

# --- MASTER DATA (Departments) ---
@app.get("/admin/masters")
async def masters_view(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    return templates.TemplateResponse("admin/masters.html", {
        "request": request, "user": user,
        "departments": db.query(Department).all()
    })

@app.post("/admin/masters/department/add")
async def add_department(name: str = Form(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse(url="/")
    try:
        db.add(Department(name=name))
        db.commit()
    except: pass
    return RedirectResponse(url="/admin/masters", status_code=302)

@app.post("/admin/masters/subdepartment/add")
async def add_sub_department(department_id: int = Form(...), name: str = Form(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse(url="/")
    db.add(SubDepartment(name=name, department_id=department_id))
    db.commit()
    return RedirectResponse(url="/admin/masters", status_code=302)

# --- TICKETS MANAGEMENT ---
@app.post("/ticket/create")
async def create_ticket(
    title: str = Form(...), category: str = Form(...), priority: str = Form(...), 
    description: str = Form(...), attachment: UploadFile = File(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user: return RedirectResponse(url="/")
    
    file_path_db = None
    if attachment and attachment.filename:
        safe_name = f"{int(datetime.now().timestamp())}_{attachment.filename}"
        disk_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(disk_path, "wb") as buffer:
            shutil.copyfileobj(attachment.file, buffer)
        file_path_db = f"/static/uploads/{safe_name}"

    new_ticket = Ticket(
        ticket_uid=f"TKT-{int(datetime.now().timestamp())}",
        title=title, category=category, priority=priority,
        description=description, attachment_url=file_path_db,
        user_id=user.id
    )
    db.add(new_ticket)
    db.commit()
    log_audit(db, user.id, "CREATE_TICKET", new_ticket.ticket_uid)
    return RedirectResponse(url="/dashboard", status_code=302)

@app.post("/admin/ticket/update")
async def update_ticket(
    ticket_id: int = Form(...), status: str = Form(...), priority: str = Form(...),
    resolution_notes: str = Form(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    tkt = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if tkt:
        tkt.status = status
        tkt.priority = priority
        tkt.resolution_notes = resolution_notes
        tkt.assigned_admin = user.id
        db.commit()
    return RedirectResponse(url="/admin/dashboard", status_code=302)

# --- EXPORT REPORT ---
@app.get("/admin/export/tickets")
async def export_tickets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role == 'user': return RedirectResponse(url="/")
    tickets = db.query(Ticket).all()
    data = [{"ID": t.ticket_uid, "User": t.owner.full_name if t.owner else "Unknown", "Title": t.title, "Status": t.status} for t in tickets]
    stream = io.BytesIO()
    pd.DataFrame(data).to_excel(stream, index=False)
    stream.seek(0)
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=Report.xlsx"})

# --- SEED SUPER ADMIN ---
@app.get("/seed")
async def seed_db(db: Session = Depends(get_db)):
    if not db.query(User).filter(User.email == "itsupport@ecometrix.co.in").first():
        admin = User(
            full_name="IT Super Admin",
            email="itsupport@ecometrix.co.in",
            hashed_password=hash_password("ITAdmin@2026"),
            role="super_admin",
            designation="Head of IT"
        )
        db.add(admin)
        db.commit()
        return "Super Admin Created: itsupport@ecometrix.co.in / ITAdmin@2026"
    return "Admin already exists"