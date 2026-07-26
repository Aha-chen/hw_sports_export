# Huawei Health Export to Strava TCX

English | [中文](README.md)

Convert encrypted Huawei Health export archives into Strava-compatible TCX files. The project runs locally by default, preserves GPS tracks, heart rate, cadence, elevation, and lap data, and optionally supports direct uploads through Strava OAuth.

> This is an independent open-source project and is not affiliated with or endorsed by Huawei or Strava.

## Screenshots

![Upload page](docs/images/upload-page.png)

![Results page](docs/images/result-page.png)

## Features

- Reads AES-encrypted ZIP archives exported from the Huawei Privacy Center, up to 2 GB per upload
- Converts GCJ-02 coordinates used in mainland China to WGS-84 to reduce track offsets in Strava
- Generates TCX activities with heart rate, cadence, elevation, distance, and calorie data
- Uses Huawei manual lap data when available and falls back to automatic one-kilometre laps
- Calibrates track distance against the total recorded by the device to reduce cross-platform differences
- Supports outdoor running, cycling, walking, and indoor activities without GPS data
- Includes sport filtering, activity details, and heart-rate and pace previews
- Optionally uploads selected activities directly to Strava through OAuth
- Bundles frontend dependencies locally, so the basic conversion workflow does not require an external CDN

## Privacy and security

By default, uploaded archives, generated files, and task state remain on the machine running the application. Temporary task directories are removed automatically after a retention period, which defaults to one hour after completion.

When direct Strava upload is enabled, only TCX files explicitly selected by the user are sent to Strava. OAuth tokens are stored in a local SQLite database rather than browser storage.

The upload endpoint checks the number of ZIP entries, individual uncompressed sizes, and estimated total expansion size to reduce resource risks from malformed archives. This project is intended primarily for local or trusted-network use. It does not include a complete public multi-tenant authentication, quota, or rate-limiting layer; add these controls at a reverse proxy or gateway before exposing it to the internet.

## Quick start

### Requirements

- Python 3.11 or later
- pip

### Local installation

```bash
git clone https://github.com/Aha-chen/hw_sports_export.git
cd hw_sports_export

python -m venv venv
source venv/bin/activate  # macOS / Linux
# venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

Start the API server:

```bash
python -m uvicorn app:app --reload --port 8000
```

In a second terminal, start the parser worker:

```bash
source venv/bin/activate  # Use venv\Scripts\activate on Windows
python worker.py
```

Open `http://127.0.0.1:8000`.

### Docker Compose

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated value into `SESSION_SECRET_KEY` in `.env`, then start the services:

```bash
docker compose up -d
```

Keep `COOKIE_SECURE=0` for local HTTP use. Set it to `1` when deploying over HTTPS.

## Usage

1. Request a Huawei Health export from the [Huawei Privacy Center](https://privacy.consumer.huawei.com/tool).
2. Download the resulting ZIP archive and keep the extraction password supplied by Huawei.
3. Upload the ZIP file, enter the password, and optionally choose a date range.
4. Wait for processing to finish, then review activity types, distances, and data previews.
5. Download the generated TCX archive and import it from the [Strava upload page](https://www.strava.com/upload/select), or configure OAuth for direct upload.

## Direct Strava upload (optional)

1. Create an application in [Strava API settings](https://www.strava.com/settings/api).
2. Select `Data Importer` as the application category and use `localhost` as the Callback Domain for local development.
3. Copy `.env.example` to `.env` and configure:

```env
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
SESSION_SECRET_KEY=your_random_session_secret
STRAVA_REDIRECT_URI=http://localhost:8000/api/strava/callback
```

4. Restart the API server. The connection option appears when the configuration is valid.

Production deployments should use a fixed HTTPS callback URL and set `COOKIE_SECURE=1`.

## Project structure

| Path | Purpose |
| --- | --- |
| `app.py` | FastAPI application, upload validation, task event stream, and downloads |
| `worker.py` | Independent parser worker and interrupted-task recovery |
| `core/parser.py` | Huawei data parsing, coordinate conversion, and TCX generation |
| `core/task_store.py` | SQLite-backed task queue and state persistence |
| `core/strava_store.py` | Server-side storage for Strava OAuth tokens |
| `routers/strava.py` | Strava OAuth and activity upload endpoints |
| `templates/`, `static/` | Web interface and bundled frontend assets |
| `tests/` | Parser, task queue, and API tests |

The API and worker coordinate through `temp/tasks.sqlite3`, with files stored under each task directory. Docker Compose starts one API container and one worker container sharing the `temp` volume.

## Development and validation

```bash
pip install -r requirements-dev.txt
pytest -q
```

The service health endpoint is `GET /healthz`.

The current storage design targets a single-host deployment. For multiple nodes or workers, move task state and temporary files to a shared database and object store, then revisit task leases, concurrency, and cleanup behaviour.

## Known limitations

- Huawei may change its export schema; unsupported variants require updates based on representative samples.
- Indoor activities without real GPS data use a synthetic track derived from pace or timing data for TCX compatibility.
- Metrics may vary slightly across devices, sport types, and Strava import behaviour.

## Contributing

Issues with reproducible details and focused pull requests are welcome. For parser compatibility reports, describe the device model, sport type, and anonymised data structure where possible. Do not publish real health data or account credentials.

## License

This project is available under the [MIT License](LICENSE).

## Development note

AI coding tools were used during development to assist with code generation, refactoring, and testing. Functionality should still be validated through the project test suite and representative export data.
