"""Start the full distributed stack locally (no Docker): data APIs, MCP, every A2A agent, and the backend.

    python -m scripts.run_distributed            # seed a small dataset on first run, then start everything
    python -m scripts.run_distributed --no-seed  # reuse the existing databases
    python -m scripts.run_distributed --banks 1000 --donors 100000   # full-size synthetic data

Agents call each other and the MCP tools over HTTP; the backend (port 8000) forwards requests to the Coordinator.
Ctrl+C stops every process.
"""
from __future__ import annotations

import argparse
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
BACKEND_PORT, MCP_PORT, BANK_PORT, DONOR_PORT = 8000, 8001, 8205, 8206
# One Prometheus scrape port per Python process that records metrics (not shifted by --port-offset).
METRICS_PORTS = {"gateway": 9464, "mcp": 9465, "coordinator": 9470, "requirement": 9471, "matching": 9472, "location": 9473,
                 "notification": 9474, "communication": 9475, "calling": 9476, "pharmacy": 9477, "emergency-priority": 9478}
OTLP_PORT = 4318  # Jaeger's OTLP/HTTP receiver (docker-compose.observability.yml)
AGENTS = {  # A2A_AGENT value -> (port, env-var prefix used for discovery bootstrap)
    "coordinator": 8100, "requirement": 8101, "matching": 8102, "location": 8103, "notification": 8104,
    "communication": 8105, "calling": 8106, "pharmacy": 8107, "emergency-priority": 8108,
}


def prefix(name: str) -> str:
    return name.replace("-", "_").upper() + "AGENT"


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def wait_port(port: int, proc: subprocess.Popen, label: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"{label} exited during startup (code {proc.returncode}). Run it by hand to see the error.")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.3)
    raise SystemExit(f"{label} did not open port {port} within {timeout:.0f}s")


