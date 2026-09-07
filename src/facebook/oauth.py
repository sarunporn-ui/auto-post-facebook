"""'Connect a Facebook Page' — server-side Facebook Login (OAuth) flow.

    1. POST /api/facebook/oauth-start   (authed)  -> {authorize_url}
    2. browser -> Facebook -> GET /connect/facebook/callback?code&state
                              -> stores the user's Pages, redirects /dashboard?fb=pick
    3. GET  /api/facebook/pending-pages (authed)  -> [{id,name}, ...]
    4. POST /api/facebook/select-page   (authed)  -> saves the FacebookConnection
    5. GET/DELETE /api/facebook/connection        -> status / disconnect

Page tokens returned by /me/accounts when the user token is long-lived are
themselves long-lived and effectively non-expiring, so no per-page exchange
is needed.
"""
from __future__ import annotations
import json
import logging
import secrets
import time
import urllib.parse

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from src.auth import get_current_user
from src.config import get_settings
from src.crypto import decrypt, encrypt
from src.db import get_session
from src.models import FacebookConnection, FacebookOAuthFlow, User
from src.repositories import facebook_repo, get_facebook_connection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["facebook"])

_FLOW_TTL_SECONDS = 900


def _graph_base() -> str:
    return f"https://graph.facebook.com/{get_settings().facebook_graph_api_version}"


def _require_fb_config():
    s = get_settings()
    if not (s.facebook_app_id and s.facebook_app_secret and s.facebook_redirect_uri):
        raise HTTPException(
            status_code=503,
            detail="Facebook integration is not configured on the server "
            "(FACEBOOK_APP_ID / FACEBOOK_APP_SECRET / FACEBOOK_REDIRECT_URI).",
        )
    return s


@router.post("/api/facebook/oauth-start")
def oauth_start(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    s = _require_fb_config()
    state = secrets.token_urlsafe(24)

    flow = session.get(FacebookOAuthFlow, current_user.id)
    if flow is None:
        flow = FacebookOAuthFlow(user_id=current_user.id, state=state)
    else:
        flow.state = state
        flow.encrypted_pages_json = ""
        flow.created_at = time.time()
    session.add(flow)
    session.commit()

    params = {
        "client_id": s.facebook_app_id,
        "redirect_uri": s.facebook_redirect_uri,
        "state": state,
        "scope": s.facebook_scopes,
        "response_type": "code",
    }
    authorize_url = "https://www.facebook.com/{ver}/dialog/oauth?{qs}".format(
        ver=s.facebook_graph_api_version,
        qs=urllib.parse.urlencode(params),
    )
    return {"authorize_url": authorize_url}


@router.get("/connect/facebook/callback")
def oauth_callback(
    session: Session = Depends(get_session),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    s = _require_fb_config()
    dash = s.app_base_url.rstrip("/") + "/dashboard"

    if error or not code or not state:
        return RedirectResponse(dash + "?fb=error")

    flow = session.exec(
        select(FacebookOAuthFlow).where(FacebookOAuthFlow.state == state)
    ).first()
    if flow is None or time.time() - flow.created_at > _FLOW_TTL_SECONDS:
        return RedirectResponse(dash + "?fb=expired")

    try:
        # code -> short-lived user token
        r = requests.get(
            f"{_graph_base()}/oauth/access_token",
            params={
                "client_id": s.facebook_app_id,
                "client_secret": s.facebook_app_secret,
                "redirect_uri": s.facebook_redirect_uri,
                "code": code,
            },
            timeout=30,
        )
        r.raise_for_status()
        short_token = r.json()["access_token"]

        # short-lived -> long-lived user token
        r = requests.get(
            f"{_graph_base()}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": s.facebook_app_id,
                "client_secret": s.facebook_app_secret,
                "fb_exchange_token": short_token,
            },
            timeout=30,
        )
        r.raise_for_status()
        long_token = r.json()["access_token"]

        # list the Pages the user manages (each entry carries its own Page token)
        pages: list[dict] = []
        url = f"{_graph_base()}/me/accounts"
        params = {"access_token": long_token, "fields": "id,name,access_token", "limit": 100}
        while url:
            pr = requests.get(url, params=params, timeout=30)
            pr.raise_for_status()
            body = pr.json()
            pages.extend(body.get("data", []))
            url = body.get("paging", {}).get("next")
            params = None  # `next` is a fully-formed URL
    except Exception as exc:
        logger.exception("Facebook OAuth callback failed")
        return RedirectResponse(dash + "?fb=error")

    flow.encrypted_pages_json = encrypt(json.dumps(pages))
    session.add(flow)
    session.commit()
    return RedirectResponse(dash + "?fb=pick")


def _load_flow_pages(session: Session, user_id: str) -> list[dict]:
    flow = session.get(FacebookOAuthFlow, user_id)
    if flow is None or not flow.encrypted_pages_json:
        raise HTTPException(status_code=404, detail="No Facebook connection in progress")
    if time.time() - flow.created_at > _FLOW_TTL_SECONDS:
        raise HTTPException(status_code=410, detail="Connection attempt expired — start again")
    return json.loads(decrypt(flow.encrypted_pages_json))


@router.get("/api/facebook/pending-pages")
def pending_pages(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    pages = _load_flow_pages(session, current_user.id)
    return [{"id": p["id"], "name": p.get("name", p["id"])} for p in pages]


class SelectPageRequest(BaseModel):
    page_id: str


@router.post("/api/facebook/select-page")
def select_page(
    payload: SelectPageRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    s = get_settings()
    pages = _load_flow_pages(session, current_user.id)
    page = next((p for p in pages if p["id"] == payload.page_id), None)
    if page is None or not page.get("access_token"):
        raise HTTPException(status_code=400, detail="That Page is not in the connected account")

    existing = get_facebook_connection(session, current_user.id)
    if existing:
        session.delete(existing)
        session.commit()

    conn = FacebookConnection(
        user_id=current_user.id,
        page_id=page["id"],
        page_name=page.get("name", ""),
        encrypted_page_token=encrypt(page["access_token"]),
        scopes=s.facebook_scopes,
    )
    facebook_repo.add(session, conn)

    flow = session.get(FacebookOAuthFlow, current_user.id)
    if flow:
        session.delete(flow)
        session.commit()

    return {"connected": True, "page_name": conn.page_name}


@router.get("/api/facebook/connection")
def get_connection(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    conn = get_facebook_connection(session, current_user.id)
    if not conn:
        return {"connected": False}
    return {"connected": True, "page_name": conn.page_name, "page_id": conn.page_id}


@router.delete("/api/facebook/connection")
def delete_connection(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    conn = get_facebook_connection(session, current_user.id)
    if conn:
        session.delete(conn)
        session.commit()
    return {"connected": False}
