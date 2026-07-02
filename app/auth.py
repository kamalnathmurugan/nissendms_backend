from __future__ import annotations

import base64
import json
from datetime import datetime, UTC
from typing import Any

import httpx
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .config import settings
from .db.base import SessionLocal
from .db.models import User


class AuthError(RuntimeError):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the JWT payload without signature verification (claims inspection only)."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        padding = 4 - len(parts[1]) % 4
        payload_bytes = base64.urlsafe_b64decode(parts[1] + "=" * padding)
        return json.loads(payload_bytes)
    except Exception:
        return {}


def _get_app_token() -> str | None:
    """Obtain an app-only access token for Microsoft Graph using client credentials."""
    if not (
        settings.azure_tenant_id
        and settings.graph_client_id
        and settings.graph_client_secret
    ):
        return None
    try:
        url = (
            f"https://login.microsoftonline.com/{settings.azure_tenant_id}"
            f"/oauth2/v2.0/token"
        )
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.graph_client_id,
                    "client_secret": settings.graph_client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
        if resp.status_code == 200:
            return resp.json().get("access_token")
    except Exception:
        pass
    return None


def _profile_from_graph(access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(f"{settings.graph_base_url}/me", headers=headers)
    if response.status_code >= 400:
        raise AuthError(response.text)
    return response.json()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def check_email_in_tenant(email: str) -> bool:
    """
    Return True if *email* exists as a member or invited B2B guest in the
    configured Entra tenant (uses app-only Graph credentials).

    Falls back to True (permissive) when Graph credentials are not configured so
    local development keeps working without them.
    """
    app_token = _get_app_token()
    if not app_token:
        # Graph not fully configured — allow through; Entra will gatekeep.
        return True

    try:
        # OData filter matches both internal members and B2B guest accounts
        url = (
            f"{settings.graph_base_url}/users"
            f"?$filter=mail eq '{email}' or userPrincipalName eq '{email}'"
            f"&$select=id,mail,userPrincipalName,userType"
            f"&$top=1"
        )
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                url, headers={"Authorization": f"Bearer {app_token}"}
            )
        if resp.status_code == 200:
            return len(resp.json().get("value", [])) > 0
    except Exception:
        # Network / Graph error — fail open so legitimate users aren't locked out.
        pass
    return True


def store_user_profile(
    profile: dict[str, Any], *, tenant_id: str | None = None
) -> dict[str, Any]:
    tenant_value = tenant_id or settings.azure_tenant_id or ""
    oid = profile.get("id") or profile.get("userPrincipalName") or ""
    email = profile.get("mail") or profile.get("userPrincipalName") or ""
    display_name = profile.get("displayName") or profile.get("givenName") or email

    if SessionLocal is None:
        return {
            "azure_oid": oid,
            "email": email,
            "display_name": display_name,
            "tenant_id": tenant_value,
            "source": "memory",
        }

    try:
        db: Session = SessionLocal()
    except Exception:
        return {
            "azure_oid": oid,
            "email": email,
            "display_name": display_name,
            "tenant_id": tenant_value,
            "source": "memory",
        }

    try:
        user = db.query(User).filter(User.azure_oid == oid).first()
        if user is None:
            user = User(
                azure_oid=oid,
                tenant_id=tenant_value,
                email=email,
                display_name=display_name,
                given_name=profile.get("givenName") or "",
                surname=profile.get("surname") or "",
                preferred_username=profile.get("userPrincipalName") or email,
                last_login_at=datetime.now(UTC),
            )
            db.add(user)
        else:
            user.tenant_id = tenant_value
            user.email = email
            user.display_name = display_name
            user.given_name = profile.get("givenName") or user.given_name or ""
            user.surname = profile.get("surname") or user.surname or ""
            user.preferred_username = profile.get("userPrincipalName") or email
            user.last_login_at = datetime.now(UTC)
            user.is_active = True
        db.commit()
        db.refresh(user)
        return {
            "id": user.id,
            "azure_oid": user.azure_oid,
            "email": user.email,
            "display_name": user.display_name,
            "tenant_id": user.tenant_id,
            "source": "database",
        }
    except OperationalError:
        return {
            "azure_oid": oid,
            "email": email,
            "display_name": display_name,
            "tenant_id": tenant_value,
            "source": "memory",
        }
    finally:
        db.close()


# Tenant GUID used by Microsoft for all personal (MSA / consumer) accounts
_MSA_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"


def authenticate_user(
    access_token: str, *, tenant_id: str | None = None
) -> dict[str, Any]:
    """
    Validate the access token, enforce tenant membership, and return the user profile.

    Rejects:
      - Personal Microsoft Account tokens (``tid`` == MSA tenant GUID)
      - Tokens issued for a different Entra tenant (``tid`` != configured tenant)
    """
    claims = _decode_jwt_payload(access_token)
    token_tid = claims.get("tid", "")
    expected_tid = settings.azure_tenant_id

    # Block personal Microsoft Account (MSA / consumer) tokens
    if token_tid == _MSA_TENANT_ID:
        raise AuthError(
            "Personal Microsoft accounts are not allowed. "
            "Please sign in with your work or invited guest account."
        )

    # Block tokens issued for a different Entra tenant
    if expected_tid and token_tid and token_tid != expected_tid:
        raise AuthError(
            "Your account does not belong to the authorised tenant. "
            "Contact your administrator to request access."
        )

    profile = _profile_from_graph(access_token)
    return store_user_profile(profile, tenant_id=tenant_id)