def load_dotenv(path: Path) -> list[str]:
    """Load KEY=VALUE lines from .env into the environment without overriding variables already set."""
    loaded: list[str] = []
    if not path.exists():
        return loaded
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip().strip("'\"")
        if key and key not in os.environ and value:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-seed", action="store_true", help="skip seeding the synthetic data APIs")
    ap.add_argument("--banks", type=int, default=100)
    ap.add_argument("--donors", type=int, default=2000)
    ap.add_argument("--port-offset", type=int, default=0, help="shift every port (e.g. 1000) if the defaults are busy")
    ap.add_argument("--reseed", action="store_true", help="wipe and regenerate the synthetic blood bank / donor data "
                    "(by default existing data is kept, so banks and donors people signed up as survive a restart)")
    ap.add_argument("--no-observability", action="store_true", help="do not record metrics / traces for Grafana, Jaeger, Prometheus")
    ap.add_argument("--llm", default=os.getenv("LLM_PROVIDER", "mock"), help="mock (default) or gemini")
    args = ap.parse_args()

    global BACKEND_PORT, MCP_PORT, BANK_PORT, DONOR_PORT
    off = args.port_offset
    BACKEND_PORT, MCP_PORT, BANK_PORT, DONOR_PORT = BACKEND_PORT + off, MCP_PORT + off, BANK_PORT + off, DONOR_PORT + off
    for key in AGENTS:
        AGENTS[key] += off
    wanted = [BACKEND_PORT, MCP_PORT, BANK_PORT, DONOR_PORT, *AGENTS.values()]
    busy = [port for port in wanted if not port_is_free(port)]
    if busy:
        raise SystemExit(
            f"These ports are already in use: {busy}.\n"
            "Another copy of the app (or Docker) is probably still running. On Windows find it with\n"
            "  netstat -ano | findstr :<port>     then   taskkill /PID <pid> /F\n"
            "or start on shifted ports:  python -m scripts.run_distributed --no-seed --port-offset 1000"
        )

    loaded = load_dotenv(ROOT / ".env")
    if loaded:
        print(f"Loaded from .env: {', '.join(sorted(loaded))}")
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.setdefault("JWT_SECRET_KEY", secrets.token_urlsafe(48))
    env.setdefault("SERVICE_TO_SERVICE_TOKEN", secrets.token_urlsafe(48))
    env.setdefault("A2A_TIMEOUT_SECONDS", "120")   # every agent call opens an MCP session; slow machines need headroom
    env.setdefault("MCP_TIMEOUT_SECONDS", "60")
    if env.get("ORS_API_KEY") and "ROUTING_PROVIDER" not in env:
        env["ROUTING_PROVIDER"] = "ors"
    env.update({
        "ENVIRONMENT": env.get("ENVIRONMENT", "development"),
        "OBSERVABILITY_ENABLED": "false" if args.no_observability else "true",
        "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
        "LLM_PROVIDER": args.llm,
        "A2A_EXECUTION_MODE": "distributed",
        "DATA_APIS_ENABLED": "true",
        "NOTIFICATION_CHANNEL": env.get("NOTIFICATION_CHANNEL", "console"),
        "BLOOD_BANK_DATABASE_URL": f"sqlite:///{(data_dir / 'blood_bank_data.db').as_posix()}",
        "DONOR_DATABASE_URL": f"sqlite:///{(data_dir / 'donor_data.db').as_posix()}",
        "BLOOD_BANK_API_URL": f"http://127.0.0.1:{BANK_PORT}",
        "DONOR_API_URL": f"http://127.0.0.1:{DONOR_PORT}",
        "NOTIFICATION_PUBLIC_BASE_URL": f"http://127.0.0.1:{BANK_PORT}",
        "NOTIFICATION_PUBLIC_DONOR_URL": f"http://127.0.0.1:{DONOR_PORT}",
        "OSM_DISCOVERY_ENABLED": env.get("OSM_DISCOVERY_ENABLED", "true"),
        "HOSPITAL_WEBHOOK_URL": f"http://127.0.0.1:{BACKEND_PORT}/api/v1/internal/response-events",
        "MCP_URL": f"http://127.0.0.1:{MCP_PORT}/mcp",
        "MCP_PORT": str(MCP_PORT),
        "A2A_AGENT_URLS": ",".join(f"http://127.0.0.1:{p}" for p in AGENTS.values()),
    })
    for name, port in AGENTS.items():
        env[f"{prefix(name)}_BASE_URL"] = f"http://127.0.0.1:{port}"

    seed_needed = args.reseed or not ((data_dir / "blood_bank_data.db").exists() and (data_dir / "donor_data.db").exists())
    if not args.no_seed and not seed_needed:
        print("Keeping the existing blood bank / donor data (use --reseed to regenerate it).")
    if not args.no_seed and seed_needed:
        print(f"Seeding synthetic data ({args.banks} blood banks, {args.donors} donors)...")
        subprocess.run([PY, "-m", "scripts.seed_blood_bank_data", "--blood-banks", str(args.banks), "--hospitals", "50",
                        "--inventory-records", str(args.banks * 16), "--historical-requests", "500", "--reset"],
                       cwd=ROOT, env=env, check=True)
        subprocess.run([PY, "-m", "scripts.seed_donor_data", "--donors", str(args.donors), "--donation-records", "1000",
                        "--notification-records", "500", "--blood-bank-count", str(args.banks), "--reset"],
                       cwd=ROOT, env=env, check=True)

    tracing = False
    if not args.no_observability:
        tracing = not port_is_free(OTLP_PORT)
        env["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"http://127.0.0.1:{OTLP_PORT}"
        env["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
        env["OTEL_TRACES_EXPORTER"] = "otlp" if tracing else "none"   # no Jaeger running -> don't spam export errors

    procs: list[tuple[str, subprocess.Popen]] = []

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    def tee(proc: subprocess.Popen, path: Path) -> None:
        """Show a service's output here and also keep it in logs/<service>.log (Grafana reads those files)."""
        with open(path, "w", encoding="utf-8", errors="replace") as log:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write(line)
                log.flush()

    def start(label: str, command: list[str], port: int, extra: dict | None = None, metrics: str | None = None) -> None:
        child_env = {**env, **(extra or {})}
        if metrics and not args.no_observability:
            child_env["OBSERVABILITY_METRICS_PORT"] = str(METRICS_PORTS[metrics])
        proc = subprocess.Popen(command, cwd=ROOT, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=tee, args=(proc, logs_dir / f"{label}.log"), daemon=True).start()
        procs.append((label, proc))
        wait_port(port, proc, label)
        print(f"  up  {label:<22} http://127.0.0.1:{port}")

    def stop(*_: object) -> None:
        print("\nStopping services...")
        for _, proc in reversed(procs):
            if proc.poll() is None:
                proc.terminate()
        for _, proc in procs:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    uvicorn = [PY, "-m", "uvicorn", "--host", "127.0.0.1", "--no-access-log"]
    try:
        print("Starting services...")
        start("blood-bank-data-api", [*uvicorn, "blood_bank_api.main:app", "--port", str(BANK_PORT)], BANK_PORT)
        start("donor-data-api", [*uvicorn, "donor_api.main:app", "--port", str(DONOR_PORT)], DONOR_PORT)
        start("mcp-server", [PY, "-m", "app.mcp.protocol_server"], MCP_PORT, metrics="mcp")
        for name, port in AGENTS.items():
            start(f"{name}-agent", [*uvicorn, "app.agents.a2a.service:create_service", "--factory", "--port", str(port)], port,
                  {"A2A_AGENT": name, f"{prefix(name)}_A2A_URL": f"http://127.0.0.1:{port}/a2a", "OTEL_SERVICE_NAME": f"{name}-agent"}, metrics=name)
        start("backend", [*uvicorn, "app.main:app", "--port", str(BACKEND_PORT)], BACKEND_PORT, {"OTEL_SERVICE_NAME": "gateway"}, metrics="gateway")
        with urllib.request.urlopen(f"http://127.0.0.1:{AGENTS['matching']}/.well-known/agent-card.json", timeout=5) as r:
            assert r.status == 200
        print(f"Places provider: {'Geoapify' if env.get('GEOAPIFY_API_KEY') else 'OpenStreetMap Overpass (set GEOAPIFY_API_KEY for Geoapify)'}"
              f" | Routing: {'OpenRouteService' if env.get('ROUTING_PROVIDER') == 'ors' else 'straight-line estimate (set ORS_API_KEY)'}")
        if args.no_observability:
            print("Monitoring: off (--no-observability)")
        else:
            print("Monitoring: metrics on" + (", traces going to Jaeger" if tracing else
                  " | traces off (start Jaeger first:  docker compose -f docker-compose.observability.yml up -d  then restart this)"))
            print("            Grafana http://localhost:3001   Jaeger http://localhost:16686   Prometheus http://localhost:9090")
        print(f"\nAll services running. API docs: http://127.0.0.1:{BACKEND_PORT}/docs   (Ctrl+C to stop)")
        while True:
            for label, proc in procs:
                if proc.poll() is not None:
                    print(f"{label} stopped unexpectedly (code {proc.returncode}); shutting down.")
                    stop()
            time.sleep(2)
    except SystemExit:
        raise
    except Exception:
        stop()
        raise


if __name__ == "__main__":
    main()
