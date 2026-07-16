"""Company aggregate ↔ persistence mapping."""

from app.database.models.company import (
    CompanyAliasModel,
    CompanyModel,
    CompanySignalModel,
    CompanySourceModel,
)
from app.domain.company import Company
from app.domain.values import CompanyName, SourceReference, WebsiteUrl


class CompanyMapper:
    @staticmethod
    def to_model(company: Company) -> CompanyModel:
        return CompanyModel(
            id=company.id,
            name=company.name.value,
            normalized_name=company.name.normalized,
            website=company.website.value if company.website else None,
            website_host=company.website.host if company.website else None,
            verified=company.verified,
            created_at=company.created_at,
            aliases=[
                CompanyAliasModel(
                    company_id=company.id, name=alias.value, normalized_name=alias.normalized
                )
                for alias in company.aliases
            ],
            sources=[
                CompanySourceModel(
                    company_id=company.id,
                    position=position,
                    source=ref.source,
                    reference=ref.reference,
                    retrieved_at=ref.retrieved_at,
                )
                for position, ref in enumerate(company.sources)
            ],
            signals=[
                CompanySignalModel(company_id=company.id, position=position, signal=signal)
                for position, signal in enumerate(company.signals)
            ],
        )

    @staticmethod
    def to_domain(model: CompanyModel) -> Company:
        company = Company(
            id=model.id,
            name=CompanyName(model.name),
            website=WebsiteUrl(model.website) if model.website else None,
            created_at=model.created_at,
        )
        company._aliases = [CompanyName(alias.name) for alias in model.aliases]
        company._sources = [
            SourceReference(
                source=row.source, reference=row.reference, retrieved_at=row.retrieved_at
            )
            for row in model.sources
        ]
        company._signals = [row.signal for row in model.signals]
        company._verified = model.verified
        return company
