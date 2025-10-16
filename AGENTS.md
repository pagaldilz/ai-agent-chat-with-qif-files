# AGENTS

This file defines role workflows that Cursor Agents (or collaborators) can follow. Procedures assume a Docker-first workflow on Windows PowerShell.

## Conventions
- Always run builds/tests inside Docker.
- If dependencies or Dockerfiles change, perform an image rebuild before running.
- No emojis in test files.

## Refactor Agent
- Scope: `app/**`, exclude `db/**` and binary assets.
- Goal: Improve readability and structure without changing behavior.
- Allowed operations: small, incremental edits; add type hints; extract functions; rename for clarity.
- Disallowed: schema changes, breaking API changes, reformatting unrelated files.

### Procedure
1. Sync main and create a feature branch.
2. Identify targets and risks; make focused edits.
3. Rebuild images if Docker or dependencies changed:
   - `docker-compose build --no-cache`
4. Run tests:
   - `docker-compose run --rm qif-agent pytest -q`
5. If failures occur, fix only introduced issues; avoid scope creep.
6. Update `README.md` or `IMPLEMENTATION_STATUS.md` if public behavior changed.
7. Summarize changes, risks, and test results in the PR description.

## Feature Agent
- Scope: `app/**`, `ui/**` (coordinate backend and UI changes).
- Goal: Implement new user-facing capability while preserving existing behavior.
- Disallowed: Editing `db/transactions.db` directly.

### Procedure
1. Design briefly in PR description: inputs, outputs, affected files.
2. Implement in small commits.
3. If requirements or Dockerfiles changed, rebuild:
   - `docker-compose build --no-cache`
4. Start stack locally for manual checks:
   - `docker-compose up --build -d`
5. Add/adjust tests, then run:
   - `docker-compose run --rm qif-agent pytest -q`
6. Update docs and examples.

## Docs Agent
- Scope: `README.md`, `IMPLEMENTATION_STATUS.md`, `test_reports/**`.
- Goal: Keep docs accurate and commands PowerShell-friendly.

### Procedure
1. Validate that commands reflect Docker-first usage.
2. When documenting test steps, use:
   - `docker-compose run --rm qif-agent pytest -q`
3. If behavior changed, document env vars and ports from `docker-compose.yml`.

## Release Agent
- Scope: repo-wide; focuses on build health and change log.

### Procedure
1. Ensure branch is up to date and tests pass in Docker:
   - `docker-compose run --rm qif-agent pytest -q`
2. If dependency files changed, rebuild first:
   - `docker-compose build --no-cache`
3. Update changelog (or PR notes) summarizing features, fixes, and risks.
4. Tag or mark the release as appropriate for your workflow.

## Guardrails
- Never commit secrets or modify `db/transactions.db` directly.
- Keep edits minimal and reversible; avoid unrelated formatting changes.
- Respect existing indentation and formatting styles.


