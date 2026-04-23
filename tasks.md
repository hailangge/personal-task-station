# Tasks

## In progress
- [x] Confirm scope
- [x] Initialize project scaffold
- [x] Implement shared data models and SQLite persistence
- [x] Implement task management server APIs
- [x] Implement billing import, merge, categorize, and summary APIs
- [x] Implement desktop client calendar widgets and task dialogs
- [x] Implement server connection configuration and certificate validation path
- [x] Implement agent-facing skills wrappers
- [x] Add unit, integration, and UI tests
- [x] Run local validation on current machine
- [x] Final review and commit
- [x] Generate self-signed certificates script
- [x] Update server for HTTPS + optional mTLS
- [x] Enforce HTTPS on client and skills
- [x] Add TLS/mTLS integration tests
- [x] Update README and tasks.md

## Notes
- Current blocker/status: Waiting on real financial source files later from user; current implementation must ship with mock/sample-driven validation and extensible import pipeline.
- Assumption: Use `/mnt/data/repositories/personal-task-station` as the canonical git repository path and use HTTPS certificate validation as the default secure connection mode for MVP.
- Current build state: MVP implementation, README, sample fixtures, and automated tests are complete; local validation passed on this Linux machine.
- HTTPS/mTLS: Server now supports TLS (via uvicorn SSL options) and optional client certificate verification. Client and skills reject HTTP entirely. Certificate generation script included at `scripts/generate_certs.py`.
- Test count: 70 passing (was 12 at initial commit).
