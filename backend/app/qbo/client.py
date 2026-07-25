"""
Thin QuickBooks Online API client: resolves the base URL for sandbox vs
production, keeps the access token fresh (refreshing via oauth.py when it's
close to expiring), and exposes the handful of operations the sync/
reconciliation flows need (create an entity, run a query, fetch a report).

The HTTP calls themselves (requests.post/get) are the one piece of this whole
pipeline that genuinely cannot be verified without a live sandbox connection -
everything upstream of the actual network call (which entity, which payload,
when to refresh, how to interpret a failure) is unit-tested with a fake
`transport` standing in for `requests`.
"""
import requests
from pymongo.database import Database

from app.config import Settings
from app.qbo import connection_store, oauth

SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com"
PRODUCTION_BASE = "https://quickbooks.api.intuit.com"


class QBONotConnectedError(RuntimeError):
    pass


class QBOAPIError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"QBO API error ({status_code}): {body}")
        self.status_code = status_code
        self.body = body


class QBOClient:
    def __init__(self, db: Database, settings: Settings, transport=requests):
        self.db = db
        self.settings = settings
        self.transport = transport

    def _base_url(self) -> str:
        return SANDBOX_BASE if self.settings.qbo_environment == "sandbox" else PRODUCTION_BASE

    def _connection(self) -> dict:
        connection = connection_store.get_connection(self.db)
        if connection is None:
            raise QBONotConnectedError("Not connected to QuickBooks Online. Visit GET /api/qbo/connect first.")
        return connection

    def _access_token(self) -> tuple[str, str]:
        connection = self._connection()
        if connection_store.is_access_token_expired(connection):
            tokens = oauth.refresh_tokens(self.settings, connection["refresh_token"])
            connection_store.update_access_token(
                self.db, tokens["access_token"], tokens["refresh_token"], tokens["expires_in"]
            )
            return tokens["access_token"], connection["realm_id"]
        return connection["access_token"], connection["realm_id"]

    def _headers(self, access_token: str) -> dict:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def create_entity(self, entity_type: str, body: dict) -> dict:
        access_token, realm_id = self._access_token()
        url = f"{self._base_url()}/v3/company/{realm_id}/{entity_type}"
        resp = self.transport.post(url, json=body, headers=self._headers(access_token), timeout=30)
        if resp.status_code >= 300:
            raise QBOAPIError(resp.status_code, resp.text)
        return resp.json()[entity_type.capitalize()]

    def query(self, sql: str) -> dict:
        access_token, realm_id = self._access_token()
        url = f"{self._base_url()}/v3/company/{realm_id}/query"
        resp = self.transport.get(
            url, params={"query": sql}, headers=self._headers(access_token), timeout=30
        )
        if resp.status_code >= 300:
            raise QBOAPIError(resp.status_code, resp.text)
        return resp.json()

    def get_profit_and_loss(self, start_date: str, end_date: str) -> dict:
        access_token, realm_id = self._access_token()
        url = f"{self._base_url()}/v3/company/{realm_id}/reports/ProfitAndLoss"
        resp = self.transport.get(
            url,
            params={"start_date": start_date, "end_date": end_date, "accounting_method": "Cash"},
            headers=self._headers(access_token),
            timeout=30,
        )
        if resp.status_code >= 300:
            raise QBOAPIError(resp.status_code, resp.text)
        return resp.json()
