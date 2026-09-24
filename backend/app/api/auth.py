"""/api/auth: login, logout, current user, and admin user management."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, require_permission
from app.audit.logger import write_audit
from app.config import get_settings
from app.database import get_db
from app.models.user import RevokedToken, Role, User
from app.schemas.auth import LoginRequest, RoleUpdate, TokenResponse, UserCreate, UserOut
from app.security.passwords import burn_verification_time, hash_password, verify_password
from app.security.rbac import Permission
from app.security.tokens import create_access_token
from app.timeutil import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])

_INVALID_LOGIN = "Invalid username or password"


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    ip = client_ip(request)
    now = utcnow()
    user = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()

    if user is None:
        burn_verification_time(body.password)
        write_audit(db, action="LOGIN_FAILED", user=body.username, ip=ip, result="FAILURE",
                    severity="WARNING", details={"reason": "unknown_user"})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INVALID_LOGIN)

    if user.locked_until and user.locked_until > now:
        retry_after = int((user.locked_until - now).total_seconds()) + 1
        write_audit(db, action="LOGIN_BLOCKED", user=user.username, ip=ip, result="FAILURE",
                    severity="WARNING", details={"reason": "account_locked"})
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Account temporarily locked after repeated failed logins",
                            headers={"Retry-After": str(retry_after)})

    if not user.is_active or not verify_password(user.password_hash, body.password):
        reason = "disabled_account" if not user.is_active else "bad_password"
        if user.is_active:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_login_attempts = 0
        write_audit(db, action="LOGIN_FAILED", user=user.username, ip=ip, result="FAILURE",
                    severity="WARNING", details={"reason": reason})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INVALID_LOGIN)

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    token, _jti, _exp = create_access_token(
        subject=str(user.id), role=user.role.name, secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm, expires_minutes=settings.access_token_minutes,
    )
    write_audit(db, action="LOGIN", user=user.username, ip=ip, resource="auth")
    return TokenResponse(access_token=token, expires_in=settings.access_token_minutes * 60,
                         username=user.username, role=user.role.name)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    claims = request.state.token_claims
    db.add(RevokedToken(jti=claims["jti"],
                        expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc)))
    write_audit(db, action="LOGOUT", user=user.username, ip=client_ip(request), resource="auth")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.from_user(user)


@router.get("/users", response_model=list[UserOut])
def list_users(_admin: User = Depends(require_permission(Permission.USER_MANAGE)),
               db: Session = Depends(get_db)):
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [UserOut.from_user(u) for u in users]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, request: Request,
                admin: User = Depends(require_permission(Permission.USER_MANAGE)),
                db: Session = Depends(get_db)):
    if db.execute(select(User.id).where(User.username == body.username)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    role = db.execute(select(Role).where(Role.name == body.role.value)).scalar_one()
    user = User(username=body.username, full_name=body.full_name, role=role,
                password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists") from exc
    db.refresh(user)
    write_audit(db, action="USER_CREATE", user=admin.username, ip=client_ip(request),
                resource=f"user:{user.username}", details={"role": body.role.value})
    return UserOut.from_user(user)


@router.patch("/users/{user_id}/role", response_model=UserOut)
def change_role(user_id: int, body: RoleUpdate, request: Request,
                admin: User = Depends(require_permission(Permission.USER_MANAGE)),
                db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role")
    old_role = target.role.name
    new_role = db.execute(select(Role).where(Role.name == body.role.value)).scalar_one()
    target.role = new_role
    db.commit()
    db.refresh(target)
    write_audit(db, action="ROLE_CHANGE", user=admin.username, ip=client_ip(request),
                resource=f"user:{target.username}",
                details={"old_role": old_role, "new_role": body.role.value}, severity="WARNING")
    return UserOut.from_user(target)
