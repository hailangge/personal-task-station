# Tasks

## In progress
- [ ] Await independent Kimi verification of the post-review subitem stale-relationship regression fix.

## Done
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
- Kimi verification status: pending; do not mark review complete until independent Kimi evidence is added.
- Verify task status vocabulary is spec-compatible: API accepts/returns `blocked`; legacy `TaskStatus.ON_HOLD` remains an alias for existing code/tests.
- Verify public/spec task field names work: `scheduled_date`, `start_time`, `due_time`, and `notes` are accepted and emitted alongside legacy internal names.
- Verify task API endpoints: CRUD, filters, status history, subitem create/edit/delete/reorder/toggle, `/tasks/calendar/summary`, and `/tasks/calendar/month`.
- Verify desktop flow: connection config/test, task list filters/actions, task edit dialog status history/subitems, calendar markers, date popup quick add/edit/status change.
- Verify Docker and scripts: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `scripts/docker-entrypoint.sh`, `scripts/deploy-linux-server.sh`, `scripts/package-linux-client.sh`, and `scripts/package-windows-client.ps1`.
- Verify docs match commands in `README.md` and `DEPLOYMENT.md`.

## Notes
- Current owner instruction: pause billing/finance expansion; only touch finance code if needed to keep existing tests passing.
- Git status before this round already includes prior uncommitted finance/email/Docker changes and deleted root spec docs replaced by `specification/*`; preserve useful prior work but align final repo with this round's priority.
- Completion requires Codex implementation, Kimi independent verification evidence, SE-side validation, memory update, then handoff to github-assistant for commit/push (do not push here).
