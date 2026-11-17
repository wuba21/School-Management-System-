"""
scripts/serve_lan.py
====================
Step 25: Waitress WSGI production server launcher for LAN deployment.

USAGE:
  python scripts/serve_lan.py [--host HOST] [--port PORT] [--threads N]

DEFAULTS:
  --host    0.0.0.0        (listen on all LAN interfaces)
  --port    8000
  --threads 8

EXAMPLES:
  python scripts/serve_lan.py
  python scripts/serve_lan.py --port 80 --threads 12
  python scripts/serve_lan.py --host 192.168.1.100 --port 8080

WHAT THIS DOES:
  1. Validates the .env configuration before starting.
  2. Collects static files automatically (collectstatic).
  3. Runs pending database migrations.
  4. Starts the Waitress WSGI server on the LAN.

Metti Secondary School — Offline LAN Deployment
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# ---------------------------------------------------------------------------
# Parse command-line arguments
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description='SSMS LAN Production Server (Waitress WSGI)',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
  python scripts/serve_lan.py                        # Default: 0.0.0.0:8000
  python scripts/serve_lan.py --port 80              # Listen on port 80
  python scripts/serve_lan.py --host 192.168.1.100   # Bind to specific LAN IP
""",
)
parser.add_argument('--host', default='0.0.0.0', help='IP address to bind to (default: 0.0.0.0)')
parser.add_argument('--port', default=8000, type=int, help='Port number (default: 8000)')
parser.add_argument('--threads', default=8, type=int, help='Number of Waitress worker threads (default: 8)')
parser.add_argument('--skip-checks', action='store_true', help='Skip pre-flight checks (not recommended)')
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_production')

PYTHON = sys.executable
MANAGE = str(BASE_DIR / 'manage.py')

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------
GREEN  = '\033[92m'
YELLOW = '\033[93m'
RED    = '\033[91m'
CYAN   = '\033[96m'
RESET  = '\033[0m'
BOLD   = '\033[1m'

def info(msg):   print(f"{CYAN}[INFO]{RESET}  {msg}")
def ok(msg):     print(f"{GREEN}[OK]{RESET}    {msg}")
def warn(msg):   print(f"{YELLOW}[WARN]{RESET}  {msg}")
def error(msg):  print(f"{RED}[ERROR]{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{CYAN}{msg}{RESET}")


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
def run_preflight():
    header("=" * 60)
    header("  SSMS Production Server — Metti Secondary School")
    header("=" * 60)

    # 1. Check .env file
    env_file = BASE_DIR / '.env'
    if not env_file.exists():
        error(f".env file not found at {env_file}")
        error("Copy .env.example to .env and configure your settings.")
        sys.exit(1)
    ok(".env file found")

    # 2. Check SECRET_KEY is not the default insecure key
    from dotenv import dotenv_values
    env_vars = dotenv_values(env_file)
    secret = env_vars.get('SECRET_KEY', '')
    if 'django-insecure' in secret or not secret:
        warn("SECRET_KEY is insecure or missing.")
        warn("Generate a new key: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\"")
        warn("Then update SECRET_KEY in your .env file.")
    else:
        ok("SECRET_KEY is set to a custom value")

    # 3. Check LAN_SERVER_IP is configured
    lan_ip = env_vars.get('LAN_SERVER_IP', '')
    if not lan_ip:
        warn("LAN_SERVER_IP not set in .env — defaulting to 192.168.1.100 in ALLOWED_HOSTS")
        warn("Add: LAN_SERVER_IP=<your-server-ip> to .env")
    else:
        ok(f"LAN_SERVER_IP = {lan_ip}")

    # 4. Run Django system check
    info("Running Django system check...")
    result = subprocess.run(
        [PYTHON, MANAGE, 'check', '--deploy', '--settings=config.settings_production'],
        capture_output=True, text=True
    )
    if result.returncode != 0 and 'silenced' not in result.stdout:
        # Only fail on actual errors, not security warnings for HTTP-only LAN
        output = result.stdout + result.stderr
        serious_errors = [line for line in output.splitlines()
                         if 'SystemCheckError' in line or ': (E' in line]
        if serious_errors:
            error("Django system check found critical errors:")
            for line in serious_errors:
                error(f"  {line}")
            sys.exit(1)
    ok("Django system check passed")

    # 5. Collect static files
    info("Collecting static files...")
    result = subprocess.run(
        [PYTHON, MANAGE, 'collectstatic', '--noinput',
         '--settings=config.settings_production'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        error("collectstatic failed:")
        error(result.stderr)
        sys.exit(1)
    ok("Static files collected")

    # 6. Run migrations
    info("Applying database migrations...")
    result = subprocess.run(
        [PYTHON, MANAGE, 'migrate', '--settings=config.settings_production'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        error("Database migration failed:")
        error(result.stderr)
        sys.exit(1)
    ok("Database migrations applied")

    # 7. Create logs directory
    log_dir = BASE_DIR / 'logs'
    log_dir.mkdir(exist_ok=True)
    ok(f"Log directory ready: {log_dir}")

    # 8. Create backups directory
    backup_dir = BASE_DIR / 'backups'
    backup_dir.mkdir(exist_ok=True)
    (backup_dir / 'database').mkdir(exist_ok=True)
    (backup_dir / 'media').mkdir(exist_ok=True)
    ok(f"Backup directory ready: {backup_dir}")


# ---------------------------------------------------------------------------
# Launch Waitress
# ---------------------------------------------------------------------------
def serve():
    if not args.skip_checks:
        run_preflight()

    header("\n  Starting Waitress WSGI Server...")
    info(f"  Binding to:    {args.host}:{args.port}")
    info(f"  Worker threads: {args.threads}")
    info(f"  Settings:      config.settings_production")
    info(f"  LAN URL:       http://<server-ip>:{args.port}/")
    print()

    try:
        import waitress
        from django.core.wsgi import get_wsgi_application

        application = get_wsgi_application()

        ok(f"SSMS is now running. Access it from any computer on the school LAN:")
        ok(f"  http://{args.host if args.host != '0.0.0.0' else '<server-ip>'}:{args.port}/")
        print(f"\n{YELLOW}Press Ctrl+C to stop the server.{RESET}\n")

        waitress.serve(
            application,
            host=args.host,
            port=args.port,
            threads=args.threads,
            channel_timeout=120,
            cleanup_interval=30,
            connection_limit=200,
            # Log format for Waitress access log
            ident='SSMS/Waitress',
        )
    except ImportError:
        error("Waitress is not installed.")
        error("Run: pip install waitress")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Server stopped by administrator.{RESET}")
        sys.exit(0)
    except Exception as e:
        error(f"Server error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    serve()
