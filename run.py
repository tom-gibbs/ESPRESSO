# run.py (ownership enforced + ?force=1 takes ownership; atomic writes; no-store)
# FIXED: accept both client/server schema variants (projects_order/projects_order vs projectOrder/projectOrder)
# FIXED: robust migration + never "wipe" due to key mismatch
#
# Canonical on disk: {"meta":..., "projects_order":[...], "projects":{pid:{name, active, paused, done_today, done_week, meta_done}}}
# API responses ALSO include "projectOrder" for client compatibility.
# API accepts payloads that contain either:
#   - projects_order + projects
#   - projectOrder + projects
#   - legacy work/personal sections
#
import json
import os
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
import threading
import webbrowser
from urllib.parse import urlparse, parse_qs
import shutil

print("=== RUN.PY STARTING ===")

PORT = 8000
STATE_FILE = Path("state.json")
BACKUP_FILE = Path("state.bak.json")

print(f"PORT: {PORT}")
print(f"STATE_FILE: {STATE_FILE}")

def _default_section():
    return {
        "active": [],
        "paused": [],
        "done_today": [],
        "done_week": [],
        "meta_done": {"day_start_ms": 0, "week_start_ms": 0},
    }

def default_payload():
    return {
        "meta": {"rev": 0, "owner": None, "owner_updated_unix": 0},
        "projects_order": ["work", "personal"],
        "projects": {
            "work": {"name": "WORK", **_default_section()},
            "personal": {"name": "PERSONAL", **_default_section()},
        },
    }

def _is_valid_section(sec: dict) -> bool:
    if not isinstance(sec, dict):
        return False
    for k in ("active", "paused", "done_today", "done_week"):
        if k not in sec or not isinstance(sec[k], list):
            return False
    if "meta_done" not in sec or not isinstance(sec["meta_done"], dict):
        return False
    return True

