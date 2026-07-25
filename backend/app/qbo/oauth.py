"""
Intuit OAuth2 authorization-code flow. This is inherently an interactive,
browser-based step - only you can log into your own Intuit developer account
and click "Authorize," so this module can't be exercised end-to-end in an
automated environment. It's built to spec against Intuit's documented OAuth2
endpoints; connect_flow.md in the repo root walks through running it once
you have your own QBO_CLIENT_ID/QBO_CLIENT_SECRET in .env.
"""
import requests

from app.config import Settings

AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SCOPE = "com.intuit.quickbooks.accounting"


class QBOOAuthError(RuntimeError):
    pass


def build_authorization_url(settings: Settings, state: str) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": settings.qbo_client_id,
        "response_type": "code",
        "scope": SCOPE,
        "redirect_uri": settings.qbo_redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_tokens(settings: Settings, code: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        auth=(settings.qbo_client_id, settings.qbo_client_secret),
        headers={"Accept": "application/json"},
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.qbo_redirect_uri},
        timeout=30,
    )
    if resp.status_code != 200:
        raise QBOOAuthError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def refresh_tokens(settings: Settings, refresh_token: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        auth=(settings.qbo_client_id, settings.qbo_client_secret),
        headers={"Accept": "application/json"},
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=30,
    )
    if resp.status_code != 200:
        raise QBOOAuthError(f"Token refresh failed ({resp.status_code}): {resp.text}")
    return resp.json()
