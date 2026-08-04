"""Bounded synthetic performance sample for D5e preflight."""

import io
import time
import tracemalloc
from typing import BinaryIO, cast

from app.services.acceptance import ACCEPTANCE_MAX_ROWS, RealDataPreflightService


def test_netease_preflight_20k_rows_stays_bounded() -> None:
    rows = ["company_id,company,email,product,shipment_date"]
    rows.extend(
        f"C-{index},Company {index},buyer-{index}@example.test,hardware,2026-07-01"
        for index in range(ACCEPTANCE_MAX_ROWS)
    )
    content = ("\n".join(rows) + "\n").encode()
    source = cast(BinaryIO, io.BytesIO(content))

    tracemalloc.start()
    started = time.perf_counter()
    report = RealDataPreflightService().preflight_netease(
        source,
        filename="synthetic-20k.csv",
    )
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert report.total_rows == ACCEPTANCE_MAX_ROWS
    assert report.estimated_company_count == ACCEPTANCE_MAX_ROWS
    assert report.estimated_contact_count == ACCEPTANCE_MAX_ROWS
    assert elapsed < 10
    assert peak < 128 * 1024 * 1024
    print(f"D5e preflight 20k: {elapsed:.3f}s, peak={peak / 1024 / 1024:.1f} MiB")
