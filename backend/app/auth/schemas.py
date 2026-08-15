"""Pydantic request/response models for the auth module."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be blank")
        return stripped

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        # Normalized here, not in the service, so every future consumer of
        # this schema (e.g. Story 1.4's login) agrees on the same casing
        # without having to remember to repeat `.strip().lower()`.
        return value.strip().lower()


class RegisterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    # No min_length=8 here (unlike RegisterRequest): login must accept
    # whatever a legitimately-registered password already is, not
    # re-enforce registration's strength rule. max_length is kept purely
    # as a defensive request-size bound.
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Returned directly here (rather than making the frontend fetch /auth/me
    # separately after login) so the account's theme is known synchronously
    # on login -- a second request would leave a render or two painted in
    # the wrong theme before it resolves (Story 5.2).
    theme: str


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    created_at: datetime
    theme: str


class UpdateThemeRequest(BaseModel):
    theme: Literal["light", "dark"]


class ThemeResponse(BaseModel):
    theme: str
