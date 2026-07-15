# Features

Feature-first organization: everything specific to one product area lives
inside its feature directory; `src/app/` routes stay thin and compose
feature components.

```
features/
├── dashboard/    # overview & metrics
├── companies/    # importer list, detail, search results
├── research/     # research runs: trigger, progress, analysis output
├── email/        # outreach email drafts: generate, edit, manage
└── settings/     # user & app configuration
```

Convention inside a feature (create subfolders only when needed —
do not pre-create empty ones):

```
features/<name>/
├── components/   # feature-specific React components
├── hooks/        # feature-specific hooks
├── api.ts        # calls to the backend via src/lib/api.ts
└── types.ts      # feature-specific types
```

Shared building blocks stay global: `src/components/ui/` (shadcn/ui),
`src/lib/` (api client, utils). A component used by 2+ features moves
up to `src/components/`.
