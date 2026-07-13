"""HTTP routes for login, registration, OTP, Keycloak SSO, and the current user.

``public_router`` carries no auth dependency and is mounted directly on the
app (via ``main``'s ``public_router``), matching the pre-migration behavior.
``router`` holds the one authenticated endpoint (``/api/auth/me``) and is
mounted on ``main``'s authenticated ``api`` router, inheriting its
``require_auth`` gate.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from news_dashboard.auth import (
    _session_days,
    authenticate,
    consume_otp,
    create_otp_for_user,
    create_session_token,
    exchange_keycloak_code,
    get_or_create_otp_user,
    keycloak_auth_metadata,
    keycloak_authorization_url,
    keycloak_config,
    keycloak_logout_url,
    keycloak_registration_url,
    require_auth,
)
from news_dashboard.auth_routes.models import LoginRequest, OTPLoginPayload, OTPRequestPayload
from news_dashboard.login_throttle import clear_failures, is_throttled, record_failure

SESSION_COOKIE = "nd_session"
OAUTH_STATE_COOKIE = "nd_oauth_state"
OAUTH_NEXT_COOKIE = "nd_oauth_next"

public_router = APIRouter()
router = APIRouter()


def _safe_next_path(next_path: str | None) -> str | None:
    """Only accept an app-relative path so Keycloak can't be used as an open redirect."""
    if not next_path or not next_path.startswith("/") or next_path.startswith("//"):
        return None
    if "://" in next_path:
        return None
    return next_path


def _login_error_redirect(error_code: str) -> RedirectResponse:
    redirect = RedirectResponse(url=f"/login?auth_error={error_code}")
    redirect.delete_cookie(key=OAUTH_STATE_COOKIE, path="/auth/callback")
    redirect.delete_cookie(key=OAUTH_NEXT_COOKIE, path="/auth/callback")
    return redirect


@public_router.get("/api/auth/config")
def auth_config() -> dict[str, Any]:
    return keycloak_auth_metadata()


@public_router.get("/api/auth/metadata")
def auth_metadata() -> dict[str, Any]:
    return keycloak_auth_metadata()


@public_router.get("/auth/login")
def keycloak_login(request: Request) -> RedirectResponse:
    if not keycloak_config().enabled:
        return RedirectResponse(url="/login")
    state = secrets.token_urlsafe(32)
    redirect = RedirectResponse(url=keycloak_authorization_url(state))
    redirect.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,
        path="/auth/callback",
    )
    next_path = _safe_next_path(request.query_params.get("next"))
    if next_path:
        redirect.set_cookie(
            key=OAUTH_NEXT_COOKIE,
            value=next_path,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=600,
            path="/auth/callback",
        )
    return redirect


@public_router.get("/auth/register")
def keycloak_register(request: Request) -> RedirectResponse:
    if not keycloak_config().enabled:
        return RedirectResponse(url="/login")
    state = secrets.token_urlsafe(32)
    redirect = RedirectResponse(url=keycloak_registration_url(state))
    redirect.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,
        path="/auth/callback",
    )
    next_path = _safe_next_path(request.query_params.get("next"))
    if next_path:
        redirect.set_cookie(
            key=OAUTH_NEXT_COOKIE,
            value=next_path,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=600,
            path="/auth/callback",
        )
    return redirect


@public_router.get("/auth/callback")
async def keycloak_callback(request: Request) -> RedirectResponse:
    provider_error = request.query_params.get("error")
    if provider_error:
        return _login_error_redirect("oauth_denied")

    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not expected_state or not state or not secrets.compare_digest(expected_state, state):
        return _login_error_redirect("oauth_state")
    if not code:
        return _login_error_redirect("oauth_code")

    try:
        user = await exchange_keycloak_code(code)
    except HTTPException:
        return _login_error_redirect("oauth_exchange_failed")

    token = create_session_token(user["id"], bool(user["is_admin"]))
    next_path = _safe_next_path(request.cookies.get(OAUTH_NEXT_COOKIE)) or "/"
    redirect = RedirectResponse(url=next_path)
    redirect.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_session_days() * 86400,
        path="/",
    )
    redirect.delete_cookie(key=OAUTH_STATE_COOKIE, path="/auth/callback")
    redirect.delete_cookie(key=OAUTH_NEXT_COOKIE, path="/auth/callback")
    return redirect


@public_router.get("/auth/logout")
def keycloak_logout() -> RedirectResponse:
    redirect = RedirectResponse(url=keycloak_logout_url())
    redirect.delete_cookie(key=SESSION_COOKIE, path="/")
    return redirect


@public_router.post("/api/auth/login")
def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    if keycloak_config().enabled:
        raise HTTPException(status_code=409, detail="Password login is disabled; use Keycloak")
    if is_throttled(payload.username):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts; try again later",
        )
    user = authenticate(payload.username, payload.password)
    if not user:
        record_failure(payload.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    clear_failures(payload.username)
    token = create_session_token(user["id"], bool(user["is_admin"]))
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_session_days() * 86400,
        path="/",
    )
    return {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}


@public_router.get("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


@public_router.post("/api/auth/otp/request")
def otp_request(payload: OTPRequestPayload, background_tasks: BackgroundTasks) -> dict[str, str]:
    from news_dashboard.email import send_otp_email

    request_key = f"otp-request:{payload.email.strip().lower()}"
    if is_throttled(request_key):
        raise HTTPException(status_code=429, detail="Too many code requests; try again later")
    record_failure(request_key)

    user = get_or_create_otp_user(payload.email)
    if user:
        otp = create_otp_for_user(int(user["id"]))
        background_tasks.add_task(send_otp_email, payload.email, otp)
    # Always return success to prevent user enumeration
    return {"status": "sent"}


@public_router.post("/api/auth/otp/login")
def otp_login(payload: OTPLoginPayload, response: Response) -> dict[str, Any]:
    login_key = f"otp-login:{payload.email.strip().lower()}"
    if is_throttled(login_key):
        raise HTTPException(status_code=429, detail="Too many code attempts; try again later")

    user = consume_otp(payload.email, payload.otp)
    if not user:
        record_failure(login_key)
        raise HTTPException(status_code=401, detail="Invalid or expired code")
    clear_failures(login_key)
    token = create_session_token(int(user["id"]), bool(user["is_admin"]))
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_session_days() * 86400,
        path="/",
    )
    return {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}


@router.get("/api/auth/me")
def auth_me(current_user: Annotated[dict[str, Any], Depends(require_auth)]) -> dict[str, Any]:
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user.get("email"),
        "is_admin": bool(current_user["is_admin"]),
    }
