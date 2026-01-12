from pydantic import BaseModel, EmailStr, validator, root_validator, Field
from typing import Optional
import logging
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger('application')

class GoogleAuthSchema(BaseModel):
    """
    Strict Schema for Google Authentication Input.
    Validates the ID Token structure before processing.
    """
    id_token: str
    role: Optional[str] = "client" # Default to client if not provided

    @validator('id_token')
    def validate_token(cls, v):
        if not v or len(v) < 50:
            logger.warning("Invalid Google ID Token length detected.")
            raise ValueError("Invalid Google ID Token format.")
        return v
    
    @validator('role')
    def validate_role(cls, v):
        allowed = ['vendor', 'client', 'staff', 'editor', 'support', 'assistant', 'admin']
        if v.lower() not in allowed:
             raise ValueError(f"Invalid role. Allowed: {allowed}")
        return v.lower()

class LoginSchema(BaseModel):
    """
    Schema for Standard Login (Email or Phone).
    """
    email_or_phone: str
    password: str

class RegistrationSchema(BaseModel):
    """
    Strict Schema for User Registration.
    Enforces: Passwords match, Valid Role, One Identifier.
    """
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str
    password_confirm: str
    role: str = "client"

    @validator('role')
    def validate_role(cls, v):
        if v not in ['vendor', 'client']:
            raise ValueError("Role must be 'vendor' or 'client'.")
        return v

    @root_validator(pre=True)
    def check_identifiers_and_passwords(cls, values):
        # 1. Password Match
        p1 = values.get('password')
        p2 = values.get('password_confirm')
        if p1 and p2 and p1 != p2:
            raise ValueError("Passwords do not match.")

        # 2. Mutually Exclusive Identifiers
        email = values.get('email')
        phone = values.get('phone')
        
        if email and phone:
            raise ValueError("Provide either Email OR Phone, not both.")
        if not email and not phone:
            raise ValueError("One identifier (Email or Phone) is required.")
            
        return values

class PasswordResetRequestSchema(BaseModel):
    email_or_phone: str

class PasswordResetConfirmSchema(BaseModel):
    token: str # OTP or Link Token
    uidb64: Optional[str] = None # For Email links
    new_password: str
    confirm_password: str

    @root_validator(skip_on_failure=True)
    def check_passwords(cls, values):
        if values.get('new_password') != values.get('confirm_password'):
            raise ValueError("Passwords do not match.")
        return values

class ChangePasswordSchema(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str

    @root_validator(skip_on_failure=True)
    def check_passwords(cls, values):
        if values.get('new_password') != values.get('confirm_password'):
            raise ValueError("New passwords do not match.")
        return values
