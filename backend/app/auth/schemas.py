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
    # Same reasoning as `theme` above, for the account's saved UI language.
    language: str


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    created_at: datetime
    theme: str
    language: str
    # Story 1.6: `User` has no `email_verified` attribute -- `validation_alias`
    # points this field at the ORM object's `email_verified_at` instead (the
    # `from_attributes` lookup key), and the `mode="before"` validator below
    # collapses that raw timestamp-or-None into a plain bool. Exposing a
    # bool rather than the timestamp itself: nothing today needs *when*,
    # just whether, and this is naturally what SettingsPage will render.
    email_verified: bool = Field(default=False, validation_alias="email_verified_at")

    @field_validator("email_verified", mode="before")
    @classmethod
    def _derive_email_verified(cls, value: object) -> bool:
        return value is not None


class UpdateThemeRequest(BaseModel):
    theme: Literal["light", "dark"]


class ThemeResponse(BaseModel):
    theme: str


class UpdateLanguageRequest(BaseModel):
    language: Literal["en", "bg", "de"]


class LanguageResponse(BaseModel):
    language: str


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)

    # Mirrors RegisterRequest's `_strip_full_name` validator -- same rule
    # (must not be blank after trimming), same field, so it should reject
    # the same way here as it does at registration.
    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be blank")
        return stripped


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    # Reuses RegisterRequest's min_length=8, max_length=128 bound (per the
    # I/O matrix) so registration and password-change enforce the exact
    # same strength rule.
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordResponse(BaseModel):
    detail: str = "Password updated."


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class VerifyEmailResponse(BaseModel):
    detail: str = "Email verified."


class ResendVerificationRequest(BaseModel):
    email: EmailStr

    # Mirrors RegisterRequest/LoginRequest's own normalization -- every
    # consumer of an email field in this module agrees on the same casing.
    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResendVerificationResponse(BaseModel):
    detail: str = "If that account exists and isn't verified yet, we've sent a new link."
