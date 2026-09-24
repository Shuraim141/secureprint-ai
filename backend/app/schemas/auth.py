from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.security.rbac import ROLE_PERMISSIONS, RoleName


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  # OAuth token type label, not a secret
    expires_in: int
    username: str
    role: str


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    permissions: list[str]  # for UI gating only; the API enforces permissions itself

    @classmethod
    def from_user(cls, user) -> "UserOut":
        return cls(id=user.id, username=user.username, full_name=user.full_name,
                   role=user.role.name, is_active=user.is_active, created_at=user.created_at,
                   permissions=sorted(p.value for p in ROLE_PERMISSIONS.get(user.role.name, ())))


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,64}$")
    password: str = Field(min_length=10, max_length=128)
    full_name: str | None = Field(default=None, max_length=128)
    role: RoleName

    @model_validator(mode="after")
    def _password_must_not_contain_username(self):
        if self.username.lower() in self.password.lower():
            raise ValueError("Password must not contain the username")
        return self


class RoleUpdate(BaseModel):
    role: RoleName
