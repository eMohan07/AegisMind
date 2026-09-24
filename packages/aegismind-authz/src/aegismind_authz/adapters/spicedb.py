from __future__ import annotations

import logging
from typing import Any

from aegismind_types import Principal, TokenConsistency

from aegismind_authz.mappers import decode_subject, encode_subject
from aegismind_authz.ports import AuthzPort, CheckRequest, RelationshipTuple

logger = logging.getLogger(__name__)

# Production Zed Schema for AegisMind Zanzibar authorization
AEGISMIND_ZED_SCHEMA = """
definition user {}

definition group {
    relation member: user | group#member
}

definition folder {
    relation reader: user | group#member | folder#reader
    relation writer: user | group#member | folder#writer

    permission view = reader + writer
    permission edit = writer
}

definition document {
    relation folder: folder
    relation viewer: user | user:* | group#member | folder#reader
    relation editor: user | group#member | folder#writer
    relation owner: user

    permission view = viewer + editor + owner + folder->view
    permission edit = editor + owner + folder->edit
}
""".strip()


class SpiceDBAuthzAdapter(AuthzPort):
    """Production gRPC adapter connecting to Authzed / SpiceDB using Zanzibar schema."""

    def __init__(
        self,
        endpoint: str = "localhost:50051",
        token: str = "aegismind_preshared_key",  # noqa: S107
        use_ssl: bool = False,
        client: Any | None = None,
        auto_connect: bool = True,
    ) -> None:
        self.endpoint = endpoint
        self.token = token
        self.use_ssl = use_ssl
        self._client = client

        if self._client is None and auto_connect:
            self._client = self._create_client()

        logger.info(
            "Configured SpiceDBAuthzAdapter targeting %s (ssl=%s)",
            self.endpoint,
            self.use_ssl,
        )

    def _create_client(self) -> Any:
        try:
            from authzed.api.v1 import Client, InsecureClient
            from grpc import ssl_channel_credentials

            if self.use_ssl:
                creds = ssl_channel_credentials()
                return Client(self.endpoint, creds)
            return InsecureClient(self.endpoint, self.token)
        except ImportError:
            logger.warning("authzed package is not available. SpiceDB adapter requires 'authzed'.")
            return None

    def _split_resource(self, resource_str: str) -> tuple[str, str]:
        if ":" in resource_str:
            res_type, res_id = resource_str.split(":", 1)
            return res_type, res_id
        return "document", resource_str

    async def bulk_check(
        self,
        requests: list[CheckRequest],
        consistency: TokenConsistency | None = None,
    ) -> list[bool]:
        if not requests:
            return []

        if self._client is None:
            raise RuntimeError(
                "SpiceDB client is not available. Install 'authzed' or provide a mock client."
            )

        from authzed.api.v1 import (
            CheckBulkPermissionsRequest,
            CheckBulkPermissionsRequestItem,
            Consistency,
            ObjectReference,
            SubjectReference,
            ZedToken,
        )

        req_items: list[Any] = []
        for req in requests:
            res_type, res_id = self._split_resource(req.resource)
            subj_type, subj_id, subj_rel = decode_subject(req.subject)

            req_items.append(
                CheckBulkPermissionsRequestItem(
                    resource=ObjectReference(
                        object_type=res_type,
                        object_id=res_id,
                    ),
                    permission=req.permission,
                    subject=SubjectReference(
                        object=ObjectReference(
                            object_type=subj_type,
                            object_id=subj_id,
                        ),
                        optional_relation=subj_rel or "",
                    ),
                )
            )

        spice_consistency: Any
        if consistency and consistency.token:
            spice_consistency = Consistency(at_least_as_fresh=ZedToken(token=consistency.token))
        else:
            spice_consistency = Consistency(minimize_latency=True)

        call_req = CheckBulkPermissionsRequest(
            items=req_items,
            consistency=spice_consistency,
        )

        response = self._client.permissions_service.CheckBulkPermissions(call_req)
        results: list[bool] = []
        for pair in response.pairs:
            has_permission = pair.item.permissionship == 1  # PERMISSIONSHIP_HAS_PERMISSION
            results.append(has_permission)

        return results

    async def write_tuples(
        self,
        tuples: list[RelationshipTuple],
    ) -> TokenConsistency:
        if not tuples:
            return TokenConsistency(at_least_as_fresh=True)

        if self._client is None:
            raise RuntimeError(
                "SpiceDB client is not available. Install 'authzed' or provide a mock client."
            )

        from authzed.api.v1 import (
            ObjectReference,
            Relationship,
            RelationshipUpdate,
            SubjectReference,
            WriteRelationshipsRequest,
        )

        updates: list[Any] = []
        for t in tuples:
            res_type, res_id = self._split_resource(t.resource)
            subj_type, subj_id, subj_rel = decode_subject(t.subject)

            updates.append(
                RelationshipUpdate(
                    operation=RelationshipUpdate.Operation.OPERATION_TOUCH,
                    relationship=Relationship(
                        resource=ObjectReference(
                            object_type=res_type,
                            object_id=res_id,
                        ),
                        relation=t.relation,
                        subject=SubjectReference(
                            object=ObjectReference(
                                object_type=subj_type,
                                object_id=subj_id,
                            ),
                            optional_relation=subj_rel or "",
                        ),
                    ),
                )
            )

        resp = self._client.permissions_service.WriteRelationships(
            WriteRelationshipsRequest(updates=updates)
        )
        token_str = resp.written_at.token if resp.written_at else ""
        return TokenConsistency(token=token_str, at_least_as_fresh=True)

    async def delete_tuples(
        self,
        tuples: list[RelationshipTuple],
    ) -> TokenConsistency:
        if not tuples:
            return TokenConsistency(at_least_as_fresh=True)

        if self._client is None:
            raise RuntimeError(
                "SpiceDB client is not available. Install 'authzed' or provide a mock client."
            )

        from authzed.api.v1 import (
            ObjectReference,
            Relationship,
            RelationshipUpdate,
            SubjectReference,
            WriteRelationshipsRequest,
        )

        updates: list[Any] = []
        for t in tuples:
            res_type, res_id = self._split_resource(t.resource)
            subj_type, subj_id, subj_rel = decode_subject(t.subject)

            updates.append(
                RelationshipUpdate(
                    operation=RelationshipUpdate.Operation.OPERATION_DELETE,
                    relationship=Relationship(
                        resource=ObjectReference(
                            object_type=res_type,
                            object_id=res_id,
                        ),
                        relation=t.relation,
                        subject=SubjectReference(
                            object=ObjectReference(
                                object_type=subj_type,
                                object_id=subj_id,
                            ),
                            optional_relation=subj_rel or "",
                        ),
                    ),
                )
            )

        resp = self._client.permissions_service.WriteRelationships(
            WriteRelationshipsRequest(updates=updates)
        )
        token_str = resp.written_at.token if resp.written_at else ""
        return TokenConsistency(token=token_str, at_least_as_fresh=True)

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
