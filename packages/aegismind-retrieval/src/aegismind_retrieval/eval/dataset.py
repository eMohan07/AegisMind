from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvalTriple(BaseModel):
    """Evaluation test case triple for retrieval and generation benchmarking."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique test case identifier")
    connector: str = Field(..., description="Source connector type (e.g. google_drive, slack)")
    query: str = Field(..., description="User query text")
    expected_answer: str = Field(..., description="Ground truth answer summary")
    expected_source_doc_ids: list[str] = Field(..., description="Expected document identifiers")
    metadata: dict[str, str] = Field(default_factory=dict)


# Golden dataset across major connectors with 10 to 12 triples each
GOLDEN_EVAL_DATASET: list[EvalTriple] = [
    # Google Drive triples
    EvalTriple(
        id="gdrive_01",
        connector="google_drive",
        query="What is the remote work policy?",
        expected_answer=(
            "Employees can work up to 2 days remotely per week with manager approval."
        ),
        expected_source_doc_ids=["doc_gdrive_remote_work"],
    ),
    EvalTriple(
        id="gdrive_02",
        connector="google_drive",
        query="Where is the quarterly financial revenue report?",
        expected_answer=(
            "Q3 consolidated financial revenue reached 14.2M with 18 percent YoY growth."
        ),
        expected_source_doc_ids=["doc_gdrive_financials_q3"],
    ),
    EvalTriple(
        id="gdrive_03",
        connector="google_drive",
        query="What is the standard employee equipment budget?",
        expected_answer=(
            "Full-time employees receive a 1500 dollar hardware refresh budget every 2 years."
        ),
        expected_source_doc_ids=["doc_gdrive_equipment_guidelines"],
    ),
    EvalTriple(
        id="gdrive_04",
        connector="google_drive",
        query="What are the data classification tiers?",
        expected_answer="Data tiers are Public, Internal, Confidential, and Restricted.",
        expected_source_doc_ids=["doc_gdrive_data_classification"],
    ),
    EvalTriple(
        id="gdrive_05",
        connector="google_drive",
        query="How do I file travel expense reimbursements?",
        expected_answer=(
            "Submit itemized receipts via Concur within 30 days of travel completion."
        ),
        expected_source_doc_ids=["doc_gdrive_expense_policy"],
    ),
    EvalTriple(
        id="gdrive_06",
        connector="google_drive",
        query="What is the customer support SLA for priority 1 issues?",
        expected_answer=("P1 critical incidents require initial response within 15 minutes."),
        expected_source_doc_ids=["doc_gdrive_support_sla"],
    ),
    EvalTriple(
        id="gdrive_07",
        connector="google_drive",
        query="What is the vendor onboarding compliance checklist?",
        expected_answer=(
            "Vendors must complete SOC2 Type 2 review, DPA signing, and security questionnaire."
        ),
        expected_source_doc_ids=["doc_gdrive_vendor_checklist"],
    ),
    EvalTriple(
        id="gdrive_08",
        connector="google_drive",
        query="What is the parental leave entitlement?",
        expected_answer=("Primary caregivers are entitled to 16 weeks of fully paid leave."),
        expected_source_doc_ids=["doc_gdrive_benefits_leave"],
    ),
    EvalTriple(
        id="gdrive_09",
        connector="google_drive",
        query="How are company OKRs tracked?",
        expected_answer=(
            "OKRs are reviewed bi-weekly in departmental syncs and scored at quarter end."
        ),
        expected_source_doc_ids=["doc_gdrive_okr_framework"],
    ),
    EvalTriple(
        id="gdrive_10",
        connector="google_drive",
        query="What are the brand design system guidelines?",
        expected_answer=(
            "Official brand palette consists of Aegis Navy, Slate Gray, and Mint Accent."
        ),
        expected_source_doc_ids=["doc_gdrive_design_system"],
    ),
    # Slack triples
    EvalTriple(
        id="slack_01",
        connector="slack",
        query="What was decided about the database migration schedule in dev-ops?",
        expected_answer=(
            "Database migration is scheduled for Sunday 02:00 UTC with read-only window."
        ),
        expected_source_doc_ids=["slack_channel_devops_db_migration"],
    ),
    EvalTriple(
        id="slack_02",
        connector="slack",
        query="Who is on-call for frontend incidents this week?",
        expected_answer=(
            "Marcus Vance is primary on-call with Sarah Chen as secondary escalation."
        ),
        expected_source_doc_ids=["slack_channel_oncall_schedule"],
    ),
    EvalTriple(
        id="slack_03",
        connector="slack",
        query="What caused the staging cluster deployment outage?",
        expected_answer=(
            "Staging failed due to an expired TLS certificate on the ingress gateway."
        ),
        expected_source_doc_ids=["slack_channel_incidents_staging"],
    ),
    EvalTriple(
        id="slack_04",
        connector="slack",
        query="What is the release candidate version for mobile app?",
        expected_answer=("Release candidate v2.4.0-rc3 is currently in external beta testing."),
        expected_source_doc_ids=["slack_channel_mobile_releases"],
    ),
    EvalTriple(
        id="slack_05",
        connector="slack",
        query="Where are the office lunch catering updates posted?",
        expected_answer=(
            "Catering menus and dietary surveys are posted in announcements every Monday."
        ),
        expected_source_doc_ids=["slack_channel_office_lunch"],
    ),
    EvalTriple(
        id="slack_06",
        connector="slack",
        query="What was the outcome of the security incident postmortem?",
        expected_answer=(
            "Root cause identified as misconfigured S3 bucket; public access blocked."
        ),
        expected_source_doc_ids=["slack_channel_sec_postmortem"],
    ),
    EvalTriple(
        id="slack_07",
        connector="slack",
        query="Who approved the new AWS billing budget threshold?",
        expected_answer="VP of Engineering approved 25000 monthly cloud ceiling.",
        expected_source_doc_ids=["slack_channel_cloud_costs"],
    ),
    EvalTriple(
        id="slack_08",
        connector="slack",
        query="What is the link to the team hackathon registration?",
        expected_answer=(
            "Hackathon registration is open via internal portal link in general channel."
        ),
        expected_source_doc_ids=["slack_channel_hackathon_2026"],
    ),
    EvalTriple(
        id="slack_09",
        connector="slack",
        query="What time is the all-hands Q&A session?",
        expected_answer=("All-hands starts at 16:00 UTC with 20 minutes allocated to open Q&A."),
        expected_source_doc_ids=["slack_channel_all_hands"],
    ),
    EvalTriple(
        id="slack_10",
        connector="slack",
        query="How do we request guest Wi-Fi access?",
        expected_answer=(
            "Submit visitor details in it-helpdesk bot to receive 24-hour guest credentials."
        ),
        expected_source_doc_ids=["slack_channel_it_helpdesk"],
    ),
    # Confluence triples
    EvalTriple(
        id="conf_01",
        connector="confluence",
        query="What is the architectural design for the search ingestion pipeline?",
        expected_answer=(
            "Ingestion pipeline uses Docling parser, contextual chunking, and pgmq queue."
        ),
        expected_source_doc_ids=["conf_arch_ingestion_pipeline"],
    ),
    EvalTriple(
        id="conf_02",
        connector="confluence",
        query="What are the cryptographic key rotation procedures?",
        expected_answer=(
            "DEKs rotate per tenant annually; Master Keys rotate via HSM every 2 years."
        ),
        expected_source_doc_ids=["conf_sec_key_rotation"],
    ),
    EvalTriple(
        id="conf_03",
        connector="confluence",
        query="What is the microservice communication protocol standard?",
        expected_answer=(
            "All internal services communicate via gRPC with mTLS and Protocol Buffers."
        ),
        expected_source_doc_ids=["conf_arch_microservice_comm"],
    ),
    EvalTriple(
        id="conf_04",
        connector="confluence",
        query="What is the disaster recovery RTO and RPO?",
        expected_answer=(
            "Recovery Time Objective is 4 hours and Recovery Point Objective is 15 minutes."
        ),
        expected_source_doc_ids=["conf_ops_disaster_recovery"],
    ),
    EvalTriple(
        id="conf_05",
        connector="confluence",
        query="What are the coding style standards for Python services?",
        expected_answer=(
            "Strict Python 3.12 typing, Pydantic v2 schemas, ruff linting, and no em dashes."
        ),
        expected_source_doc_ids=["conf_eng_python_standards"],
    ),
    EvalTriple(
        id="conf_06",
        connector="confluence",
        query="How is data retention handled under GDPR Article 17?",
        expected_answer=(
            "User deletion requests trigger automated cascading tombstone purging in 30 days."
        ),
        expected_source_doc_ids=["conf_compliance_gdpr_rtbf"],
    ),
    EvalTriple(
        id="conf_07",
        connector="confluence",
        query="What is the database connection pooling configuration?",
        expected_answer=(
            "PgBouncer manages connection pools with maximum 50 server connections per node."
        ),
        expected_source_doc_ids=["conf_infra_pgbouncer_setup"],
    ),
    EvalTriple(
        id="conf_08",
        connector="confluence",
        query="What are the API rate limiting thresholds?",
        expected_answer=(
            "Anonymous users are capped at 60 req/min; authenticated users get 600 req/min."
        ),
        expected_source_doc_ids=["conf_api_rate_limiting"],
    ),
    EvalTriple(
        id="conf_09",
        connector="confluence",
        query="What is the container deployment strategy?",
        expected_answer=(
            "Kubernetes rolling updates with minimum 2 replicas active during rollout."
        ),
        expected_source_doc_ids=["conf_deploy_k8s_strategy"],
    ),
    EvalTriple(
        id="conf_10",
        connector="confluence",
        query="How are security audit logs archived?",
        expected_answer=(
            "Audit logs are replicated to append-only WORM S3 buckets with 7-year retention."
        ),
        expected_source_doc_ids=["conf_sec_audit_archive"],
    ),
    # Jira triples
    EvalTriple(
        id="jira_01",
        connector="jira",
        query="What is the status of ticket SEC-892?",
        expected_answer=("SEC-892 zero stale read window verification is closed and verified."),
        expected_source_doc_ids=["jira_issue_sec_892"],
    ),
    EvalTriple(
        id="jira_02",
        connector="jira",
        query="What is the blocker on ticket ENG-1044?",
        expected_answer=(
            "ENG-1044 is blocked waiting on external partner OAuth client ID generation."
        ),
        expected_source_doc_ids=["jira_issue_eng_1044"],
    ),
    EvalTriple(
        id="jira_03",
        connector="jira",
        query="What is the acceptance criteria for PROD-505?",
        expected_answer=(
            "Top-k retrieval latency must stay below 200 milliseconds under 50 RPS load."
        ),
        expected_source_doc_ids=["jira_issue_prod_505"],
    ),
    EvalTriple(
        id="jira_04",
        connector="jira",
        query="Who is assigned to bug INFRA-312?",
        expected_answer=("DevOps engineer Alex Miller is assigned to investigate memory leaks."),
        expected_source_doc_ids=["jira_issue_infra_312"],
    ),
    EvalTriple(
        id="jira_05",
        connector="jira",
        query="What sprint is feature DATA-789 scheduled in?",
        expected_answer="DATA-789 is committed for Sprint 44 starting next Tuesday.",
        expected_source_doc_ids=["jira_issue_data_789"],
    ),
    EvalTriple(
        id="jira_06",
        connector="jira",
        query="What is the priority level of ticket OPS-204?",
        expected_answer=(
            "OPS-204 is marked as High priority due to disk usage nearing 85 percent."
        ),
        expected_source_doc_ids=["jira_issue_ops_204"],
    ),
    EvalTriple(
        id="jira_07",
        connector="jira",
        query="When was ticket BUG-991 reported?",
        expected_answer=("BUG-991 was created on September 18 after staging regression run."),
        expected_source_doc_ids=["jira_issue_bug_991"],
    ),
    EvalTriple(
        id="jira_08",
        connector="jira",
        query="What components are affected by ticket CORE-612?",
        expected_answer=("CORE-612 affects aegismind-authz and aegismind-retrieval packages."),
        expected_source_doc_ids=["jira_issue_core_612"],
    ),
    EvalTriple(
        id="jira_09",
        connector="jira",
        query="What is the release fix version for ticket UI-401?",
        expected_answer="UI-401 fix is targeting Lens Web UI release version 0.2.0.",
        expected_source_doc_ids=["jira_issue_ui_401"],
    ),
    EvalTriple(
        id="jira_10",
        connector="jira",
        query="What was the resolution of ticket FEAT-112?",
        expected_answer=(
            "FEAT-112 was closed as Done following peer review and conformance tests."
        ),
        expected_source_doc_ids=["jira_issue_feat_112"],
    ),
    # GitHub triples
    EvalTriple(
        id="github_01",
        connector="github",
        query="What does pull request 88 change?",
        expected_answer=(
            "PR 88 adds reciprocal rank fusion support to merge dense and lexical rankings."
        ),
        expected_source_doc_ids=["github_pr_88_rrf_merge"],
    ),
    EvalTriple(
        id="github_02",
        connector="github",
        query="What was fixed in commit 4f9a12c?",
        expected_answer=(
            "Commit 4f9a12c fixed token consistency parameter passing in bulk authz check."
        ),
        expected_source_doc_ids=["github_commit_4f9a12c"],
    ),
    EvalTriple(
        id="github_03",
        connector="github",
        query="What dependencies were updated in dependabot PR 102?",
        expected_answer=("Dependabot updated pydantic from 2.9 to 2.10 and authzed gRPC client."),
        expected_source_doc_ids=["github_pr_102_dependencies"],
    ),
    EvalTriple(
        id="github_04",
        connector="github",
        query="Where is the CI workflow for running permission guardrail tests?",
        expected_answer=("Workflow is defined in github/workflows/permission-guardrails.yml."),
        expected_source_doc_ids=["github_workflow_guardrails"],
    ),
    EvalTriple(
        id="github_05",
        connector="github",
        query="What is the main branch protection rule in the repository?",
        expected_answer=(
            "Requires 1 approving review, passing CI status checks, and linear commit history."
        ),
        expected_source_doc_ids=["github_branch_protection"],
    ),
    EvalTriple(
        id="github_06",
        connector="github",
        query="What was reported in issue 75 regarding docker-compose?",
        expected_answer=("Issue 75 reported unhealthy postgres service on Windows host mounts."),
        expected_source_doc_ids=["github_issue_75_compose"],
    ),
    EvalTriple(
        id="github_07",
        connector="github",
        query="Who authored pull request 94 for MCP bridge?",
        expected_answer="PR 94 was authored by lead security engineer Elena Rostova.",
        expected_source_doc_ids=["github_pr_94_mcp_bridge"],
    ),
    EvalTriple(
        id="github_08",
        connector="github",
        query="What pre-commit hooks are configured in the repository?",
        expected_answer=(
            "Pre-commit runs ruff check, ruff format, trailing whitespace, and check-yaml."
        ),
        expected_source_doc_ids=["github_pre_commit_config"],
    ),
    EvalTriple(
        id="github_09",
        connector="github",
        query="What is the Dockerfile multi-stage build structure for Agora?",
        expected_answer=(
            "Uses python:3.12-slim base, installs uv, copies wheels, and runs as non-root user."
        ),
        expected_source_doc_ids=["github_dockerfile_agora"],
    ),
    EvalTriple(
        id="github_10",
        connector="github",
        query="What code coverage threshold is enforced on PR builds?",
        expected_answer=("CI enforces minimum 85 percent line coverage across all packages."),
        expected_source_doc_ids=["github_codecov_threshold"],
    ),
]
