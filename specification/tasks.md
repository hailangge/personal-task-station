# Tasks

## In progress
- [x] Review current repo state for this iteration: README/specification files/tests/source plus `git status --short` and `git diff --stat`; existing uncommitted calendar/deploy/finance/email work preserved rather than clobbered.
- [x] Re-scope specs to target usable personal small desktop: stable calendar/task desktop plus CSV-first finance/transaction processing MVP.
- [x] Confirm calendar/floating desktop path remains stable and desktop client has Calendar, Tasks, Finance, and Connection tabs wired through `ServerApiClient`.
- [x] Complete finance desktop minimum loop on top of existing API: month summary, transaction list, duplicate table, CSV import button, reanalyze button, and selected duplicate undo.
- [x] Keep finance automation boundary honest: CSV/TSV import is the reliable MVP path; email/bank/provider automation remains optional/experimental and must not be presented as required automatic sync.
- [x] Add UI regression coverage for Finance tab duplicate population, selected duplicate undo, and reanalyze API call.
- [x] Run final targeted validation for calendar, finance/transaction processing, connection config, deployment smoke assets, and py_compile.
- [x] Validation results for this iteration: `python -m py_compile src/personal_task_station/client/api_client.py src/personal_task_station/client/main_window.py src/personal_task_station/client/views/finance_view.py tests/ui/test_main_window.py` passed; `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_billing_pipeline.py tests/integration/test_billing_api.py tests/integration/test_task_api.py tests/ui/test_calendar_widget.py tests/ui/test_main_window.py tests/ui/test_connection_config.py tests/deployment/test_deployment_assets.py -q` passed 37 tests; `bash -n scripts/run-host-server.sh scripts/smoke-test.sh scripts/deploy-linux-server.sh scripts/package-linux-client.sh` passed; `scripts/run-host-server.sh --dry-run`, `scripts/smoke-test.sh --dry-run`, `scripts/deploy-linux-server.sh --dry-run`, and `scripts/package-linux-client.sh --dry-run` passed; `docker compose config` passed.
- [x] Full regression validation: `QT_QPA_PLATFORM=offscreen pytest -q` passed 138 tests.
- [ ] Create one clear git commit after validation passes; do not push.
- [x] Fix task external API contract priority compatibility: `TaskCreate`/`TaskUpdate` now accept integer values, numeric strings, and labels `critical`/`high`/`medium`/`normal`/`low`/`lowest`, while responses keep integer priority output.
- [x] Verify task field alias consistency across schema, API, skill CLI, README, DEPLOYMENT, spec docs, scripts, and tests for `scheduled_date`/`task_date`, `start_time`/`start_at`, `due_time`/`due_at`, and `notes`/`note`.
- [x] Scan/fix task test naming references: no stale pluralized task API test filename references remain; docs/spec references use `tests/integration/test_task_api.py`.
- [x] Add regression coverage for priority string parsing, numeric priority strings, invalid priority validation, API alias round-trip, and task skill alias/priority payloads.
- [x] Run task API contract validation: `pytest tests/unit/test_task_service.py tests/integration/test_task_api.py tests/integration/test_skills.py -q` passed 27 tests; `QT_QPA_PLATFORM=offscreen pytest tests/ui/test_task_dialog.py -q` passed 1 test; `bash -n scripts/smoke-test.sh` passed; `python -m py_compile src/personal_task_station/shared/schemas.py src/personal_task_station/skills/task_skill.py scripts/validate_security.py` passed; `pytest tests/deployment/test_deployment_assets.py -q` passed 7 tests; `scripts/smoke-test.sh --dry-run` passed.
- [x] Re-audit production-readiness gaps across client/server/config/dependencies/SQLite/startup/tests/uncommitted changes/Docker/scripts/docs.
- [x] Align `specification/requirements.md`, `specification/design.md`, and `specification/tasks.md` to production-ready accessible delivery.
- [x] Choose host-based service as primary access plan and Docker Compose as alternate; document local/LAN/remote boundaries, API key, optional HTTPS/mTLS, and reverse proxy/tunnel recommendation.
- [x] Add operator-ready `.env.example`, host startup script, API smoke script, and systemd user service template.
- [x] Update README/DEPLOYMENT with local and LAN addresses, client connection instructions, health/API smoke commands, and Docker alternate path.
- [x] Add deployment asset tests for host/smoke/systemd/env/docs behavior.
- [x] Run focused production-readiness validation for script syntax/dry-runs, deployment tests, and targeted tests.
- [x] Redesign desktop floating Calendar Month/Week/Compact content visuals (`src/personal_task_station/client/main_window.py`, `src/personal_task_station/client/widgets/calendar_widget.py`, `tests/ui/test_calendar_widget.py`)
- [x] Add desktop window affordances for resize, edge snap/dock behavior, top-most controls, and tray show/hide/quit (`src/personal_task_station/client/main_window.py`, `tests/ui/test_main_window.py`)
- [x] Collapse secondary controls into compact top-right icon/menu affordances (`src/personal_task_station/client/main_window.py`, `tests/ui/test_main_window.py`)
- [x] Add configurable persisted desktop main background color via compact Appearance menu (`src/personal_task_station/shared/schemas.py`, `src/personal_task_station/client/main_window.py`, `tests/ui/test_main_window.py`, `tests/ui/test_connection_config.py`)
- [x] Add configurable persisted calendar area background color via compact Appearance menu (`src/personal_task_station/shared/schemas.py`, `src/personal_task_station/client/main_window.py`, `src/personal_task_station/client/widgets/calendar_widget.py`, `tests/ui/test_main_window.py`, `tests/ui/test_calendar_widget.py`, `tests/ui/test_connection_config.py`)
- [x] Fix calendar background binding so `calendar_background_color` applies to the Month content viewport/cells/panel and Week/Compact grids/cards, not only outer border styling (`src/personal_task_station/client/widgets/calendar_widget.py`, `tests/ui/test_calendar_widget.py`)
- [x] Validate UI behavior locally: `QT_QPA_PLATFORM=offscreen pytest tests/ui/test_calendar_widget.py tests/ui/test_main_window.py -q` passed 9 tests; `QT_QPA_PLATFORM=offscreen pytest tests/ui -q` passed 12 tests.
- [ ] Independent Kimi verification for prior UI follow-up remains not run in this Codex-only implementation pass.

