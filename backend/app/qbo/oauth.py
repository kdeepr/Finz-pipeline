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
    try:
        resp = requests.post(
            TOKEN_URL,
            auth=(settings.qbo_client_id, settings.qbo_client_secret),
            headers={"Accept": "application/json"},
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.qbo_redirect_uri},
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        # A network-level failure (timeout, DNS, connection refused) here is
        # otherwise indistinguishable from a crash - route it through the
        # same error path as an HTTP-level failure so /callback shows the
        # user a clean banner instead of an unhandled 500.
        raise QBOOAuthError(f"Could not reach Intuit's token endpoint: {exc}") from exc
    if resp.status_code != 200:
        raise QBOOAuthError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def refresh_tokens(settings: Settings, refresh_token: str) -> dict:
    try:
        resp = requests.post(
            TOKEN_URL,
            auth=(settings.qbo_client_id, settings.qbo_client_secret),
            headers={"Accept": "application/json"},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        raise QBOOAuthError(f"Could not reach Intuit's token endpoint: {exc}") from exc
    if resp.status_code != 200:
        raise QBOOAuthError(f"Token refresh failed ({resp.status_code}): {resp.text}")
    return resp.json()
