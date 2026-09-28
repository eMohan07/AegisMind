from __future__ import annotations

import os
import tempfile
import time

import pytest

from aegismind_core.approvals.models import Proposal, ProposalStatus, RiskLevel
from aegismind_core.approvals.policy import evaluate, compute_risk
from aegismind_core.approvals.store import ApprovalStore


class TestPolicy:
    """Tests for the evaluate policy function."""

    def test_auto_tools(self) -> None:
        assert evaluate("search_local_knowledge", {"query": "test"}) == "auto"
        assert evaluate("read_system_file", {"path": "/tmp/test"}) == "auto"

    def test_approval_tools(self) -> None:
        assert evaluate("create_note", {"title": "test", "content": "x", "tags": []}) == "approval"
        assert evaluate("run_local_command", {"cmd": "git status"}) == "approval"
        assert evaluate("save_memory", {"fact": "x", "tags": ["a"]}) == "approval"

    def test_deny_unknown_tool(self) -> None:
        assert evaluate("unknown_tool", {}) == "deny"

    def test_deny_unallowlisted_command(self) -> None:
        result = evaluate("run_local_command", {"cmd": "rm -rf /"})
        assert result == "deny"

    def test_allowlisted_command_is_approval(self) -> None:
        result = evaluate("run_local_command", {"cmd": "git status"})
        assert result == "approval"

    def test_deny_unallowlisted_command_with_metachar(self) -> None:
        result = evaluate("run_local_command", {"cmd": "echo test; cat /etc/passwd"})
        assert result == "deny"


class TestComputeRisk:
    """Tests for the compute_risk function."""

    def test_new_note_is_low(self) -> None:
        assert compute_risk("create_note", is_new=True) == "low"

    def test_overwrite_note_is_medium(self) -> None:
        assert compute_risk("create_note", is_new=False) == "medium"

    def test_run_local_command_is_medium(self) -> None:
        assert compute_risk("run_local_command") == "medium"

    def test_save_memory_is_low(self) -> None:
        assert compute_risk("save_memory") == "low"

    def test_tainted_elevates_low_to_medium(self) -> None:
        assert compute_risk("save_memory", tainted=True) == "medium"

    def test_tainted_elevates_medium_to_high(self) -> None:
        assert compute_risk("create_note", is_new=False, tainted=True) == "high"


class TestApprovalStore:
    """Tests for the ApprovalStore SQLite backend."""

    @pytest.fixture(autouse=True)
    def _setup_store(self, tmp_path: tempfile.TemporaryDirectory) -> None:
        self.db_path = os.path.join(tmp_path, "approvals.db")
        self.store = ApprovalStore(db_path=self.db_path)

    def test_create_and_get(self) -> None:
        proposal = Proposal(
            tool_name="create_note",
            args={"title": "test"},
            risk=RiskLevel.LOW,
            reasoning="test",
            preview="test preview",
            source_refs=[],
            tainted=False,
            taint_sources=[],
        )
        self.store.create(proposal)
        fetched = self.store.get(proposal.id)
        assert fetched is not None
        assert fetched.tool_name == "create_note"
        assert fetched.status == ProposalStatus.PENDING

    def test_list_by_status(self) -> None:
        proposal = Proposal(
            tool_name="save_memory",
            args={"fact": "x"},
            risk=RiskLevel.LOW,
            reasoning="test",
            preview="",
            source_refs=[],
            tainted=False,
            taint_sources=[],
        )
        self.store.create(proposal)
        pending = self.store.list_by_status("pending")
        assert len(pending) == 1
        all_proposals = self.store.list_by_status()
        assert len(all_proposals) >= 1

    def test_update(self) -> None:
        proposal = Proposal(
            tool_name="create_note",
            args={"title": "test"},
            risk=RiskLevel.LOW,
            reasoning="test",
            preview="",
            source_refs=[],
            tainted=False,
            taint_sources=[],
        )
        self.store.create(proposal)
        proposal.status = ProposalStatus.APPROVED
        proposal.decision_reason = "approved by user"
        self.store.update(proposal)
        fetched = self.store.get(proposal.id)
        assert fetched is not None
        assert fetched.status == ProposalStatus.APPROVED
        assert fetched.decision_reason == "approved by user"

    def test_expire_old(self) -> None:
        proposal = Proposal(
            tool_name="create_note",
            args={"title": "test"},
            risk=RiskLevel.LOW,
            reasoning="test",
            preview="",
            source_refs=[],
            tainted=False,
            taint_sources=[],
        )
        self.store.create(proposal)
        expired = self.store.expire_old()
        assert expired == 0
        proposal.expires_at = "2020-01-01T00:00:00+00:00"
        self.store.update(proposal)
        expired = self.store.expire_old()
        assert expired == 1
        fetched = self.store.get(proposal.id)
        assert fetched is not None
        assert fetched.status == ProposalStatus.EXPIRED

    def test_get_missing(self) -> None:
        assert self.store.get("nonexistent_id") is None


