"""Application orchestration for synchronous, traceable raw CSV intake."""

import asyncio
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO
from uuid import UUID

from app.domain.bulk_import import ImportSession, RawImportRow, RawImportRowStatus
from app.domain.exceptions import DuplicateOperation
from app.domain.repositories import BulkImportUnitOfWork
from app.services.bulk_import import StreamingCsvIntake

BulkImportUowFactory = Callable[[], BulkImportUnitOfWork]
SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")


@dataclass(frozen=True)
class BulkImportOutcome:
    session: ImportSession
    reused_existing: bool


@dataclass(frozen=True)
class RawImportRowPage:
    session_id: UUID
    page: int
    limit: int
    total: int
    rows: tuple[RawImportRow, ...]


class BulkImportWorkflow:
    def __init__(
        self,
        uow_factory: BulkImportUowFactory,
        parser: StreamingCsvIntake | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._parser = parser or StreamingCsvIntake()

    async def upload(
        self,
        *,
        file: BinaryIO,
        original_filename: str,
        source: str,
        mapping: Mapping[str, str],
        expected_file_sha256: str | None = None,
    ) -> BulkImportOutcome:
        normalized_source = self._normalize_source(source)
        safe_filename = PurePath(original_filename).name.strip()
        if not safe_filename:
            raise ValueError("bulk import requires an original filename")

        preflight = await asyncio.to_thread(
            self._parser.preflight,
            file,
            mapping=mapping,
        )
        if expected_file_sha256 and preflight.file_sha256 != expected_file_sha256:
            raise ValueError("file changed after preflight")
        existing = await self._find_existing(
            source=normalized_source,
            file_sha256=preflight.file_sha256,
        )
        if existing is not None:
            return BulkImportOutcome(session=existing, reused_existing=True)

        session = ImportSession.create(
            source=normalized_source,
            original_filename=safe_filename,
            file_size_bytes=preflight.file_size_bytes,
            file_sha256=preflight.file_sha256,
            mapping_json={
                "logical_fields": dict(mapping),
                "source_headers": list(preflight.headers),
            },
            encoding=preflight.encoding,
        )
        try:
            async with self._uow_factory() as uow:
                await uow.bulk_import.add_session(session)
                await uow.commit()
        except DuplicateOperation:
            raced = await self._find_existing(
                source=normalized_source,
                file_sha256=preflight.file_sha256,
            )
            if raced is None:
                raise
            return BulkImportOutcome(session=raced, reused_existing=True)

        try:
            session.start_processing()
            await self._save_session(session)
            batches = self._parser.iter_batches(
                file,
                session_id=session.id,
                preflight=preflight,
            )
            totals = {"total": 0, "accepted": 0, "invalid": 0, "duplicate": 0}
            while batch := await asyncio.to_thread(_next_batch, batches):
                for row in batch:
                    totals["total"] += 1
                    totals[row.status.value] += 1
                async with self._uow_factory() as uow:
                    persisted = await uow.bulk_import.get_session(session.id)
                    if persisted is None:
                        raise RuntimeError("bulk import session disappeared during processing")
                    await uow.bulk_import.add_rows(batch)
                    persisted.record_progress(
                        total_rows=totals["total"],
                        accepted_rows=totals["accepted"],
                        invalid_rows=totals["invalid"],
                        duplicate_rows=totals["duplicate"],
                    )
                    await uow.bulk_import.save_session(persisted)
                    await uow.commit()
                    session = persisted
            if session.total_rows != preflight.total_rows:
                raise RuntimeError("CSV changed between preflight and persistence")
            session.complete()
            await self._save_session(session)
            return BulkImportOutcome(session=session, reused_existing=False)
        except Exception:
            await self._mark_failed(session.id)
            raise

    async def _find_existing(self, *, source: str, file_sha256: str) -> ImportSession | None:
        async with self._uow_factory() as uow:
            return await uow.bulk_import.find_session(
                source=source,
                file_sha256=file_sha256,
            )

    async def _save_session(self, session: ImportSession) -> None:
        async with self._uow_factory() as uow:
            await uow.bulk_import.save_session(session)
            await uow.commit()

    async def _mark_failed(self, session_id: UUID) -> None:
        try:
            async with self._uow_factory() as uow:
                session = await uow.bulk_import.get_session(session_id)
                if session is None or session.completed_at is not None:
                    return
                session.fail("bulk_import_processing_failed")
                await uow.bulk_import.save_session(session)
                await uow.commit()
        except Exception:
            # Preserve the original processing failure. The global API handler
            # records the request id; no uploaded content is written to logs.
            return

    @staticmethod
    def _normalize_source(source: str) -> str:
        normalized = source.strip().lower()
        if not SOURCE_PATTERN.fullmatch(normalized):
            raise ValueError(
                "bulk import source must contain only lowercase letters, numbers, _, -, or ."
            )
        return normalized


class BulkImportQueryWorkflow:
    def __init__(self, uow_factory: BulkImportUowFactory) -> None:
        self._uow_factory = uow_factory

    async def get_session(self, session_id: UUID) -> ImportSession | None:
        async with self._uow_factory() as uow:
            return await uow.bulk_import.get_session(session_id)

    async def list_rows(
        self,
        *,
        session_id: UUID,
        page: int,
        limit: int,
        status: RawImportRowStatus | None,
    ) -> RawImportRowPage | None:
        async with self._uow_factory() as uow:
            session = await uow.bulk_import.get_session(session_id)
            if session is None:
                return None
            rows, total = await uow.bulk_import.list_rows(
                session_id=session_id,
                status=status,
                offset=(page - 1) * limit,
                limit=limit,
            )
            return RawImportRowPage(
                session_id=session_id,
                page=page,
                limit=limit,
                total=total,
                rows=tuple(rows),
            )


def _next_batch(
    batches: Iterator[tuple[RawImportRow, ...]],
) -> tuple[RawImportRow, ...] | None:
    try:
        return next(batches)
    except StopIteration:
        return None
