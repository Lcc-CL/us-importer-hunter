"""Print a row-free D5e acceptance preflight report for a local file."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.services.acceptance import (
    NetEasePreflightReport,
    RealDataPreflightService,
    UmailPreflightReport,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect a local NetEase or Umail file without persistence or providers."
    )
    parser.add_argument("kind", choices=("netease", "umail"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--mapping", type=Path)
    return parser.parse_args()


def _mapping(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    decoded: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in decoded.items()
    ):
        raise ValueError("mapping must be a JSON object of string keys and values")
    return {key: value for key, value in decoded.items()}


def main() -> None:
    arguments = _arguments()
    service = RealDataPreflightService()
    mapping = _mapping(arguments.mapping)
    report: NetEasePreflightReport | UmailPreflightReport
    with arguments.file.open("rb") as source:
        if arguments.kind == "netease":
            report = service.preflight_netease(
                source,
                filename=arguments.file.name,
                mapping=mapping,
            )
        else:
            report = service.preflight_umail(
                source,
                filename=arguments.file.name,
                mapping=mapping,
            )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
