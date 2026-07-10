# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A standalone Django **sandbox** implementation of task T-068: integrating ANPR (automatic number-plate recognition) events into a vehicle gate pass log, modeled after a real task spec written for a separate, larger codebase called **Steiza** (not present on this machine). The actual Django project lives in `macroscope/` (note: project dir is spelled "macroscope", the surveillance product is "Macroscop").

The spec PDF — `T-068-macroscop-vehicle-gate-integration.pdf` at the repo root — originally assumed Macroscop would perform ANPR. In practice, the Macroscop server has no GPU, so recognition is done on-camera by the **Dahua DHI-ITC413-PW4D-IZ3**. We connect directly to the camera, bypassing Macroscop entirely.

The spec assumes infrastructure that doesn't exist here (`terminal.Terminal`, `accounts.CustomUser`, `TimeStampVisibleModel`, `TerminalActionBasedPermission`, a `tos-client` frontend). This repo reimplements the same domain model and architecture standalone, with deliberate simplifications (see "Deviations from the spec" below), so the code can later be ported into the real Steiza repo with minimal changes.

## Current production status (as of 2026-07-08)

- Integration is **live**: worker connects directly to Dahua camera at `195.19.150.181:8000`
- Terminal id=2 ("Колосок"), GateCamera id=2 (`role=ENTRY`, `channel_id=b334adc4-d8d1-4d30-8cdb-4eb122fe926c`)
- `VehicleGatePass` records are being created in real-time from camera events
- Macroscop server (`195.19.150.181:8080`) still inaccessible — license key not yet activated
- Reliability threshold for Dahua: `0.60` (Dahua's Confidence 0–100 scale, divided by 100)

## Commands

All commands run from `macroscope/` (the Django project root), using the venv at `../.venv/bin/python` (or activate it first).

```bash
# from repo root
source .venv/bin/activate
cd macroscope

python manage.py runserver              # dev server, http://127.0.0.1:8000
python manage.py test                   # full test suite
python manage.py test vehicle_fleet      # single app
python manage.py makemigrations          # after model changes
python manage.py migrate
python manage.py createsuperuser         # for /admin/

# Dahua direct integration (current production mode)
nohup python manage.py run_macroscop_integration \
    --terminal-id=2 --source=dahua --gate-camera-id=2 \
    > /tmp/dahua_integration.log 2>&1 &

# Macroscop integration (pending license activation)
python manage.py run_macroscop_integration --terminal-id=<pk>                 # live /event stream
python manage.py run_macroscop_integration --terminal-id=<pk> --mode=demo      # server-side demo
python manage.py run_macroscop_integration --terminal-id=<pk> \
    --fixture=vehicle_fleet_integration/tests/fixtures/plate_event.json        # offline replay
```

Secrets are read from `macroscope/.env` (git-ignored) via `django-environ`. Never commit credentials.

## Architecture

Three Django apps, wired into `macroscope/macroscope/settings.py` and `macroscope/macroscope/urls.py`:

- **`terminal/`** — minimal stand-in for Steiza's real `Terminal` model (multi-tenancy root). Just `Terminal(name, slug, is_active)`.
- **`vehicle_fleet/`** — domain layer: models, REST API, business logic. Layout follows `urls.py → views.py → serializers.py → services.py → models.py`:
  - `models.py`: `TimeStampedModel` (abstract base), `FleetVehicle`, `GateCamera`, `VehicleGatePass`, `MacroscopIntegrationState`.
  - `constants.py`: `GateCameraRole`, `GatePassDirection`, `GatePassSource`, `MACROSCOP_DIRECTION_MAP` (maps both Russian `"Въезд"/"Выезд"` and English `"entry"/"exit"` to our enum — the latter needed for Dahua events).
  - `services.py`: `PlateNormalizer` (upper-case, strip spaces/hyphens, keep Cyrillic), `FleetVehicleService` (uniqueness validation), `GatePassService` (manual gate-pass creation).
  - `views.py`/`urls.py`: all endpoints scoped under `/api/terminals/<int:terminal_pk>/` via `TerminalScopedMixin`.
- **`vehicle_fleet_integration/`** — infrastructure layer, isolated from the public API:
  - **Macroscop path** (pending):
    - `client.py`: `MacroscopHttpClient` — Basic auth with MD5 password, `get_channels()`, `stream_events()` (NDJSON `/event`), `get_archive_events()`, `get_archive_event_types()`.
    - `event_parser.py`: `parse_event_line()` (drops keep-alives), `extract_plate_event()` → `ParsedPlateEvent`.
    - `stream_worker.py`: long-poll loop on `/event` with exponential reconnect backoff.
    - `archive_poller.py`: fallback poll on `/archive_events`.
  - **Dahua path** (active):
    - `dahua_client.py`: `DahuaHttpClient` — Digest auth, `stream_events()` parses `multipart/x-mixed-replace` stream from `/cgi-bin/eventManager.cgi`.
    - `dahua_event_parser.py`: `extract_plate_event_dahua()` → `ParsedPlateEvent`. See field mapping below.
    - `dahua_stream_worker.py`: long-poll loop with exponential reconnect backoff (1s → 60s cap).
  - `event_processor.py`: shared `process_plate_event()` — works for both Macroscop and Dahua events.
  - `management/commands/run_macroscop_integration.py`: entrypoint; `--source=macroscop` (default) or `--source=dahua --gate-camera-id=<pk>`.

## REST API endpoints

All under `/api/terminals/<terminal_pk>/`, require authentication (Basic Auth or Session):

| Method | URL | Description |
|--------|-----|-------------|
| GET, POST | `fleet-vehicles/` | List / create fleet vehicles |
| GET, PATCH, DELETE | `fleet-vehicles/<id>/` | Retrieve / update / soft-delete |
| GET, POST | `vehicle-gate-passes/` | List / create gate passes (POST = manual only) |
| GET | `vehicle-gate-passes/<id>/` | Retrieve single pass |
| GET, POST | `gate-cameras/` | List / create cameras |
| GET, PATCH | `gate-cameras/<id>/` | Retrieve / update camera |
| POST | `gate-cameras/sync/` | Sync from Macroscop (501 stub) |

Plus `/admin/` Django admin.

## Dahua camera event field mapping

The Dahua DHI-ITC413-PW4D-IZ3 sends `multipart/x-mixed-replace` with bodies like:
`Code=TrafficJunction;action=Pulse;index=0;data={...JSON...}`

**Critical gotcha — Dahua timestamp fields:**
- `"UTC"` field = camera's **local time (МСК)** expressed as Unix seconds — **NOT actual UTC** (misleading name).
- `"RealUTC"` field = actual UTC Unix timestamp — **use this one**.
- Difference is always exactly 10800 seconds (3 hours = UTC+3 offset).
- Parser uses `data['RealUTC']` with fallback to `data['UTC']`.

Field mapping in `dahua_event_parser.py`:

| Our field | Dahua JSON path | Notes |
|-----------|-----------------|-------|
| `numberplate` | `data['TrafficCar']['PlateNumber']` | fallback: `data['Object']['Text']` |
| `passed_at` | `data['RealUTC']` | Unix timestamp, treated as UTC |
| `direction` | `data['TrafficCar']['DrivingDirection'][0]` | `"Leave"` → exit, `"Approach"` → entry |
| `reliability` | `data['Object']['Confidence'] / 100.0` | Dahua gives 0–100, we store 0.0–1.0 |
| `event_id` | `data['EventID']` | Integer → `uuid.UUID(int=...)` for UUIDField |
| `recognized_color` | `data['TrafficCar']['VehicleColor']` | |
| `recognized_type` | `data['TrafficCar']['CarType']` | |

**Observed data quality issues (inform Александр):**
- `"Country"` field shows `"PSE"`, `"NOR"` etc. instead of Russia — camera's country/plate-format setting is wrong, should be set to RUS.
- Some plates lose the first letter (`802TM193` instead of `А802ТМ193`) — camera angle or recognition zone misconfigured.
- Occasional fully wrong reads at high confidence (`WIIELT0NG` at 86%) — likely night glare; IR illumination settings need tuning.

## Event processing algorithm (`event_processor.process_plate_event`)

1. Drop if `reliability < MIN_RELIABILITY` (Macroscop: `settings.MACROSCOP_INTEGRATION['MIN_RELIABILITY']` default `0.85`; Dahua: `settings.DAHUA_INTEGRATION['MIN_RELIABILITY']` default `0.60`) — debug log.
2. Drop if `macroscop_event_id` already exists in DB (hard unique index on `VehicleGatePass`) — warning log.
3. Normalize plate via `PlateNormalizer`.
4. Look up `GateCamera` by `(terminal, channel_id)`; warn if unbound but don't abort.
5. Resolve `direction`: event's `direction` field takes priority (via `MACROSCOP_DIRECTION_MAP`, accepts both Russian and English values); falls back to `GateCamera.role`. Abort with warning if neither resolves.
6. Soft dedup: skip if identical `(registration_number, direction, gate_camera)` pass exists within `DEDUP_WINDOW_SEC` (default `60s`) of this event's timestamp.
7. Look up `FleetVehicle` by `(terminal, registration_number)` — optional link.
8. Create `VehicleGatePass(source=macroscop)`, update `MacroscopIntegrationState.last_event_at` — both in one transaction.

## Deviations from the original spec (intentional, agreed with the user)

- **`Terminal`** is a real model here (not hardcoded) — kept the multi-tenant shape for fidelity with the eventual Steiza port.
- **User model**: built-in `django.contrib.auth.User`, not a custom `accounts.CustomUser`.
- **Permissions**: global DRF `IsAuthenticated` only — no granular `TerminalActionBasedPermission`. Re-introduce when porting into Steiza.
- **Pagination**: `PageNumberPagination` (`PAGE_SIZE=50`).
- **`gate-cameras/sync/`** — `501` stub; wire to `MacroscopHttpClient.get_channels()` once server is reachable.
- **Dahua direct integration** — not in the original spec; added because Macroscop server has no GPU for ANPR. Macroscop is redundant in the current single-camera setup; would add value as an aggregator if multiple cameras are added.
- Frontend (`tos-client` equivalent) is out of scope.

## Macroscop API essentials (from the T-068 spec PDF)

- Base URL: `http://195.19.150.181:8080` (port forwarded from router; also `10.66.66.21:8080` via WireGuard VPN).
- Auth: HTTP Basic with password as **MD5 hash** (`Authorization: Basic base64(login:md5(password))`), or GET params for `/event`.
- Credentials: login=`root`, password=empty → MD5=`d41d8cd98f00b204e9800998ecf8427e`.
- `GET /api/channels`, `GET /event` (NDJSON stream), `POST /archive_events`, `GET /archive_event_types`.
- Plate event fields: `EventId`, `Numberplate`/`plateText`, `ZonedTimestamp`, `ChannelId`, `direction` (`"Въезд"`/`"Выезд"`), `Reliability` (**comma decimal separator**, e.g. `"0,9999972581863403"`).

## Org structure

- **Колосок** — end client/customer; owns the terminal and Macroscop license.
- **Macroscop** — third-party VMS vendor; not involved day-to-day.
- **`@ter224` / Александр** — Колосок's IT/camera contractor; installed the Macroscop server and Dahua camera. Contact for camera config changes and credentials.

## Open questions (status as of 2026-07-10)

1. **Macroscop license activation** — still waiting on Колосок's руководитель. Once activated, Александр will configure the API user. Port 8080 is now accessible via port forwarding (`195.19.150.181:8080`) but returns `401` — auth/license still blocking.
2. **Camera country/plate format setting** — Александр should set plate recognition country to Russia (RUS) in Dahua SmartPSS or web interface to improve accuracy. Currently recognizing plates as PSE/NOR/NLD.
3. **Camera recognition zone and angle** — some plates lose the first character; Александр should verify the recognition zone covers the full plate area and the camera angle is within spec (≤30° from vehicle axis).
4. **Macroscop camera UUIDs** — UUIDs of entry/exit cameras and "Обнаружен автономер" event type; needed when Macroscop integration is activated.
5. **`/archive_events` response shape** — not documented in spec; `archive_poller.py` handles both bare list and `{"events": [...]}` defensively.

## Reference artifacts

- `T-068-macroscop-vehicle-gate-integration.pdf` — the task spec this implementation follows.
- `macroscop-4.6-api.pdf` — official Macroscop REST/HTTP API docs.
- Implementation plan: `~/.claude/plans/enchanted-forging-wand.md`.
- Telegram `@ter224` (Александр) — contact for camera config and Macroscop credentials.