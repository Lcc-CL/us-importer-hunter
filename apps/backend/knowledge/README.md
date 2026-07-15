# Knowledge Base

Source corpus for RAG and agent memory. Everything the AI "knows" beyond
its prompts starts here: the rag service ingests these documents
(embedding → Qdrant) and agents retrieve from them at run time.

```
knowledge/
├── industry/    # industry knowledge: verticals, product categories, HS codes
├── shipping/    # shipping knowledge: modes, containers, incoterms, documents
├── logistics/   # logistics operations: lanes, ports, customs, forwarding
├── sales/       # sales playbooks: pitch angles, objection handling
├── emails/      # outreach email examples, templates, do's & don'ts
├── customer/    # customer knowledge: personas, pain points, case studies
└── faq/         # frequently asked questions and canonical answers
```

## Conventions

- Plain Markdown (`.md`), one topic per file, English or Chinese.
- Filenames are kebab-case and descriptive: `fcl-vs-lcl.md`,
  `cold-email-structure.md`.
- Documents are chunked at ingestion — keep files focused; prefer many
  small files over one large one.
- This directory is content, not code: editing it never requires a code
  change. Re-ingestion picks up changes (pipeline lands with the rag
  service, later sprint).
