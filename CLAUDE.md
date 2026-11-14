# CLAUDE.md — Férový nájem

Read `docs/SPEC.md` first. It is the source of truth for scope, data sources, API and legal rules.

## Working with Pavel
- Talk in Russian; code, comments, commits and docs in English.
- Be a sparring partner: short answers, no filler. Push back only on real technical/legal errors or unnoticed risks (max 3 sentences), then it's his call.
- Pavel is an SRE (Python, Docker, K8s, Terraform, ELK) and new to macOS/iOS. Explain Xcode/Swift specifics briefly; don't explain infra basics.

## Stack
- Backend: Python 3.12, FastAPI, Postgres + PostGIS, SQLAlchemy/psycopg, pytest, ruff.
- iOS: Swift, SwiftUI, iOS 17+, String Catalog (cs + en). No third-party deps unless justified.
- Infra: Docker Compose locally; one small cloud host for beta.

## Hard rules
- Never put API keys in the iOS app or the repo. Use `.env` (gitignored) + `.env.example`.
- Never fetch, display or store owner names or other personal data from the cadastre.
- No scraping of Sreality / Bezrealitky / Facebook or any portal.
- No persistent personal data. Reports are computed and returned, not stored.
- Every **[VERIFY]** item in SPEC.md: check the real source (OpenAPI spec, actual XLSX, docs) before writing code that depends on it. If reality differs, update SPEC.md and tell Pavel.
- Scoring thresholds live in config, not hard-coded.
- Report wording: factual ("X % above MF median"), never accusatory.

## Workflow
- Work milestone by milestone (SPEC.md §9). Start with M0; confirm the API KN key works before anything else depends on it.
- Ingestion jobs must be idempotent and runnable from CLI (`python -m app.ingest.<source>`).
- Tests use recorded fixtures for external APIs; no live calls in CI.
- iOS: verify the build in the Simulator (`xcodebuild`) after changes.
- Small commits, conventional messages.

## Commands (fill in as they appear)
```
cp .env.example .env                      # once, then fill in CUZK_API_KEY
docker compose up -d --build              # db (Postgres 16 + PostGIS + pg_trgm) + api on :8000
curl localhost:8000/v1/health
cd backend && uv sync                     # deps + Python 3.12 managed by uv
cd backend && uv run pytest
cd backend && uv run ruff check . && uv run ruff format --check .
cd backend && uv run python -m scripts.probe_api_kn   # live API KN probe, writes fixtures
cd backend && uv run alembic upgrade head            # DB schema
cd backend && uv run python -m app.ingest.mf_rent_map          # MF rent map (latest XLSX)
cd backend && uv run python -m app.ingest.ruian_addresses      # RÚIAN addresses (Praha+Brno; --all)
cd backend && uv run python -m app.cli.resolve 21951977 --unit 24 --disposition 2+kk   # M1 chain
cd backend && uv run python -m app.ingest.flood_zones         # VÚV flood zones (~360 MB download)
curl 'localhost:8000/v1/address/suggest?q=u%20krizku'         # API; contract at /openapi.json
cd ios && xcodegen generate && open FerovyNajem.xcodeproj   # .xcodeproj is generated, not committed
cd ios && xcodebuild -project FerovyNajem.xcodeproj -scheme FerovyNajem \
  -destination 'platform=iOS Simulator,name=iPhone 18 Pro' -derivedDataPath build build
# DEBUG deep links for screenshots:
xcrun simctl launch booted cz.ferovynajem.app -screen report -demo red -expand YES -scroll bottom
# add -mock YES to use recorded responses instead of the local backend (Debug → http://localhost:8000)
cd ios && xcodebuild test -project FerovyNajem.xcodeproj -scheme FerovyNajem -destination 'platform=iOS Simulator,name=iPhone 18 Pro'
```
