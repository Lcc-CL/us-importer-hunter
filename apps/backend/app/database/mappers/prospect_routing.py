"""Prospect-routing domain ↔ persistence mapping."""

from app.database.models.prospect_routing import ProspectRouteModel, ProspectRoutingRunModel
from app.domain.prospect_routing import (
    ProspectRoute,
    ProspectRouteReviewStatus,
    ProspectRoutingRun,
    ProspectRoutingRunStatus,
    ProspectTier,
)


class ProspectRoutingMapper:
    @staticmethod
    def run_to_model(run: ProspectRoutingRun) -> ProspectRoutingRunModel:
        return ProspectRoutingRunModel(
            id=run.id,
            import_session_id=run.import_session_id,
            rules_version=run.rules_version,
            configuration_hash=run.configuration_hash,
            entity_state_hash=run.entity_state_hash,
            execution_generation=run.execution_generation,
            criteria_json=run.criteria_json,
            weights_snapshot_json=run.weights_snapshot_json,
            status=run.status.value,
            total_companies=run.total_companies,
            routed_companies=run.routed_companies,
            blocked_companies=run.blocked_companies,
            tier_a_count=run.tier_a_count,
            tier_b_count=run.tier_b_count,
            tier_c_count=run.tier_c_count,
            tier_d_count=run.tier_d_count,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_summary=run.error_summary,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    @staticmethod
    def run_to_domain(model: ProspectRoutingRunModel) -> ProspectRoutingRun:
        return ProspectRoutingRun(
            id=model.id,
            import_session_id=model.import_session_id,
            rules_version=model.rules_version,
            configuration_hash=model.configuration_hash,
            entity_state_hash=model.entity_state_hash,
            execution_generation=model.execution_generation,
            criteria_json=model.criteria_json,
            weights_snapshot_json=model.weights_snapshot_json,
            status=ProspectRoutingRunStatus(model.status),
            total_companies=model.total_companies,
            routed_companies=model.routed_companies,
            blocked_companies=model.blocked_companies,
            tier_a_count=model.tier_a_count,
            tier_b_count=model.tier_b_count,
            tier_c_count=model.tier_c_count,
            tier_d_count=model.tier_d_count,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_summary=model.error_summary,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def route_to_model(route: ProspectRoute) -> ProspectRouteModel:
        return ProspectRouteModel(
            id=route.id,
            routing_run_id=route.routing_run_id,
            execution_generation=route.execution_generation,
            company_id=route.company_id,
            company_name=route.company_name,
            pre_score=route.pre_score,
            recommended_tier=(route.recommended_tier.value if route.recommended_tier else None),
            effective_tier=(route.effective_tier.value if route.effective_tier else None),
            feature_snapshot_json=route.feature_snapshot_json,
            reason_codes=list(route.reason_codes),
            warning_codes=list(route.warning_codes),
            review_status=route.review_status.value,
            override_reason=route.override_reason,
            reviewed_by=route.reviewed_by,
            reviewed_at=route.reviewed_at,
            contact_count=route.contact_count,
            has_usable_contact=route.has_usable_contact,
            has_usable_email=route.has_usable_email,
            preferred_role_category=route.preferred_role_category,
            created_at=route.created_at,
            updated_at=route.updated_at,
        )

    @staticmethod
    def route_to_domain(model: ProspectRouteModel) -> ProspectRoute:
        return ProspectRoute(
            id=model.id,
            routing_run_id=model.routing_run_id,
            execution_generation=model.execution_generation,
            company_id=model.company_id,
            company_name=model.company_name,
            pre_score=model.pre_score,
            recommended_tier=(
                ProspectTier(model.recommended_tier) if model.recommended_tier else None
            ),
            effective_tier=(ProspectTier(model.effective_tier) if model.effective_tier else None),
            feature_snapshot_json=model.feature_snapshot_json,
            reason_codes=tuple(model.reason_codes),
            warning_codes=tuple(model.warning_codes),
            review_status=ProspectRouteReviewStatus(model.review_status),
            override_reason=model.override_reason,
            reviewed_by=model.reviewed_by,
            reviewed_at=model.reviewed_at,
            contact_count=model.contact_count,
            has_usable_contact=model.has_usable_contact,
            has_usable_email=model.has_usable_email,
            preferred_role_category=model.preferred_role_category,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
