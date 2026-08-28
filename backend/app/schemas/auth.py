"""认证相关 schema。"""
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1)


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    role_code: str
    role_name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    roles: list[RoleOut] = []


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
