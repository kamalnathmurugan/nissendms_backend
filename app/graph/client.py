"""Microsoft Graph client — app-only (client-credentials) auth.

Acquires a token for the backend Entra app via MSAL and exposes thin async
request helpers. Tokens are cached by MSAL and refreshed automatically.
"""
import httpx
import msal

from ..config import settings


class GraphError(RuntimeError):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"Graph {status}: {message}")


class GraphClient:
    def __init__(self):
        self._app = msal.ConfidentialClientApplication(
            client_id=settings.graph_client_id,
            authority=settings.authority_url,
            client_credential=settings.graph_client_secret,
        )

    def _token(self) -> str:
        result = self._app.acquire_token_silent([settings.graph_scope], account=None)
        if not result:
            result = self._app.acquire_token_for_client(scopes=[settings.graph_scope])
        if "access_token" not in result:
            raise GraphError(
                401,
                result.get("error_description", result.get("error", "token failure")),
            )
        return result["access_token"]

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self._token()}"}
        if extra:
            h.update(extra)
        return h

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        content: bytes | None = None,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        url = path if path.startswith("http") else f"{settings.graph_base_url}{path}"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.request(
                method,
                url,
                json=json,
                content=content,
                headers=self._headers(headers),
                params=params,
            )
        if resp.status_code >= 400:
            raise GraphError(resp.status_code, resp.text)
        return resp

    async def get(self, path: str, **kw) -> dict:
        return (await self.request("GET", path, **kw)).json()

    async def post(self, path: str, **kw) -> dict:
        r = await self.request("POST", path, **kw)
        return r.json() if r.content else {}

    async def delete(self, path: str, **kw) -> None:
        await self.request("DELETE", path, **kw)


_client: GraphClient | None = None


def graph() -> GraphClient:
    """Lazily-constructed singleton (only valid when Graph is configured)."""
    global _client
    if _client is None:
        _client = GraphClient()
    return _client
