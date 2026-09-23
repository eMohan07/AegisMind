from __future__ import annotations

import logging
from typing import Any

from aegismind_core.domain.permissions import (
    AuthzDecision,
    ConsistencyRequirement,
    ConsistencyToken,
    PermissionCheck,
    Resource,
    Subject,
)
from aegismind_core.ports.authz import AuthzPort

logger = logging.getLogger(__name__)

# Standard SpiceDB Zanzibar schema for AegisMind
AEGISMIND_SPICEDB_SCHEMA = """
definition user {}

definition folder {
    relation reader: user | folder#reader
    relation writer: user | folder#writer

    permission view = reader + writer
    permission edit = writer
}

definition document {
    relation folder: folder
    relation reader: user | user:* | folder#reader
    relation writer: user | folder#writer

    permission view = reader + writer + folder->view
    permission edit = writer + folder->edit
}
""".strip()


class SpiceDBAuthzAdapter(AuthzPort):
    """Zanzibar authorization adapter backed by SpiceDB.

    Translates AegisMind permission checks to SpiceDB CheckPermission
    and CheckBulkPermissions API calls with zed token consistency.
    """

    def __init__(
        self,
        endpoint: str = "localhost:50051",
        preshared_key: str = "aegismind_dev_key",
        use_ssl: bool = False,
        client: Any | None = None,
        auto_connect: bool = True,
    ) -> None:
        self.endpoint = endpoint
        self.preshared_key = preshared_key
        self.use_ssl = use_ssl
        self._client = client

        if self._client is None and auto_connect:
            self._client = self._init_client()

        logger.info(
            "Configured SpiceDBAuthzAdapter targeting %s (ssl=%s)",
            self.endpoint,
            self.use_ssl,
        )

    def _init_client(self) -> Any:
        try:
            from authzed.api.v1 import Client, InsecureClient
            from grpc import ssl_channel_credentials

            if self.use_ssl:
                creds = ssl_channel_credentials()
                return Client(self.endpoint, creds)
            return InsecureClient(self.endpoint, self.preshared_key)
        except ImportError:
            logger.warning(
                "authzed-py library is not installed. SpiceDB calls will require a configured "
                "client or installed authzed dependency."
            )
            return None

    def _build_consistency(self, consistency: ConsistencyToken | None) -> Any:
        """Construct SpiceDB consistency proto object."""
        from authzed.api.v1 import Consistency, ZedToken

        is_at_least_fresh = (
            consistency is None
            or consistency.requirement == ConsistencyRequirement.AT_LEAST_AS_FRESH
        )
        if is_at_least_fresh:
            if consistency and consistency.token:
                return Consistency(at_least_as_fresh=ZedToken(token=consistency.token))
            return Consistency(minimize_latency=True)
        if consistency and consistency.requirement == ConsistencyRequirement.FULLY_CONSISTENT:
            return Consistency(fully_consistent=True)
        return Consistency(minimize_latency=True)

    async def check(
        self,
        check: PermissionCheck,
        consistency: ConsistencyToken | None = None,
    ) -> AuthzDecision:
        results = await self.bulk_check([check], consistency)
        return results[0]

    async def bulk_check(
        self,
        checks: list[PermissionCheck],
        consistency: ConsistencyToken | None = None,
    ) -> list[AuthzDecision]:
        if not checks:
            return []

        if self._client is None:
            raise RuntimeError(
                "SpiceDB client is not available. Install 'authzed' or provide a mock client."
            )

        try:
            from authzed.api.v1 import (
                CheckBulkPermissionsRequest,
                CheckBulkPermissionsRequestItem,
                ObjectReference,
                SubjectReference,
            )

            req_items = []
            for item in checks:
                req_items.append(
                    CheckBulkPermissionsRequestItem(
                        resource=ObjectReference(
                            object_type=item.resource.type,
                            object_id=item.resource.id,
                        ),
                        permission=item.permission,
                        subject=SubjectReference(
                            object=ObjectReference(
                                object_type=item.subject.type,
                                object_id=item.subject.id,
                            ),
                            optional_relation=item.subject.relation or "",
                        ),
                    )
                )

            spice_consistency = self._build_consistency(consistency)
            request = CheckBulkPermissionsRequest(
                items=req_items,
                consistency=spice_consistency,
            )

            response = self._client.permissions_service.CheckBulkPermissions(request)

            decisions: list[AuthzDecision] = []
            for pair in response.pairs:
                has_permission = pair.item.permissionship == 1
                reason = (
                    "Allowed by SpiceDB Zanzibar check"
                    if has_permission
                    else "Denied by SpiceDB Zanzibar check"
                )
                decisions.append(
                    AuthzDecision(
                        permitted=has_permission,
                        reason=reason,
                    )
                )

            return decisions

        except Exception as exc:
            logger.error("SpiceDB bulk check error: %s", exc)
            raise

    async def write_relationship(
        self,
        subject: Subject,
        relation: str,
        resource: Resource,
    ) -> str:
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

        update = RelationshipUpdate(
            operation=RelationshipUpdate.Operation.OPERATION_TOUCH,
            relationship=Relationship(
                resource=ObjectReference(
                    object_type=resource.type,
                    object_id=resource.id,
                ),
                relation=relation,
                subject=SubjectReference(
                    object=ObjectReference(
                        object_type=subject.type,
                        object_id=subject.id,
                    ),
                    optional_relation=subject.relation or "",
                ),
            ),
        )

        resp = self._client.permissions_service.WriteRelationships(
            WriteRelationshipsRequest(updates=[update])
        )
        token = resp.written_at.token if resp.written_at else ""
        logger.debug("Wrote relationship in SpiceDB, token: %s", token)
        return token

    async def delete_relationship(
        self,
        subject: Subject,
        relation: str,
        resource: Resource,
    ) -> str:
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

        update = RelationshipUpdate(
            operation=RelationshipUpdate.Operation.OPERATION_DELETE,
            relationship=Relationship(
                resource=ObjectReference(
                    object_type=resource.type,
                    object_id=resource.id,
                ),
                relation=relation,
                subject=SubjectReference(
                    object=ObjectReference(
                        object_type=subject.type,
                        object_id=subject.id,
                    ),
                    optional_relation=subject.relation or "",
                ),
            ),
        )

        resp = self._client.permissions_service.WriteRelationships(
            WriteRelationshipsRequest(updates=[update])
        )
        token = resp.written_at.token if resp.written_at else ""
        logger.debug("Deleted relationship in SpiceDB, token: %s", token)
        return token