## UI Follow-up Validation
- [x] Production readiness validation: `pytest tests/deployment/test_deployment_assets.py tests/unit/test_client_config.py -q` passed 12 tests; `bash -n scripts/run-host-server.sh scripts/smoke-test.sh scripts/deploy-linux-server.sh scripts/package-linux-client.sh` passed; `scripts/run-host-server.sh --dry-run`, `scripts/smoke-test.sh --dry-run`, `scripts/deploy-linux-server.sh --dry-run`, and `scripts/package-linux-client.sh --dry-run` passed; `docker compose config` passed; `pytest tests/integration/test_task_api.py tests/integration/test_tls.py -q` passed 10 tests; temporary host server on `127.0.0.1:8765` passed `scripts/smoke-test.sh`; `pytest tests/ui/test_connection_config.py -q` passed 2 tests.
- [x] `python -m py_compile src/personal_task_station/client/main_window.py src/personal_task_station/client/widgets/calendar_widget.py tests/ui/test_main_window.py tests/ui/test_calendar_widget.py` passed.
- [x] `QT_QPA_PLATFORM=offscreen pytest tests/ui/test_calendar_widget.py tests/ui/test_main_window.py -q` passed: 9 tests in 22.92s.
- [x] `QT_QPA_PLATFORM=offscreen pytest tests/ui -q` passed: 12 tests in 23.16s.
- [x] `python -m py_compile src/personal_task_station/client/main_window.py src/personal_task_station/shared/schemas.py tests/ui/test_main_window.py tests/ui/test_connection_config.py` passed.
- [x] `pytest tests/ui/test_main_window.py tests/ui/test_connection_config.py -q` passed: 11 tests in 0.91s.
- [x] `QT_QPA_PLATFORM=offscreen pytest tests/ui/test_calendar_widget.py tests/ui/test_main_window.py tests/ui/test_connection_config.py -q` passed: 13 tests in 23.34s.
- [x] `python -m py_compile src/personal_task_station/shared/schemas.py src/personal_task_station/client/main_window.py src/personal_task_station/client/widgets/calendar_widget.py tests/ui/test_main_window.py tests/ui/test_calendar_widget.py tests/ui/test_connection_config.py` passed.
- [x] `QT_QPA_PLATFORM=offscreen pytest tests/ui/test_calendar_widget.py tests/ui/test_main_window.py tests/ui/test_connection_config.py -q` passed: 15 tests in 26.06s.
- [x] Validate calendar content background binding follow-up: `python -m py_compile src/personal_task_station/client/widgets/calendar_widget.py tests/ui/test_calendar_widget.py` passed; `QT_QPA_PLATFORM=offscreen pytest tests/ui/test_calendar_widget.py -q` passed: 4 tests in 21.84s; `QT_QPA_PLATFORM=offscreen pytest tests/ui/test_calendar_widget.py tests/ui/test_main_window.py -q` passed: 14 tests in 22.96s.
- [ ] Kimi UI follow-up verification not run in this Codex-only implementation pass.

