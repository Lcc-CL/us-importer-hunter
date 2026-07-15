"""Demo company dataset.

Field names follow specs/company.yaml; values are fictional but shaped
like real US importers so demos and tests exercise realistic data.
"""

from typing import Any

DEMO_COMPANIES: list[dict[str, Any]] = [
    {
        "name": "Pacific Home Goods Inc.",
        "website": "https://pacifichomegoods.example.com",
        "country": "US",
        "state": "CA",
        "city": "Los Angeles",
        "industry": "Home & Garden",
        "product_categories": ["furniture", "home decor"],
        "hs_codes": ["9403", "9405"],
        "origin_countries": ["CN", "VN"],
        "lanes": ["CNSHA-USLAX", "VNSGN-USLAX"],
        "sources": ["demo"],
    },
    {
        "name": "Great Lakes Auto Parts LLC",
        "website": "https://glautoparts.example.com",
        "country": "US",
        "state": "MI",
        "city": "Detroit",
        "industry": "Automotive",
        "product_categories": ["brake components", "filters"],
        "hs_codes": ["8708"],
        "origin_countries": ["CN", "MX"],
        "lanes": ["CNNGB-USCHI"],
        "sources": ["demo"],
    },
    {
        "name": "Eastline Apparel Group",
        "website": "https://eastlineapparel.example.com",
        "country": "US",
        "state": "NY",
        "city": "New York",
        "industry": "Apparel",
        "product_categories": ["knitwear", "outerwear"],
        "hs_codes": ["6110", "6201"],
        "origin_countries": ["CN", "BD", "IN"],
        "lanes": ["CNSHA-USNYC", "BDCGP-USNYC"],
        "sources": ["demo"],
    },
]
