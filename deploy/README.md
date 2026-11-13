# openl.work deployment

Public entry: https://openl.work/zaowu/ . Existing projects and the original domain home remain unchanged. `/api/v1/` and `/api/health` are reserved for this application.

Build frontend with `VITE_BASE_PATH=/zaowu/ npm run build`. Python 3.11 environment: `/opt/zaowu-engine/venv`; install `backend/requirements.txt`. Native CAD needs libGL/libXrender on Linux. Single Uvicorn process and `GENERATION_WORKERS=1` are used on the shared 2GB host.

Release source and built frontend go in `/opt/zaowu-engine/releases/<commit>`. The `current` symlink selects the active release. Persistent database/files live in `/var/lib/zaowu-engine`, owned by the unprivileged `zaowu` service user. Private provider keys, signing secret and paths are in `/etc/zaowu-engine.env` (root-owned 0600), loaded by systemd, never committed. Set `ADMIN_EMAILS` to the owner's real account; disable the default admin registration in public deployment by leaving this variable empty until assigned.

Install `zaowu.service` in `/etc/systemd/system/`, enable/start it. Add `nginx-locations.conf` inside the existing HTTPS server, then run `nginx -t` before reloading. Preserve a dated backup before editing existing configuration. Existing HTTPS certificate is reused.

Check `systemctl status zaowu`, `journalctl -u zaowu`, `/api/health`, the SPA entry and deep links. Verify native STEP generation and API auth after release. Provider billing requires real calls; offline tests alone do not verify vendor availability.

Rollback: point `current` to the previous release and restart `zaowu`; database schema is unchanged by this release. For first-install rollback, stop/disable `zaowu`, remove only its added Nginx include, validate/reload Nginx. Preserve `/var/lib/zaowu-engine` and private configuration. Do not remove other projects or shared Nginx configuration.