## Done
- [x] Set compact floating defaults and position persistence fields (`src/personal_task_station/shared/schemas.py`)
- [x] Tune desktop main window into a smaller translucent top-right draggable widget (`src/personal_task_station/client/main_window.py`)
- [x] Add UI regression coverage for floating defaults, saved position restore, and drag persistence (`tests/ui/test_main_window.py`)
- [x] Kimi strict review completed (this agent). Verified task service/API CRUD, filters, status history, subitem create/edit/delete/reorder/toggle, calendar summary/month aggregation, client connection/task list/edit/calendar flows, Docker assets, Linux/Windows package scripts, README/DEPLOYMENT consistency, and tests.
- [x] Fix Kimi-identified subitem stale-relationship class: `add_subitem`, `delete_subitem`, `update_subitem`, `toggle_subitem`, and `reorder_subitems` now refresh task relationships and status sync reads authoritative current subitems.
- [x] Add regression coverage for same-session `task.subitems` / `get_task` freshness after add/delete, current-subitem status sync after add, and update/reorder relationship order consistency.
- [x] Run post-fix targeted validation: `pytest tests/unit/test_task_service.py tests/integration/test_task_api.py -q` passed with 11 tests.
- [x] Kimi strict review identified subitem reorder response staleness; Codex fixed `POST /tasks/{task_id}/subitems/reorder` to return the requested order immediately and added regression coverage for response plus subsequent GET.
- [x] Run post-Kimi targeted validation: `pytest tests/integration/test_task_api.py -q` passed with 3 tests.
- [x] Re-scope specification to prioritize task management, calendar view, and deployment delivery (`specification/requirements.md`, `specification/design.md`, `specification/tasks.md`)
- [x] Review existing task-management/server/client/deployment code for gaps (`src/personal_task_station/server/routers/tasks.py`, `src/personal_task_station/server/services/tasks.py`, `src/personal_task_station/client/*`, `Dockerfile`, `docker-compose.yml`, `scripts/*`)
- [x] Complete task service/API CRUD, status history, subitem operations, search/filtering (`src/personal_task_station/server/routers/tasks.py`, `src/personal_task_station/server/services/tasks.py`, `src/personal_task_station/shared/schemas.py`)
- [x] Complete calendar aggregation API and tests (`src/personal_task_station/server/routers/tasks.py`, `src/personal_task_station/server/services/tasks.py`, `tests/integration/test_task_api.py`, `tests/unit/test_task_service.py`)
- [x] Complete client task UI/calendar view/connection path (`src/personal_task_station/client/api_client.py`, `src/personal_task_station/client/main_window.py`, `src/personal_task_station/client/widgets/calendar_widget.py`, `src/personal_task_station/client/dialogs/*`, `src/personal_task_station/client/views/connection_view.py`)
- [x] Complete Docker server deployment files and docs (`Dockerfile`, `docker-compose.yml`, `.dockerignore`, `scripts/docker-entrypoint.sh`, `DEPLOYMENT.md`, `README.md`)
- [x] Add Linux deployment/package scripts (`scripts/deploy-linux-server.sh`, `scripts/package-linux-client.sh`)
- [x] Add Windows client package script (`scripts/package-windows-client.ps1`)
- [x] Add/extend unit, integration, UI, and deployment validation tests (`tests/unit/test_task_service.py`, `tests/integration/test_task_api.py`, `tests/ui/*`, `tests/deployment/test_deployment_assets.py`)
- [x] Run Codex local validation and record commands/results
- [x] Prepare handoff notes for Kimi strict review

## Kimi Review Handoff
- Kimi strict review evidence found one concrete product defect: reorder updated database `sort_order` values but returned a stale pre-reorder `task.subitems` relationship in the immediate response.
- Additional Codex follow-up status: service now reloads current subitems for status sync/order decisions and refreshes in-memory task relationships after add/update/toggle/delete/reorder; regression tests cover stale add/delete/status-sync/order cases.
- Kimi verification status: **COMPLETED** — independent Kimi verification performed. All 99 tests pass. Docker Compose config validates. Linux scripts pass syntax and dry-run checks. Windows script is syntactically valid and documents PyInstaller. README and DEPLOYMENT.md are consistent with implementation. One concrete API defect was found and fixed: `create_task` with subitems triggering status sync produced an unflushed history entry that caused a `ResponseValidationError`; fixed by adding `session.flush()` after `_sync_task_status_from_subitems`. Integration test `test_create_task_with_completed_subitem_syncs_status` added as regression coverage.
- Verify task status vocabulary is spec-compatible: API accepts/returns `blocked`; legacy `TaskStatus.ON_HOLD` remains an alias for existing code/tests.
- Verify public/spec task field names work: `scheduled_date`, `start_time`, `due_time`, and `notes` are accepted and emitted alongside legacy internal names.
- Verify task API endpoints: CRUD, filters, status history, subitem create/edit/delete/reorder/toggle, `/tasks/calendar/summary`, and `/tasks/calendar/month`.
- Verify desktop flow: connection config/test, task list filters/actions, task edit dialog status history/subitems, calendar markers, date popup quick add/edit/status change.
- Verify Docker and scripts: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `scripts/docker-entrypoint.sh`, `scripts/deploy-linux-server.sh`, `scripts/package-linux-client.sh`, and `scripts/package-windows-client.ps1`.
- Verify docs match commands in `README.md` and `DEPLOYMENT.md`.

## Notes
- Current owner instruction for this iteration: turn the repo into a usable small desktop focused on calendar plus finance/transaction MVP; preserve existing uncommitted finance/email/billing work and isolate/document risky automation rather than clobbering it.
- Git status before this round already includes prior uncommitted finance/email/Docker changes and deleted root spec docs replaced by `specification/*`; preserve useful prior work but align final repo with this round's priority.
- Completion requires Codex implementation, local validation, one clear git commit if validation passes, and no push.
