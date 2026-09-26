"""create_admin.py — Bootstrap / Provision an Administrator Account for KAVACH.

Usage:
  # Interactive mode:
  python scripts/create_admin.py

  # Non-interactive mode with CLI arguments:
  python scripts/create_admin.py --email admin@kavach.local --password adminpassword --name "System Administrator"
"""

import argparse
import getpass
import os
from pathlib import Path
import sys

# Ensure repository root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.session import SessionLocal
from backend.db.models import User, Department, Role
from backend.auth.security import hash_password
from backend.audit.logbook import log_event


def ensure_defaults(db):
    """Ensures default departments and roles exist in the database."""
    default_depts = [
        ("general", "General plant operations and shared services"),
        ("process", "Process Engineering, refining units and reactions"),
        ("maintenance", "Mechanical, rotating equipment & reliability"),
        ("hse", "Health, Safety & Environmental compliance"),
    ]
    for d_name, d_desc in default_depts:
        if not db.query(Department).filter(Department.name == d_name).first():
            db.add(Department(name=d_name, description=d_desc))

    default_roles = [
        ("engineer", "Standard operator and query analysis access"),
        ("approver", "Supervisor/manager with sign-off and approval gate authority"),
        ("admin", "Full administrator with user, model and security management"),
        ("auditor", "Compliance auditor with complete read-only audit log access"),
    ]
    for r_name, r_desc in default_roles:
        if not db.query(Role).filter(Role.name == r_name).first():
            db.add(Role(name=r_name, description=r_desc))

    db.commit()


def main():
    parser = argparse.ArgumentParser(description="Create or promote an administrator account for KAVACH.")
    parser.add_argument("--email", help="Administrator email address")
    parser.add_argument("--password", help="Administrator password")
    parser.add_argument("--name", help="Administrator display name", default="System Administrator")
    parser.add_argument("--restore-defaults", action="store_true", help="Restore missing default departments and roles without modifying users")
    args = parser.parse_args()

    print("=" * 60)
    print(" KAVACH: Sovereign On-Premises Administrator Bootstrap Tool")
    print("=" * 60)

    db = SessionLocal()
    try:
        ensure_defaults(db)

        if args.restore_defaults:
            print("\n[+] System defaults verified and restored:")
            print("    Departments: general, process, maintenance, hse")
            print("    Roles:       engineer, approver, admin, auditor\n")
            return

        email = args.email
        if not email:
            email = input("Enter Admin Email [default: admin@kavach.local]: ").strip() or "admin@kavach.local"

        password = args.password
        if not password:
            while True:
                password = getpass.getpass("Enter Admin Password (min 6 chars): ").strip()
                if len(password) < 6:
                    print("Error: Password must be at least 6 characters.")
                    continue
                confirm = getpass.getpass("Confirm Admin Password: ").strip()
                if password != confirm:
                    print("Error: Passwords do not match. Please try again.")
                    continue
                break

        name = args.name or "System Administrator"

        email_clean = email.strip().lower()
        pwd_hash = hash_password(password)

        existing = db.query(User).filter(User.email == email_clean).first()
        if existing:
            existing.name = name
            existing.password_hash = pwd_hash
            existing.role = "admin"
            existing.department = "general"
            db.commit()
            action_desc = "promoted existing user to admin"
            user_id = str(existing.id)
            print(f"\n[+] Successfully updated existing user '{email_clean}' to ADMIN role.")
        else:
            new_admin = User(
                name=name,
                email=email_clean,
                password_hash=pwd_hash,
                role="admin",
                department="general",
            )
            db.add(new_admin)
            db.commit()
            db.refresh(new_admin)
            action_desc = "created new admin account"
            user_id = str(new_admin.id)
            print(f"\n[+] Successfully created new ADMIN account: '{email_clean}'")

        # Record event in tamper-evident audit log
        log_event(
            event_type="admin_provision",
            actor="cli_bootstrap",
            summary=f"Administrator bootstrap: {action_desc} ({email_clean})",
            metadata={"email": email_clean, "role": "admin", "department": "general", "user_id": user_id},
            external_calls=0,
            user_id=user_id,
        )

        print("\n" + "-" * 60)
        print(" Administrator Credentials Verified:")
        print(f"   Name:       {name}")
        print(f"   Email:      {email_clean}")
        print(f"   Role:       admin")
        print(f"   Department: general")
        print("-" * 60)
        print("You can now sign in at http://localhost:3000 to manage users, roles, and plant departments.\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
