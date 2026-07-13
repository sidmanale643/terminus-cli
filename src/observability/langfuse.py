import atexit
import importlib.util
import os
import ssl
from dotenv import load_dotenv

load_dotenv()

_langfuse_client = None


def is_available() -> bool:
    """Return whether the optional Langfuse SDK is installed."""
    return importlib.util.find_spec("langfuse") is not None

def _should_verify_ssl() -> bool:
    """Return True unless LANGFUSE_VERIFY_SSL is explicitly set to 'false'."""
    return os.environ.get("LANGFUSE_VERIFY_SSL", "true").lower() != "false"


def _get_ssl_context() -> ssl.SSLContext | None:
    """Return an SSL context respecting LANGFUSE_VERIFY_SSL."""
    if _should_verify_ssl():
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def get_langfuse_client():
    """Get or create the Langfuse client.

    Returns None if credentials are not configured.
    Import langfuse ONLY after env vars are loaded to avoid init with missing keys.
    """
    global _langfuse_client

    if _langfuse_client is not None:
        return _langfuse_client

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    if not public_key or not secret_key or not is_available():
        return None

    try:
        from langfuse import Langfuse
    except ImportError:
        return None

    kwargs = dict(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )

    if not _should_verify_ssl():
        kwargs["httpx_client"] = None

    try:
        _langfuse_client = Langfuse(**kwargs)
    except Exception:
        # Observability must never prevent the CLI from starting or running.
        return None
    return _langfuse_client


def is_enabled():
    """Check if the optional SDK is installed and tracing is configured."""
    return bool(
        is_available()
        and os.environ.get("LANGFUSE_PUBLIC_KEY")
        and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def flush():
    """Flush pending events to Langfuse. Call before process exit."""
    client = get_langfuse_client()
    if client:
        try:
            client.flush()
        except Exception as e:
            import sys
            print(f"[Langfuse] Flush failed: {e}", file=sys.stderr)


# Ensure any queued events are flushed when the interpreter exits normally.
atexit.register(flush)


def test_connection(timeout: int = 10) -> tuple[bool, str]:
    """Verify Langfuse credentials and connectivity.

    Returns (ok, message).  If ok is False, message explains why.
    """
    if not is_enabled():
        return False, "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are not set."

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    try:
        import urllib.request
        import json
        import base64

        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        req = urllib.request.Request(
            f"{host.rstrip('/')}/api/public/projects",
            headers={"Authorization": f"Basic {auth}"},
        )
        ctx = _get_ssl_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode())
            projects = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(projects, list) and len(projects) > 0:
                proj_names = [p.get("name", "unknown") for p in projects]
                return True, f"Connected to Langfuse ({host}). Projects: {', '.join(proj_names)}."
            return True, f"Connected to Langfuse ({host}), but no projects found."
    except Exception as e:
        return False, f"Cannot reach Langfuse at {host}: {type(e).__name__}: {e}"


def observe(name=None, as_type=None):
    """Decorator to instrument a function as a Langfuse trace/span/generation.

    Falls back to a no-op decorator if Langfuse is not configured.
    """
    if not is_enabled():
        def noop_decorator(fn):
            return fn
        return noop_decorator

    try:
        from langfuse.decorators import observe as _observe
    except ImportError:
        def noop_decorator(fn):
            return fn
        return noop_decorator
    return _observe(name=name, as_type=as_type)
