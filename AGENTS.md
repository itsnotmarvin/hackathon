# Project structure

This is one shared application. Four responsibility folders contain parts that work together. Each person works on their own branch.

## Find your working area

Before editing, run `git branch --show-current`, check your current directory, and run `git status --short`.

| Branch | Owner | Folder / responsibility |
| --- | --- | --- |
| Not yet confirmed | AJ | `founders-and-leadership/` |
| `noah_mea` (assignment pending confirmation) | Noah (provisional) | `funding-and-financial-health/` |
| `tm` | Tim | `business-and-market-potential/` |
| `marvin` | Marvin | `reputation-and-ecosystem-interest/` |

Use a confirmed branch mapping to identify your folder automatically. If the user already assigned your folder, use that assignment. For an unknown branch, an unconfirmed mapping, `master`, or a detached HEAD, ask for the assignment before editing unless it is already provided. If your current responsibility folder conflicts with your branch mapping, surface the mismatch before editing. Do not switch branches automatically.

## Folder responsibilities

- `founders-and-leadership/`: founder and leadership background, experience, accomplishments, and risk appetite.
- `funding-and-financial-health/`: funding history, investors, fundraising pace, and financial health.
- `business-and-market-potential/`: market timing, business model, scalability, and headcount growth.
- `reputation-and-ecosystem-interest/`: company reputation, associations, community activity, and public interest.

## Working rules

- Keep implementation in your assigned responsibility folder. You may read other folders to understand the application.
- Follow the shared stack and conventions. These folders are connected parts of one application; do not scaffold separate apps unless requested.
- Reuse agreed interfaces and existing code. Flag changes that affect another folder before changing its expected inputs or outputs.
- Edit other responsibility folders or shared root files only when the user's task includes that work.
- Preserve unrelated changes. When asked to commit, stage only your intended files and inspect the staged diff.
- Run checks appropriate to your changes and report what passed, what failed, and anything still needed to connect your work to the application.
