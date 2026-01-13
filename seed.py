import os
import asyncio
from supabase import create_client, Client
from dotenv import load_dotenv

# Load keys
load_dotenv()

# MUST use the SERVICE_ROLE key to create users without email confirmation
URL = os.environ.get("SUPABASE_URL")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SERVICE_KEY:
    print("❌ ERROR: SUPABASE_SERVICE_KEY is missing in .env file!")
    exit()

supabase: Client = create_client(URL, SERVICE_KEY)

def seed_admin():
    email = "itsupport@ecometrix.co.in"
    password = "ITAdmin@2026"

    print(f"⚙️  Attempting to create Super Admin: {email}...")

    try:
        # 1. Create User in Supabase Auth
        # This auto-confirms the email so you can log in immediately
        user_attributes = {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": "IT Super Admin"}
        }
        user = supabase.auth.admin.create_user(user_attributes)
        user_id = user.user.id
        print(f"✅ Auth User Created! ID: {user_id}")

        # 2. Force Update Role to 'super_admin' in profiles table
        # We wait a moment to ensure the trigger 'handle_new_user' has fired
        import time
        time.sleep(2) 
        
        response = supabase.table("profiles").update({"role": "super_admin", "designation": "Head of IT"}).eq("id", user_id).execute()
        print(f"✅ Role elevated to SUPER_ADMIN.")
        print("-" * 30)
        print(f"🚀 LOGIN READY:\nEmail: {email}\nPass:  {password}")
        print("-" * 30)

    except Exception as e:
        print(f"⚠️  Info: {str(e)}")
        print("Tip: If the user already exists, just go logging in!")

if __name__ == "__main__":
    seed_admin()