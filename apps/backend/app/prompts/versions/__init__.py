"""Versioned prompt snapshots.

Active prompts live in their agent directories (shared/, research/, ...);
when a prompt changes, the previous version is archived here so runs
remain reproducible and prompts can be diffed / rolled back.

Convention (to finalize with the first real prompt):
    versions/<agent>/<prompt-name>.v<N>.md
"""
