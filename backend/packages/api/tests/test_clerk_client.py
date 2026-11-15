import asyncio
import json

import httpx
import pytest
from codecraft_api.clerk_client import ClerkClient, ClerkOrganisation


def test_reusing_an_organisation_updates_metadata_through_the_metadata_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "org_1"})

    client = ClerkClient("sk_test_secret")
    mock = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.clerk.com/v1",
    )
    monkeypatch.setattr(client, "_client", mock)
    organisation = ClerkOrganisation(
        id="org_1",
        name="Design",
        private_metadata={"codecraft_idempotency_key": "key-a"},
    )

    async def run() -> None:
        try:
            await client.record_organisation_idempotency_key(
                organisation=organisation,
                idempotency_key="key-b",
            )
        finally:
            await mock.aclose()

    asyncio.run(run())

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "PATCH"
    assert request.url.path == "/v1/organizations/org_1/metadata"
    body = json.loads(request.content)
    assert body["private_metadata"]["codecraft_idempotency_keys"] == ["key-a", "key-b"]
