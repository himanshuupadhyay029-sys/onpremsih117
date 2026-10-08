"""routes.py — FastAPI authentication endpoints (register, login, logout, me) and dependencies."""

from typing import List, Optional
import os
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.audit.logbook import log_event
from backend.auth.security import (
    JWT_EXPIRATION_DAYS,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.db.models import User, Department, Role
from backend.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

VALID_ROLES = ('superadmin', 'admin', 'approver', 'auditor', 'engineer')
VALID_DEPARTMENTS = ('process', 'maintenance', 'hse', 'projects', 'finance', 'general')


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = 'engineer'
    department: str = 'general'


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    department: str
    created_at: str

    class Config:
        from_attributes = True


class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class UserProvisionRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = 'engineer'
    department: str = 'general'


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    password: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth Dependencies
# ---------------------------------------------------------------------------

def get_current_user(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    kavach_explicit_logout: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> User:
    """Extracts and validates the current user from the httpOnly cookie or Authorization header."""
    token = access_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()

    if not token:
        from backend.config import AUTO_LOGIN_SUPERADMIN
        if AUTO_LOGIN_SUPERADMIN and not kavach_explicit_logout:
            superadmin = (
                db.query(User)
                .filter((User.role == "superadmin") | (User.email == "admin@kavach.local"))
                .first()
            )
            if superadmin:
                return superadmin

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. No session cookie or token provided.",
        )

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )

    user_id = payload["sub"]
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed user identity.")

    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found.")

    return user


def get_optional_user(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    kavach_explicit_logout: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Returns the authenticated user if present, or None if unauthenticated."""
    try:
        return get_current_user(
            access_token=access_token,
            authorization=authorization,
            kavach_explicit_logout=kavach_explicit_logout,
            db=db,
        )
    except HTTPException:
        return None


def require_role(*allowed_roles):
    """FastAPI dependency factory: 403 if current_user.role not in allowed_roles."""
    def _dependency(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}. Your role: {current_user.role}.",
            )
        return current_user
    return _dependency


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    req: RegisterRequest,
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Registers an account. Public registration is disabled once users exist; only Admins can provision."""
    user_count = db.query(User).count()
    if user_count > 0:
        caller = get_optional_user(access_token=access_token, authorization=authorization, db=db)
        if not caller or caller.role not in ("admin", "superadmin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Public self-registration is disabled. Please contact your system administrator to provision your account.",
            )

    email_clean = req.email.strip().lower()
    if not email_clean or not req.password:
        raise HTTPException(status_code=400, detail="Email and password cannot be blank.")

    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{email_clean}' already exists.",
        )

    # First user is automatically superadmin, otherwise role requested
    role_val = ('superadmin' if user_count == 0 else (req.role.strip().lower() if req.role else 'engineer'))
    dept_val = req.department.strip().lower() if req.department else 'general'
    if role_val not in VALID_ROLES:
        role_val = 'engineer'
    if dept_val not in VALID_DEPARTMENTS:
        dept_val = 'general'

    pwd_hash = hash_password(req.password)
    user = User(
        name=req.name.strip() or email_clean.split("@")[0],
        email=email_clean,
        password_hash=pwd_hash,
        role=role_val,
        department=dept_val,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        department=user.department,
        created_at=user.created_at.isoformat(),
    )


