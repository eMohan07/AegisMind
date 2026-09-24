from __future__ import annotations

import logging
from typing import Any

from aegismind_types import Principal, TokenConsistency

from aegismind_authz.mappers import encode_subject
from aegismind_authz.ports import AuthzPort, CheckRequest, RelationshipTuple

logger = logging.getLogger(__name__)


class OpenFGAAuthzAdapter(AuthzPort):
    """Alternative authorization adapter targeting OpenFGA fine-grained authorization."""

    def __init__(
        self,
        api_url: str = "http://localhost:8080",
        store_id: str = "aegismind_store",
        client: Any | None = None,
    ) -> None:
        self.api_url = api_url
        self.store_id = store_id
        self._client = client
        logger.info(
            "Configured OpenFGAAuthzAdapter targeting %s (store_id=%s)",
            self.api_url,
            self.store_id,
        )

    async def bulk_check(
        self,
        requests: list[CheckRequest],
        consistency: TokenConsistency | None = None,
    ) -> list[bool]:
        if not requests:
            return []

        if self._client is None:
            raise RuntimeError("OpenFGA client is not available. Configure client or mock.")

        results: list[bool] = []
        for req in requests:
            res = self._client.check(
                user=req.subject,
                relation=req.permission,
                object=req.resource,
            )
            # Support both boolean return and object with .allowed attribute
            allowed = getattr(res, "allowed", res) if res is not None else False
            results.append(bool(allowed))

        return results

    async def write_tuples(
        self,
        tuples: list[RelationshipTuple],
    ) -> TokenConsistency:
        if not tuples:
            return TokenConsistency(at_least_as_fresh=True)

        if self._client is None:
            raise RuntimeError("OpenFGA client is not available. Configure client or mock.")

        writes = [{"user": t.subject, "relation": t.relation, "object": t.resource} for t in tuples]
        self._client.write(writes=writes, deletes=[])
        return TokenConsistency(at_least_as_fresh=True)

    async def delete_tuples(
        self,
        tuples: list[RelationshipTuple],
    ) -> TokenConsistency:
        if not tuples:
            return TokenConsistency(at_least_as_fresh=True)

        if self._client is None:
            raise RuntimeError("OpenFGA client is not available. Configure client or mock.")

        deletes = [
            {"user": t.subject, "relation": t.relation, "object": t.resource} for t in tuples
        ]
        self._client.write(writes=[], deletes=deletes)
        return TokenConsistency(at_least_as_fresh=True)

    async def check_permission(
        self,
        subject: Principal,
        relation: str,
        resource: str,
    ) -> bool:
        subject_str = encode_subject(subject)
        req = CheckRequest(resource=resource, permission=relation, subject=subject_str)
        results = await self.bulk_check([req])
        return results[0]
