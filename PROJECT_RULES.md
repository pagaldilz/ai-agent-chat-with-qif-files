## Project Rules

These rules guide all AI-assisted changes in this repository. They are always-on and apply across tasks, PRs, and agents.

### Environment and Tooling
- Primary OS/shell: Windows 10 with PowerShell. Prefer PowerShell command examples.
- Application runs in Docker via `docker-compose.yml`. Assume Docker context for running, testing, and building.
- When `requirements.txt` or any package-related dependency changes, rebuild images.

### Build and Run (PowerShell)
- Start services (forces rebuild when needed):
  - `docker-compose up --build`
- Rebuild without starting:
  - `docker-compose build --no-cache`
- Run tests in backend container:
  - `docker-compose run --rm qif-agent pytest -q`

### Testing Policy
- All tests must pass before merge: `pytest -q` executed inside Docker.
- No emojis in test files (content or snapshot outputs).
- Add tests for bug fixes and new features where feasible.

### Code Style and Quality
- Python 3.12; write clear, descriptive names and explicit types in public APIs.
- Prefer early returns; avoid broad `try/except` and unused catches.
- Keep edits focused; do not reformat unrelated code.
- Preserve file indentation and formatting styles; do not convert tabs/spaces.

### Architecture and Boundaries
- Backend FastAPI app in `app/`; UI in `ui/`.
- Do not modify `db/transactions.db` directly; interact through application code.
- Place new analyzers under `app/analyzers/` and new parsers under `app/parsers/`.

### Data and Security
- Never commit secrets. Use environment variables configured in `docker-compose.yml`.
- Logs must not contain sensitive personal information.

### Agent/AI Editing Guardrails
- Favor small, incremental edits with clear diffs.
- Update `README.md` and `IMPLEMENTATION_STATUS.md` when behavior or interfaces change.
- If build/test steps depend on Docker, ensure images are rebuilt automatically as part of the procedure.

### Auto-Rebuild Guidance
- Trigger a rebuild when any of the following change:
  - `requirements.txt`, `ui/requirements.txt`
  - `Dockerfile`, `ui/Dockerfile`
  - System-level dependencies or environment variables
- Recommended commands (PowerShell):
  - `docker-compose build --no-cache`
  - `docker-compose up -d`


