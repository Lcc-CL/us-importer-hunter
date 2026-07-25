"""Pure, dependency-free text normalization shared across layers.

Lives in shared (not services) because persistence-layer lookups and the
entity resolver must normalize identically — a name normalized two ways is
two different companies.
"""

import re
import unicodedata

COMPANY_SUFFIXES = (
    "incorporated",
    "inc",
    "corporation",
    "corp",
    "company",
    "co",
    "limited",
    "ltd",
    "llc",
    "l.l.c.",
    "llp",
    "l.l.p.",
    "plc",
    "gmbh",
    "s.a.",
    "s.a",
    "sa",
    "bv",
    "b.v.",
    "pty ltd",
    "pty. ltd.",
    "pte ltd",
    "pte. ltd.",
)


def normalize_company_name(raw: str) -> str:
    """Remove suffixes, punctuation, extra whitespace; lowercase."""
    if not raw:
        return ""
    n = unicodedata.normalize("NFKD", raw)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower()
    # Remove periods from abbreviations before suffix removal
    n = n.replace(".", " ")
    n = re.sub(r"[,\-–—()\[\]{}«»\"'`′]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    # Remove suffixes as whole tokens
    tokens = n.split()
    result = [
        t for t in tokens if t not in COMPANY_SUFFIXES and t.rstrip(".") not in COMPANY_SUFFIXES
    ]
    return " ".join(result) if result else n
