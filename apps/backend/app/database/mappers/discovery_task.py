"""DiscoveryTask aggregate ↔ persistence mapping."""

import json
from typing import cast

from app.database.models.discovery_task import DiscoveryCandidateModel, DiscoveryTaskModel
from app.domain.discovery import (
    DiscoveryCandidate,
    DiscoveryCandidateStatus,
    DiscoveryTask,
    DiscoveryTaskStatus,
)


class DiscoveryTaskMapper:
    @staticmethod
    def to_model(task: DiscoveryTask) -> DiscoveryTaskModel:
        return DiscoveryTaskModel(
            id=task.id,
            original_prompt=task.original_prompt,
            requested_count=task.requested_count,
            effective_count=task.effective_count,
            parsed_region=task.parsed_region,
            parsed_category=task.parsed_category,
            parsed_keywords=json.dumps(task.parsed_keywords, ensure_ascii=False),
            provider=task.provider,
            status=task.status.value,
            provider_failure_count=task.provider_failure_count,
            error_summary=task.error_summary,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            candidates=[
                DiscoveryCandidateModel(
                    id=item.id,
                    task_id=task.id,
                    source=item.source,
                    source_url=item.source_url,
                    external_id=item.external_id,
                    company_name=item.company_name,
                    normalized_name=item.normalized_name,
                    website=item.website,
                    normalized_domain=item.normalized_domain,
                    address=item.address,
                    region=item.region,
                    product_description=item.product_description,
                    import_evidence=item.import_evidence,
                    raw_metadata_json=item.raw_metadata_json,
                    status=item.status.value,
                    company_id=item.company_id,
                    duplicate_of_id=item.duplicate_of_id,
                    failure_reason=item.failure_reason,
                    created_at=item.created_at,
                )
                for item in task.candidates
            ],
        )

    @staticmethod
    def to_domain(model: DiscoveryTaskModel) -> DiscoveryTask:
        decoded_keywords = json.loads(model.parsed_keywords)
        if not isinstance(decoded_keywords, list) or not all(
            isinstance(item, str) for item in decoded_keywords
        ):
            raise ValueError("persisted discovery keywords must be a JSON string list")
        task = DiscoveryTask(
            id=model.id,
            original_prompt=model.original_prompt,
            requested_count=model.requested_count,
            effective_count=model.effective_count,
            parsed_region=model.parsed_region,
            parsed_category=model.parsed_category,
            parsed_keywords=tuple(cast(list[str], decoded_keywords)),
            provider=model.provider,
            created_at=model.created_at,
        )
        task._status = DiscoveryTaskStatus(model.status)
        task._provider_failure_count = model.provider_failure_count
        task._error_summary = model.error_summary
        task._started_at = model.started_at
        task._completed_at = model.completed_at
        task._candidates = [
            DiscoveryCandidate(
                id=item.id,
                source=item.source,
                source_url=item.source_url,
                external_id=item.external_id,
                company_name=item.company_name,
                normalized_name=item.normalized_name,
                website=item.website,
                normalized_domain=item.normalized_domain,
                address=item.address,
                region=item.region,
                product_description=item.product_description,
                import_evidence=item.import_evidence,
                raw_metadata_json=item.raw_metadata_json,
                status=DiscoveryCandidateStatus(item.status),
                company_id=item.company_id,
                duplicate_of_id=item.duplicate_of_id,
                failure_reason=item.failure_reason,
                created_at=item.created_at,
            )
            for item in model.candidates
        ]
        return task