def _is_valid_projects_payload(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if "meta" not in payload or not isinstance(payload["meta"], dict):
        return False
    if "rev" not in payload["meta"]:
        return False
    if "projects" not in payload or not isinstance(payload["projects"], dict):
        return False
    if "projects_order" not in payload or not isinstance(payload["projects_order"], list):
        return False
    for pid, p in payload["projects"].items():
        if not isinstance(pid, str) or not pid:
            return False
        if not isinstance(p, dict):
            return False
        if "name" not in p:
            return False
        if not _is_valid_section(p):
            return False
    return True

def _is_valid_legacy_payload(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if "meta" not in payload or not isinstance(payload["meta"], dict):
        return False
    if "rev" not in payload["meta"]:
        return False
    for section in ("work", "personal"):
        if section not in payload or not isinstance(payload[section], dict):
            return False
        sec = payload[section]
        for k in ("active", "paused", "done_today", "done_week"):
            if k not in sec or not isinstance(sec[k], list):
                return False
        if "meta_done" not in sec or not isinstance(sec["meta_done"], dict):
            return False
    return True

def load_json_file(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def load_state():
    raw = load_json_file(STATE_FILE)
    if raw is not None:
        return raw
    raw_bak = load_json_file(BACKUP_FILE)
    if raw_bak is not None:
        return raw_bak
    return default_payload()

def normalize_section(sec: dict) -> dict:
    sec = sec if isinstance(sec, dict) else {}
    done_old = sec.get("done", []) if isinstance(sec.get("done"), list) else []
    out = {
        "active": sec.get("active", []) if isinstance(sec.get("active"), list) else [],
        "paused": sec.get("paused", []) if isinstance(sec.get("paused"), list) else [],
        "done_today": sec.get("done_today", []) if isinstance(sec.get("done_today"), list) else [],
        "done_week": sec.get("done_week", []) if isinstance(sec.get("done_week"), list) else [],
        "meta_done": sec.get("meta_done", {}) if isinstance(sec.get("meta_done"), dict) else {},
    }
    if done_old and not out["done_today"] and not out["done_week"]:
        out["done_today"] = done_old
        out["done_week"] = done_old
    out["meta_done"].setdefault("day_start_ms", 0)
    out["meta_done"].setdefault("week_start_ms", 0)
    return out

def migrate_legacy_to_projects(payload: dict) -> dict:
    work = normalize_section(payload.get("work", {}))
    personal = normalize_section(payload.get("personal", {}))
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    out = {
        "meta": {
            "rev": int(meta.get("rev", 0) or 0),
            "owner": meta.get("owner", None),
            "owner_updated_unix": int(meta.get("owner_updated_unix", 0) or 0),
        },
        "projects_order": ["work", "personal"],
        "projects": {
            "work": {"name": "WORK", **work},
            "personal": {"name": "PERSONAL", **personal},
        },
    }
    return out

def normalize_state(payload: dict):
    """
    Returns canonical "projects" payload.
    Also accepts client variant keys: projectOrder (instead of projects_order)
    """
    if not isinstance(payload, dict):
        return default_payload()

    # Accept client key name for order
    if "projects_order" not in payload and "projectOrder" in payload and isinstance(payload["projectOrder"], list):
        payload["projects_order"] = payload["projectOrder"]

    # Very old: {work, personal} but missing meta
    if "work" in payload and "personal" in payload and "meta" not in payload and "projects" not in payload:
        payload = {
            "meta": {"rev": 0, "owner": None, "owner_updated_unix": 0},
            "work": payload.get("work", {}),
            "personal": payload.get("personal", {}),
        }

    # Very old: {active, paused, done}
    if all(k in payload for k in ("active", "paused", "done")) and "projects" not in payload:
        payload = {
            "meta": {"rev": 0, "owner": None, "owner_updated_unix": 0},
            "work": {
                "active": payload.get("active", []),
                "paused": payload.get("paused", []),
                "done": payload.get("done", []),
            },
            "personal": {"active": [], "paused": [], "done": []},
        }

    # New-ish format (projects)
    if "projects" in payload and isinstance(payload.get("projects"), dict):
        if "meta" not in payload or not isinstance(payload["meta"], dict):
            payload["meta"] = {"rev": 0, "owner": None, "owner_updated_unix": 0}
        payload["meta"].setdefault("rev", 0)
        payload["meta"].setdefault("owner", None)
        payload["meta"].setdefault("owner_updated_unix", 0)

        projects = payload.get("projects", {})
        out_projects = {}
        for pid, proj in projects.items():
            if not isinstance(pid, str) or not pid:
                continue
            proj = proj if isinstance(proj, dict) else {}
            # client may include "name" and also "id"; pid is authoritative
            name = proj.get("name", pid)
            if not isinstance(name, str):
                name = pid
            name = name.strip() or pid
            sec = normalize_section(proj)
            out_projects[pid] = {"name": name, **sec}

        order = payload.get("projects_order", [])
        if not isinstance(order, list):
            order = []
        # keep only existing
        order = [x for x in order if isinstance(x, str) and x in out_projects]
        # append any missing
        for pid in out_projects.keys():
            if pid not in order:
                order.append(pid)

        # Ensure at least work/personal exist
        for pid, nm in (("work", "WORK"), ("personal", "PERSONAL")):
            if pid not in out_projects:
                out_projects[pid] = {"name": nm, **_default_section()}
            if pid not in order:
                order.append(pid)

        out = {
            "meta": {
                "rev": int(payload["meta"].get("rev", 0) or 0),
                "owner": payload["meta"].get("owner", None),
                "owner_updated_unix": int(payload["meta"].get("owner_updated_unix", 0) or 0),
            },
            "projects_order": order,
            "projects": out_projects,
        }
        if not _is_valid_projects_payload(out):
            return default_payload()
        return out

    # Legacy -> migrate
    legacy = {
        "meta": payload.get("meta", {"rev": 0, "owner": None, "owner_updated_unix": 0}),
        "work": normalize_section(payload.get("work", {})),
        "personal": normalize_section(payload.get("personal", {})),
    }
    if not _is_valid_legacy_payload(legacy):
        return default_payload()
    migrated = migrate_legacy_to_projects(legacy)
    if not _is_valid_projects_payload(migrated):
        return default_payload()
    return migrated

def with_client_compat(payload: dict) -> dict:
    """
    Server canonical keys: projects_order
    Client expects: projectOrder
    Return payload that includes BOTH (same list).
    """
    p = normalize_state(payload)
    out = dict(p)
    out["projectOrder"] = list(p.get("projects_order", []))
    return out

def count_items(payload: dict) -> int:
    try:
        p = normalize_state(payload)
        total = 0
        for pid, sec in p.get("projects", {}).items():
            total += len(sec.get("active", []))
            total += len(sec.get("paused", []))
            total += len(sec.get("done_today", []))
            total += len(sec.get("done_week", []))
        return total
    except Exception:
        return 0

def atomic_write_json(path: Path, obj: dict):
    try:
        if path.exists():
            shutil.copy2(path, BACKUP_FILE)
    except Exception:
        pass
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

class Handler(SimpleHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict, no_store: bool = False):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if no_store:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(data)

    def _parse_qs(self):
        u = urlparse(self.path)
        return u, parse_qs(u.query or "")

    def _parse_force(self) -> bool:
        _, qs = self._parse_qs()
        return qs.get("force", ["0"])[0] in ("1", "true", "yes", "on")

    def _parse_allow_empty(self) -> bool:
        _, qs = self._parse_qs()
        return qs.get("allow_empty", ["0"])[0] in ("1", "true", "yes", "on")

    # Security: only serve specific files, not the entire directory
    ALLOWED_FILES = {"/", "/index.html", "/espresso-icon.png"}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/state":
            payload = with_client_compat(load_state())
            return self._send_json(200, payload, no_store=True)
        # Restrict static file serving to allowed files only
        path = u.path if u.path != "/" else "/index.html"
        if path not in self.ALLOWED_FILES:
            self.send_error(404, "Not Found")
            return
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/state":
            return self._send_json(404, {"ok": False, "error": "Not found"}, no_store=True)

        force = self._parse_force()
        allow_empty = self._parse_allow_empty()

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            incoming_raw = json.loads(body) if body else {}
            incoming = normalize_state(incoming_raw)
            current = normalize_state(load_state())
            now = int(time.time())

            incoming_n = count_items(incoming)
            current_n = count_items(current)

            if force and (incoming_n == 0) and (current_n > 0) and not allow_empty:
                return self._send_json(
                    409,
                    {
                        "ok": False,
                        "error": "Refusing to overwrite non-empty state with an empty payload (force save safety). Refresh/reload first, or use allow_empty=1 if you really intend to wipe.",
                        "incoming_count": incoming_n,
                        "current_count": current_n,
                    },
                    no_store=True,
                )

            incoming_owner = incoming["meta"].get("owner")
            current_owner = current["meta"].get("owner")

            if current_owner is None and incoming_owner is not None:
                current_owner = incoming_owner
                current["meta"]["owner"] = incoming_owner
                current["meta"]["owner_updated_unix"] = now

            if current_owner is not None and (incoming_owner != current_owner) and not force:
                return self._send_json(
                    409,
                    {
                        "ok": False,
                        "error": "Owner mismatch. Use Force save to take ownership.",
                        "current_owner": current_owner,
                        "incoming_owner": incoming_owner,
                        "owner_updated_unix": current["meta"].get("owner_updated_unix", 0),
                        "rev": current["meta"].get("rev", 0),
                    },
                    no_store=True,
                )

            if force and incoming_owner is not None:
                incoming["meta"]["owner"] = incoming_owner
                incoming["meta"]["owner_updated_unix"] = now
            else:
                incoming["meta"]["owner"] = current_owner
                incoming["meta"]["owner_updated_unix"] = int(current["meta"].get("owner_updated_unix", 0) or 0)

            incoming_rev = int(incoming["meta"].get("rev", 0) or 0)
            current_rev = int(current["meta"].get("rev", 0) or 0)
            incoming["meta"]["rev"] = max(incoming_rev, current_rev) + 1

            atomic_write_json(STATE_FILE, incoming)

            return self._send_json(
                200,
                {
                    "ok": True,
                    "saved_at_unix": now,
                    "bytes": STATE_FILE.stat().st_size,
                    "owner": incoming["meta"]["owner"],
                    "rev": incoming["meta"]["rev"],
                },
                no_store=True,
            )
        except Exception as e:
            return self._send_json(400, {"ok": False, "error": str(e)}, no_store=True)

def open_browser():
    webbrowser.open(f"http://localhost:{PORT}/index.html")

if __name__ == "__main__":
    print("Starting server setup...")
    threading.Timer(0.6, open_browser).start()
    server = HTTPServer(("localhost", PORT), Handler)
    print(f"Serving on http://localhost:{PORT}/index.html")
    print("API: GET/POST http://localhost:8000/api/state (saved to state.json)")
    print("Ownership enforced. Use POST /api/state?force=1 to take ownership.")
    print("Force-save safety: won't overwrite non-empty state with empty payload unless allow_empty=1.")
    print("Press Ctrl+C to stop.")
    server.serve_forever()