class TestProposalModel:
    """Tests for the Proposal Pydantic model."""

    def test_default_values(self) -> None:
        proposal = Proposal(
            tool_name="test",
            args={},
        )
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.risk == RiskLevel.LOW
        assert proposal.tainted is False
        assert proposal.expires_at is not None

    def test_expiry(self) -> None:
        proposal = Proposal(
            tool_name="test",
            args={},
        )
        assert not proposal.is_expired()

    def test_elevate_risk(self) -> None:
        proposal = Proposal(
            tool_name="test",
            args={},
            risk=RiskLevel.LOW,
        )
        proposal.elevate_risk()
        assert proposal.risk == RiskLevel.MEDIUM
        proposal.elevate_risk()
        assert proposal.risk == RiskLevel.HIGH


class TestApprovalFlow:
    """Integration tests for the full approval flow."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: tempfile.TemporaryDirectory) -> None:
        self.db_path = os.path.join(tmp_path, "approvals.db")
        self.store = ApprovalStore(db_path=self.db_path)
        self.approval_store = self.store

    def test_approval_tool_never_touches_filesystem_before_approval(self) -> None:
        from aegismind_core.agent.ports import NoteCreatorPort
        from aegismind_core.approvals import Proposal, RiskLevel, evaluate

        class FakeNoteCreator(NoteCreatorPort):
            def __init__(self) -> None:
                self.created = False

            async def create_note(self, title: str, content: str, tags: list[str], source_query: str | None = None) -> str:
                self.created = True
                return "NOTE_CREATED"

        fake_creator = FakeNoteCreator()
        args = {"title": "secret", "content": "hidden", "tags": ["private"]}
        policy_result = evaluate("create_note", args)
        assert policy_result == "approval"
        assert not fake_creator.created

        proposal = Proposal(
            tool_name="create_note",
            args=args,
            risk=RiskLevel.LOW,
            reasoning="test",
            preview="test",
            source_refs=[],
            tainted=False,
            taint_sources=[],
        )
        self.store.create(proposal)
        assert not fake_creator.created

    def test_deny_cannot_be_bypassed_by_edited_args(self) -> None:
        from aegismind_core.approvals import Proposal, RiskLevel, evaluate

        args = {"cmd": "rm -rf /"}
        policy_result = evaluate("run_local_command", args)
        assert policy_result == "deny"

        proposal = Proposal(
            tool_name="run_local_command",
            args=args,
            risk=RiskLevel.MEDIUM,
            reasoning="test",
            preview="['rm', '-rf', '/']",
            source_refs=[],
            tainted=False,
            taint_sources=[],
        )
        self.store.create(proposal)
        proposal.edited_args = {"cmd": "rm -rf /"}
        final_policy = evaluate(proposal.tool_name, proposal.edited_args)
        assert final_policy == "deny"

    def test_expiry_works(self) -> None:
        from aegismind_core.approvals import Proposal, RiskLevel

        proposal = Proposal(
            tool_name="create_note",
            args={},
            risk=RiskLevel.LOW,
            reasoning="test",
            preview="",
            source_refs=[],
            tainted=False,
            taint_sources=[],
        )
        self.store.create(proposal)
        assert not proposal.is_expired()
        time.sleep(0.01)

        proposal.expires_at = "2020-01-01T00:00:00+00:00"
        self.store.update(proposal)
        assert proposal.is_expired()
        expired_count = self.store.expire_old()
        assert expired_count >= 1
        fetched = self.store.get(proposal.id)
        assert fetched is not None
        assert fetched.status == ProposalStatus.EXPIRED
