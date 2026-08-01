"""D4a report exports contain only the documented audit fields."""

import csv
import io
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.calibration import CalibrationReportResponse
from app.services.calibration_exports import (
    calibration_report_json,
    calibration_summary_csv,
)

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def report_response() -> CalibrationReportResponse:
    company_id = uuid4()
    return CalibrationReportResponse.model_validate(
        {
            "calibration_id": uuid4(),
            "discovery_task_id": uuid4(),
            "prospect_batch_id": uuid4(),
            "status": "completed",
            "sample_source": "manual_csv",
            "sample_reality_status": "user_supplied_unverified",
            "created_at": NOW,
            "updated_at": NOW,
            "generated_at": NOW,
            "providers": {
                "website_fetch_mode": "fixture",
                "research_provider_mode": "deterministic_fake",
                "draft_provider_mode": "deterministic_fake",
                "contact_source_mode": "official_website",
                "paid_request_count": 0,
                "research_provider_call_count": 0,
                "draft_provider_call_count": 0,
                "provider_duration_ms": 150,
                "token_usage_total": 0,
            },
            "summary": {
                "sample_count": 3,
                "website_research_success_count": 1,
                "website_research_success_rate": 0.3333,
                "evidence_review_company_count": 1,
                "evidence_accepted_count": 1,
                "evidence_rejected_count": 0,
                "opportunity_generated_count": 1,
                "opportunity_generation_rate": 0.3333,
                "qualified_count": 1,
                "personal_contact_count": 1,
                "personal_contact_coverage_rate": 0.3333,
                "department_contact_count": 0,
                "department_contact_coverage_rate": 0.0,
                "draft_generated_count": 1,
                "draft_generation_rate": 0.3333,
                "ready_for_real_outreach_count": 1,
                "evaluated_company_count": 1,
                "worker_recovery_count": 0,
                "average_processing_duration_ms": 500,
                "average_research_accuracy": 4.0,
                "average_opportunity_reasonableness": 4.0,
                "average_contact_usability": 4.0,
                "average_draft_personalization": 4.0,
                "average_draft_professionalism": 4.0,
            },
            "truth_checks": {
                "fabricated_contact_count": 0,
                "unreviewed_fact_in_draft_count": 0,
                "rejected_claim_in_score_or_draft_count": 0,
                "pending_claim_bypassed_count": 0,
                "draft_marked_sent_count": 0,
                "duplicate_entity_count": 0,
                "invalid_email_contact_count": 0,
                "website_failure_mislabeled_company_missing_count": 0,
                "opportunity_score_is_probability": False,
            },
            "companies": [
                {
                    "company_id": company_id,
                    "company_name": "Atlas Hardware",
                    "final_status": "completed",
                    "error_code": None,
                    "error_summary": None,
                    "research": {
                        "request_succeeded": True,
                        "pages_fetched": 2,
                        "duration_ms": 100,
                        "new_claim_count": 1,
                        "accepted_count": 1,
                        "edited_count": 0,
                        "rejected_count": 0,
                        "pending_count": 0,
                        "claims_without_source_count": 0,
                        "failure_reason": None,
                    },
                    "opportunity": {
                        "generated": True,
                        "score": 72.0,
                        "qualification_decision": "qualified",
                        "major_positive_reasons": ["trusted evidence"],
                        "major_deduction_reasons": [],
                        "limiting_reasons": [],
                        "trusted_evidence_count": 1,
                        "stopped_for_insufficient_evidence": False,
                    },
                    "contact": {
                        "personal_contact_found": True,
                        "department_contact_found": False,
                        "contact_type": "personal",
                        "name": "Maria Chen",
                        "title_or_department": "Supply Chain Director",
                        "email": "maria@example.com",
                        "phone": None,
                        "source_url": "https://example.com/contact",
                        "manually_confirmed": False,
                        "contact_not_found_reason": None,
                    },
                    "draft": {
                        "generated": True,
                        "not_generated_reason": None,
                        "contact_type": "personal",
                        "fact_count": 1,
                        "facts": [
                            {
                                "claim": "customs activity confirmed",
                                "source_urls": ["https://evidence.example/atlas"],
                                "traceable_to_company_evidence": True,
                            }
                        ],
                        "all_facts_traceable": True,
                        "contains_unreviewed_claim": False,
                        "contains_rejected_claim": False,
                        "awaiting_human_review": True,
                        "explicitly_not_sent": True,
                    },
                    "worker": {
                        "queue_wait_ms": 10,
                        "total_duration_ms": 500,
                        "stage_durations_ms": {"researching": 100},
                        "attempt_count": 1,
                        "recovery_count": 0,
                        "lease_expired": False,
                        "duplicate_entity_count": 0,
                    },
                    "evaluation": {
                        "research_accuracy": 4,
                        "opportunity_reasonableness": 4,
                        "contact_usability": 4,
                        "draft_personalization": 4,
                        "draft_professionalism": 4,
                        "ready_for_real_outreach": True,
                        "reviewer_name": "Internal Reviewer",
                        "notes": "Ready for a human outreach decision.",
                        "reviewed_at": NOW,
                    },
                }
            ],
        }
    )


def test_csv_export_is_parseable_and_contains_review_and_traceability_summary() -> None:
    rendered = calibration_summary_csv(report_response())
    rows = list(csv.DictReader(io.StringIO(rendered)))

    assert len(rows) == 1
    assert rows[0]["company_name"] == "Atlas Hardware"
    assert rows[0]["draft_all_facts_traceable"] == "True"
    assert rows[0]["email_not_sent"] == "True"
    assert rows[0]["reviewer_name"] == "Internal Reviewer"


def test_json_export_has_no_configuration_prompt_or_raw_page_fields() -> None:
    rendered = calibration_report_json(report_response())
    payload = json.loads(rendered)
    lowered = rendered.lower()

    assert payload["providers"]["paid_request_count"] == 0
    assert payload["companies"][0]["draft"]["facts"][0]["source_urls"]
    for forbidden in (
        "api_key",
        "environment_variable",
        "provider_prompt",
        "raw_html",
        "raw_page_content",
    ):
        assert forbidden not in lowered
