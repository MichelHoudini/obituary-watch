"""
observability.py — structured logging + optional Sentry, shared by every
entry point (app.main, app.watcher, app.milestones).

Both are fail-safe by design, matching this project's existing pattern for
optional integrations (see ANALYTICS_HEAD_SNIPPET in app/main.py):
- setup_logging() always runs, no config needed, just switches the log
  format from plain text to JSON lines.
- setup_sentry() only does anything if SENTRY_DSN is set. Unset means
  exactly today's behavior: no Sentry, no crash, no extra dependency
  actually contacting anything over the network.
"""
import json
import logging
import os
import sys

# LogRecord attributes that always exist -- excluded when picking up
# caller-supplied `extra={...}` fields, so we don't dump logging's own
# internals (pathname, thread ids, etc.) into every line.
_RESERVED_LOG_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS:
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """Replace whatever logging config exists with JSON-lines output on
    stdout. Safe to call multiple times (e.g. once per entry point) --
    always resets to a single handler rather than stacking duplicates."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def setup_sentry(component: str) -> None:
    """Initialize Sentry if SENTRY_DSN is set; otherwise a complete no-op.
    `component` (e.g. "web", "watcher", "milestones") is tagged on every
    event so errors from the three separate entry points are
    distinguishable in Sentry, since they run as entirely separate
    processes (Render web service vs. two different GitHub Actions jobs)."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.1,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
    )
    sentry_sdk.set_tag("component", component)
