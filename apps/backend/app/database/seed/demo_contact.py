"""Demo contact dataset.

Contacts reference demo companies by name; values are fictional.
"""

from typing import Any

DEMO_CONTACTS: list[dict[str, Any]] = [
    {
        "company_name": "Pacific Home Goods Inc.",
        "full_name": "Maria Chen",
        "title": "Director of Supply Chain",
        "email": "maria.chen@pacifichomegoods.example.com",
        "linkedin_url": None,
        "sources": ["demo"],
    },
    {
        "company_name": "Great Lakes Auto Parts LLC",
        "full_name": "David Kowalski",
        "title": "Logistics Manager",
        "email": "d.kowalski@glautoparts.example.com",
        "linkedin_url": None,
        "sources": ["demo"],
    },
    {
        "company_name": "Eastline Apparel Group",
        "full_name": "Priya Raman",
        "title": "VP Operations",
        "email": "priya.raman@eastlineapparel.example.com",
        "linkedin_url": None,
        "sources": ["demo"],
    },
]
