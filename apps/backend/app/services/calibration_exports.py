"""Whitelisted CSV/JSON exports for calibration reports."""

import csv
import io

from app.schemas.calibration import CalibrationReportResponse


def calibration_summary_csv(report: CalibrationReportResponse) -> str:
    output = io.StringIO()
    fieldnames = [
        "company_id",
        "company_name",
        "final_status",
        "research_succeeded",
        "pages_fetched",
        "accepted_claims",
        "edited_claims",
        "rejected_claims",
        "pending_claims",
        "opportunity_score",
        "qualification_decision",
        "trusted_evidence_count",
        "contact_type",
        "contact_name",
        "contact_email",
        "contact_source_url",
        "draft_generated",
        "draft_fact_count",
        "draft_all_facts_traceable",
        "draft_awaiting_review",
        "email_not_sent",
        "worker_attempt_count",
        "worker_recovery_count",
        "processing_duration_ms",
        "research_accuracy",
        "opportunity_reasonableness",
        "contact_usability",
        "draft_personalization",
        "draft_professionalism",
        "ready_for_real_outreach",
        "reviewer_name",
        "reviewed_at",
        "review_notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for company in report.companies:
        evaluation = company.evaluation
        writer.writerow(
            {
                "company_id": str(company.company_id),
                "company_name": company.company_name,
                "final_status": company.final_status,
                "research_succeeded": company.research.request_succeeded,
                "pages_fetched": company.research.pages_fetched,
                "accepted_claims": company.research.accepted_count,
                "edited_claims": company.research.edited_count,
                "rejected_claims": company.research.rejected_count,
                "pending_claims": company.research.pending_count,
                "opportunity_score": company.opportunity.score,
                "qualification_decision": company.opportunity.qualification_decision,
                "trusted_evidence_count": company.opportunity.trusted_evidence_count,
                "contact_type": company.contact.contact_type,
                "contact_name": company.contact.name,
                "contact_email": company.contact.email,
                "contact_source_url": company.contact.source_url,
                "draft_generated": company.draft.generated,
                "draft_fact_count": company.draft.fact_count,
                "draft_all_facts_traceable": company.draft.all_facts_traceable,
                "draft_awaiting_review": company.draft.awaiting_human_review,
                "email_not_sent": company.draft.explicitly_not_sent,
                "worker_attempt_count": company.worker.attempt_count,
                "worker_recovery_count": company.worker.recovery_count,
                "processing_duration_ms": company.worker.total_duration_ms,
                "research_accuracy": evaluation.research_accuracy if evaluation else None,
                "opportunity_reasonableness": (
                    evaluation.opportunity_reasonableness if evaluation else None
                ),
                "contact_usability": evaluation.contact_usability if evaluation else None,
                "draft_personalization": (
                    evaluation.draft_personalization if evaluation else None
                ),
                "draft_professionalism": (
                    evaluation.draft_professionalism if evaluation else None
                ),
                "ready_for_real_outreach": (
                    evaluation.ready_for_real_outreach if evaluation else None
                ),
                "reviewer_name": evaluation.reviewer_name if evaluation else None,
                "reviewed_at": evaluation.reviewed_at.isoformat() if evaluation else None,
                "review_notes": evaluation.notes if evaluation else None,
            }
        )
    return output.getvalue()


def calibration_report_json(report: CalibrationReportResponse) -> str:
    return report.model_dump_json(indent=2)