@router.post("/login", response_model=UserResponse)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Authenticates user credentials and sets an httpOnly session cookie with SameSite=Lax."""
    email_clean = req.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "department": user.department,
    })
    max_age = JWT_EXPIRATION_DAYS * 24 * 3600
    is_cloud = os.environ.get("CLOUD_DEPLOYMENT", "false").lower() == "true"
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="none" if is_cloud else "lax",
        secure=is_cloud,  # True on HTTPS (Render/cloud), False on local HTTP
        path="/",
    )
    # Clear explicit logout flag so user is actively authenticated
    response.delete_cookie(key="kavach_explicit_logout", path="/")

    return UserResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        department=user.department,
        created_at=user.created_at.isoformat(),
    )


@router.post("/logout")
def logout(response: Response):
    """Clears the session cookie and marks explicit logout."""
    response.delete_cookie(key="access_token", path="/")
    response.set_cookie(
        key="kavach_explicit_logout",
        value="1",
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def me(
    response: Response,
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    kavach_explicit_logout: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    """Returns the authenticated user profile.
    If AUTO_LOGIN_SUPERADMIN is enabled and no session exists (and user didn't explicitly log out),
    automatically authenticates as superadmin.
    """
    token = access_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()

    if token:
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            try:
                user_uuid = uuid.UUID(payload["sub"])
                user = db.query(User).filter(User.id == user_uuid).first()
                if user:
                    return UserResponse(
                        id=str(user.id),
                        name=user.name,
                        email=user.email,
                        role=user.role,
                        department=user.department,
                        created_at=user.created_at.isoformat(),
                    )
            except Exception:
                pass

    # If no valid token found, check AUTO_LOGIN_SUPERADMIN
    from backend.config import AUTO_LOGIN_SUPERADMIN
    if AUTO_LOGIN_SUPERADMIN and not kavach_explicit_logout:
        superadmin = (
            db.query(User)
            .filter((User.role == "superadmin") | (User.email == "admin@kavach.local"))
            .first()
        )
        if superadmin:
            token = create_access_token({
                "sub": str(superadmin.id),
                "email": superadmin.email,
                "name": superadmin.name,
                "role": superadmin.role,
                "department": superadmin.department,
            })
            max_age = JWT_EXPIRATION_DAYS * 24 * 3600
            response.set_cookie(
                key="access_token",
                value=token,
                max_age=max_age,
                httponly=True,
                samesite="lax",
                secure=False,
                path="/",
            )
            return UserResponse(
                id=str(superadmin.id),
                name=superadmin.name,
                email=superadmin.email,
                role=superadmin.role,
                department=superadmin.department,
                created_at=superadmin.created_at.isoformat(),
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. No session cookie or token provided.",
    )


# ---------------------------------------------------------------------------
# Dynamic Department & Role Management (Admin-Controlled)
# ---------------------------------------------------------------------------

@router.get("/departments")
def list_departments(db: Session = Depends(get_db)):
    """Returns all plant departments."""
    rows = db.query(Department).order_by(Department.name).all()
    if not rows:
        return [{"name": d, "description": f"{d.capitalize()} operations"} for d in VALID_DEPARTMENTS]
    return [{"id": str(r.id), "name": r.name, "description": r.description} for r in rows]


@router.post("/departments", status_code=status.HTTP_201_CREATED)
def create_department(
    req: DepartmentCreate,
    current_user: User = Depends(require_role("superadmin")),
    db: Session = Depends(get_db),
):
    """Creates a new plant department (Superadmin only)."""
    clean_name = req.name.strip().lower()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Department name cannot be blank.")
    existing = db.query(Department).filter(Department.name == clean_name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Department '{clean_name}' already exists.")

    dept = Department(name=clean_name, description=req.description)
    db.add(dept)
    db.commit()
    db.refresh(dept)

    log_event(
        event_type="department_created",
        actor=f"superadmin:{current_user.email}",
        summary=f"Superadmin created department '{clean_name}'",
        metadata={"name": clean_name, "description": req.description},
        user_id=str(current_user.id),
    )
    return {"id": str(dept.id), "name": dept.name, "description": dept.description}


@router.delete("/departments/{dept_id}")
def delete_department(
    dept_id: str,
    current_user: User = Depends(require_role("superadmin")),
    db: Session = Depends(get_db),
):
    """Deletes a plant department (Superadmin only). 'general' and departments with assigned users cannot be deleted."""
    dept = None
    try:
        uid = uuid.UUID(dept_id)
        dept = db.query(Department).filter(Department.id == uid).first()
    except ValueError:
        dept = db.query(Department).filter(Department.name == dept_id.lower()).first()

    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    if dept.name.lower() == "general":
        raise HTTPException(
            status_code=400,
            detail="The root 'general' department is protected and cannot be deleted.",
        )

    assigned_count = db.query(User).filter(User.department == dept.name).count()
    if assigned_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete department '{dept.name}': {assigned_count} active user(s) are currently assigned to it. Please reassign them first.",
        )

    dept_name = dept.name
    db.delete(dept)
    db.commit()

    log_event(
        event_type="department_deleted",
        actor=f"superadmin:{current_user.email}",
        summary=f"Superadmin '{current_user.email}' deleted department '{dept_name}'",
        metadata={"department": dept_name},
        user_id=str(current_user.id),
    )
    return {"message": f"Department '{dept_name}' deleted successfully."}


@router.get("/roles")
def list_roles(db: Session = Depends(get_db)):
    """Returns all system roles."""
    rows = db.query(Role).order_by(Role.name).all()
    if not rows:
        return [{"name": r, "description": f"{r.capitalize()} role"} for r in VALID_ROLES]
    return [{"id": str(r.id), "name": r.name, "description": r.description} for r in rows]


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(
    req: RoleCreate,
    current_user: User = Depends(require_role("superadmin")),
    db: Session = Depends(get_db),
):
    """Creates a new operational role (Superadmin only)."""
    clean_name = req.name.strip().lower()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Role name cannot be blank.")
    existing = db.query(Role).filter(Role.name == clean_name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Role '{clean_name}' already exists.")

    role = Role(name=clean_name, description=req.description)
    db.add(role)
    db.commit()
    db.refresh(role)

    log_event(
        event_type="role_created",
        actor=f"superadmin:{current_user.email}",
        summary=f"Superadmin created role '{clean_name}'",
        metadata={"name": clean_name, "description": req.description},
        user_id=str(current_user.id),
    )
    return {"id": str(role.id), "name": role.name, "description": role.description}


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: str,
    current_user: User = Depends(require_role("superadmin")),
    db: Session = Depends(get_db),
):
    """Deletes an operational role (Superadmin only). 'superadmin', 'admin' and roles with assigned users cannot be deleted."""
    role = None
    try:
        uid = uuid.UUID(role_id)
        role = db.query(Role).filter(Role.id == uid).first()
    except ValueError:
        role = db.query(Role).filter(Role.name == role_id.lower()).first()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")

    if role.name.lower() in ("admin", "superadmin"):
        raise HTTPException(
            status_code=400,
            detail=f"The system '{role.name}' role is protected and cannot be deleted.",
        )

    assigned_count = db.query(User).filter(User.role == role.name).count()
    if assigned_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete role '{role.name}': {assigned_count} active user(s) are currently assigned to it. Please reassign them first.",
        )

    role_name = role.name
    db.delete(role)
    db.commit()

    log_event(
        event_type="role_deleted",
        actor=f"superadmin:{current_user.email}",
        summary=f"Superadmin '{current_user.email}' deleted role '{role_name}'",
        metadata={"role": role_name},
        user_id=str(current_user.id),
    )
    return {"message": f"Role '{role_name}' deleted successfully."}


# ---------------------------------------------------------------------------
# Administrative User Provisioning & Management
# ---------------------------------------------------------------------------

@router.get("/users", response_model=List[UserResponse])
def list_users(
    current_user: User = Depends(require_role("superadmin", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    """Lists provisioned users scoped to role and department."""
    if current_user.role == "superadmin" or (current_user.role == "auditor" and current_user.department == "general"):
        users = db.query(User).order_by(User.created_at.desc()).all()
    else:
        # Department Admin or Department Auditor: strictly scoped to own department
        users = db.query(User).filter(User.department == current_user.department).order_by(User.created_at.desc()).all()

    return [
        UserResponse(
            id=str(u.id),
            name=u.name,
            email=u.email,
            role=u.role,
            department=u.department,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def provision_user(
    req: UserProvisionRequest,
    current_user: User = Depends(require_role("superadmin", "admin")),
    db: Session = Depends(get_db),
):
    """Provisions a new employee account. Superadmin can provision anywhere; Department Admin can only provision non-admin roles in their own department."""
    email_clean = req.email.strip().lower()
    if not email_clean or not req.password:
        raise HTTPException(status_code=400, detail="Email and password cannot be blank.")

    role_clean = req.role.strip().lower() if req.role else "engineer"
    dept_clean = req.department.strip().lower() if req.department else "general"

    if role_clean not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{role_clean}'. Must be one of: {', '.join(VALID_ROLES)}.")

    # Department Admin restrictions
    if current_user.role == "admin":
        if dept_clean != current_user.department:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Department administrators can only provision users within their own department ('{current_user.department}').",
            )
        if role_clean in ("admin", "superadmin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Department administrators cannot provision admin or superadmin accounts.",
            )

    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{email_clean}' already exists.",
        )

    pwd_hash = hash_password(req.password)
    user = User(
        name=req.name.strip() or email_clean.split("@")[0],
        email=email_clean,
        password_hash=pwd_hash,
        role=role_clean,
        department=dept_clean,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_event(
        event_type="user_provisioned",
        actor=f"{current_user.role}:{current_user.email}",
        summary=f"{current_user.role.capitalize()} '{current_user.email}' provisioned user '{user.name}' ({user.email}) as role='{user.role}', dept='{user.department}'",
        metadata={"user_id": str(user.id), "email": user.email, "role": user.role, "department": user.department},
        user_id=str(current_user.id),
    )

    return UserResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        department=user.department,
        created_at=user.created_at.isoformat(),
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    req: UserUpdateRequest,
    current_user: User = Depends(require_role("superadmin", "admin")),
    db: Session = Depends(get_db),
):
    """Updates user role, department, name, or password. Subject to departmental boundary enforcement."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format.")

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Department Admin restrictions
    if current_user.role == "admin":
        if user.department != current_user.department:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Department administrators cannot modify users outside their department ('{current_user.department}').",
            )
        if user.role in ("admin", "superadmin") and str(user.id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Department administrators cannot modify other admin or superadmin accounts.",
            )
        if req.department is not None and req.department.strip().lower() != current_user.department:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Department administrators cannot reassign users to other departments.",
            )
        if req.role is not None and req.role.strip().lower() in ("admin", "superadmin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Department administrators cannot promote users to admin or superadmin.",
            )

    if req.name is not None and req.name.strip():
        user.name = req.name.strip()
    if req.role is not None and req.role.strip():
        role_clean = req.role.strip().lower()
        if role_clean not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role '{role_clean}'.")
        user.role = role_clean
    if req.department is not None and req.department.strip():
        user.department = req.department.strip().lower()
    if req.password is not None and req.password.strip():
        user.password_hash = hash_password(req.password.strip())

    db.commit()
    db.refresh(user)

    log_event(
        event_type="user_updated",
        actor=f"{current_user.role}:{current_user.email}",
        summary=f"{current_user.role.capitalize()} '{current_user.email}' updated user '{user.email}' (role={user.role}, dept={user.department})",
        metadata={"user_id": str(user.id), "email": user.email, "role": user.role, "department": user.department},
        user_id=str(current_user.id),
    )

    return UserResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        department=user.department,
        created_at=user.created_at.isoformat(),
    )


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    current_user: User = Depends(require_role("superadmin", "admin")),
    db: Session = Depends(get_db),
):
    """Deletes an account. Self-deletion and cross-admin deletions are strictly prohibited."""
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own administrative account.")

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format.")

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Root superadmin protection: cannot delete if only 1 remains
    if user.role == "superadmin":
        superadmin_count = db.query(User).filter(User.role == "superadmin").count()
        if superadmin_count <= 1:
            raise HTTPException(status_code=400, detail="The root superadmin account is protected and cannot be deleted.")

    # Department Admin restrictions
    if current_user.role == "admin":
        if user.department != current_user.department:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Department administrators cannot delete users outside their department ('{current_user.department}').",
            )
        if user.role in ("admin", "superadmin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Department administrators cannot delete admin or superadmin accounts.",
            )

    user_email = user.email
    db.delete(user)
    db.commit()

    log_event(
        event_type="user_deleted",
        actor=f"{current_user.role}:{current_user.email}",
        summary=f"{current_user.role.capitalize()} '{current_user.email}' deleted user '{user_email}'",
        metadata={"user_id": user_id, "email": user_email},
        user_id=str(current_user.id),
    )

    return {"message": f"User '{user_email}' deleted successfully."}

