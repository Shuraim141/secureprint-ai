"""Shared FastAPI dependencies: authentication and permission checks."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.audit.logger import write_audit
from app.config import get_settings
from app.database import get_db
from app.models.user import RevokedToken, User
from app.security.rbac import Permission, has_permission
from app.security.tokens import TokenError, decode_access_token

_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str:
    # Behind a reverse proxy this must come from a trusted X-Forwarded-For (production).
    return request.client.host if request.client else "unknown"


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        # Not written to the audit table: unauthenticated floods must not grow the database.
        raise _unauthorized()

    def reject(reason: str) -> HTTPException:
        write_audit(db, action="AUTH_TOKEN_REJECTED", user="anonymous", resource=request.url.path,
                    ip=client_ip(request), result="FAILURE", severity="WARNING",
                    details={"reason": reason})
        return _unauthorized()

    settings = get_settings()
    try:
        claims = decode_access_token(
            credentials.credentials, secret=settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
    except TokenError as exc:
        raise reject(str(exc)) from exc

    if db.get(RevokedToken, claims["jti"]) is not None:
        raise reject("token revoked")
    try:
        user = db.get(User, int(claims["sub"]))
    except ValueError as exc:
        raise reject("malformed subject") from exc
    if user is None or not user.is_active:
        raise reject("user missing or disabled")

    request.state.token_claims = claims
    return user


def require_permission(*permissions: Permission):
    """Dependency factory: user needs ANY of the listed permissions."""

    def dependency(
        request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
    ) -> User:
        if not any(has_permission(user.role.name, p) for p in permissions):
            write_audit(db, action="ACCESS_DENIED", user=user.username, resource=request.url.path,
                        ip=client_ip(request), result="FAILURE", severity="WARNING",
                        details={"role": user.role.name,
                                 "required_any_of": [p.value for p in permissions]})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return dependency
