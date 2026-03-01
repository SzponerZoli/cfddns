from __future__ import annotations

import secrets
import threading
import time
import uuid
import os
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from cfddns.cloudflare_ddns import CloudflareDDNS, UpdateResult
from cfddns.config_store import AppData, ConfigStore, ProfileConfig


app = Flask(__name__)
app.secret_key = os.getenv("CFDDNS_SECRET_KEY", secrets.token_hex(32))
store = ConfigStore()
scheduler_lock = threading.Lock()
scheduler_started = False

state_lock = threading.Lock()
app_state = {
    "profile_states": {},
    "logs": [],
}


def add_log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {message}"
    with state_lock:
        app_state["logs"].insert(0, line)
        app_state["logs"] = app_state["logs"][:200]


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped


def _default_profile_state() -> dict:
    return {
        "last_run": None,
        "last_result": "Not run yet",
        "last_success": None,
        "last_changed_records": 0,
        "last_ip": None,
    }


def get_profile_state(profile_id: str) -> dict:
    with state_lock:
        if profile_id not in app_state["profile_states"]:
            app_state["profile_states"][profile_id] = _default_profile_state()
        return dict(app_state["profile_states"][profile_id])


def run_update(profile: ProfileConfig) -> UpdateResult:
    updater = CloudflareDDNS(profile.api_token, profile.zone_id)
    record_names = [name.strip() for name in profile.record_names_csv.split(",") if name.strip()]
    result = updater.update_records(
        record_names=record_names,
        record_type=profile.record_type,
        ttl=profile.ttl,
        proxied=profile.proxied,
    )

    with state_lock:
        if profile.id not in app_state["profile_states"]:
            app_state["profile_states"][profile.id] = _default_profile_state()
        profile_state = app_state["profile_states"][profile.id]
        profile_state["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        profile_state["last_result"] = result.message
        profile_state["last_success"] = result.success
        profile_state["last_changed_records"] = result.changed_records
        profile_state["last_ip"] = result.current_ip

    status = "OK" if result.success else "ERROR"
    add_log(f"{status} [{profile.name}]: {result.message} (ip={result.current_ip or 'n/a'})")
    return result


def scheduler_loop() -> None:
    due_by_profile: dict[str, float] = {}

    while True:
        now = time.time()
        data = store.load()

        for profile in data.profiles:
            if profile.id not in due_by_profile:
                due_by_profile[profile.id] = now
            if profile.enabled and now >= due_by_profile[profile.id]:
                run_update(profile)
                due_by_profile[profile.id] = now + max(30, int(profile.interval_seconds or 300))

        existing_ids = {profile.id for profile in data.profiles}
        for profile_id in list(due_by_profile.keys()):
            if profile_id not in existing_ids:
                del due_by_profile[profile_id]

        time.sleep(5)


def start_scheduler_once() -> None:
    global scheduler_started
    with scheduler_lock:
        if scheduler_started:
            return
        thread = threading.Thread(target=scheduler_loop, daemon=True)
        thread.start()
        scheduler_started = True


def _find_selected_profile(data: AppData) -> ProfileConfig:
    selected_id = data.selected_profile_id
    for profile in data.profiles:
        if profile.id == selected_id:
            return profile
    data.selected_profile_id = data.profiles[0].id
    store.save(data)
    return data.profiles[0]


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        data = store.load()
        if username == data.auth.username and check_password_hash(data.auth.password_hash, password):
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Invalid credentials"

    return render_template("login.html", error=error)


@app.get("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
@login_required
def index():
    data = store.load()
    selected_profile_id = request.args.get("profile_id", "").strip()
    if selected_profile_id and selected_profile_id in {p.id for p in data.profiles}:
        data.selected_profile_id = selected_profile_id
        store.save(data)

    selected_profile = _find_selected_profile(data)
    with state_lock:
        logs_snapshot = list(app_state["logs"])
    return render_template(
        "index.html",
        data=data,
        selected_profile=selected_profile,
        selected_state=get_profile_state(selected_profile.id),
        logs=logs_snapshot,
    )


@app.post("/profile/save")
@login_required
def save_profile():
    data = store.load()
    form = request.form
    profile_id = form.get("profile_id", "").strip()

    target = None
    for profile in data.profiles:
        if profile.id == profile_id:
            target = profile
            break

    if target is None:
        target = ProfileConfig(id=uuid.uuid4().hex)
        data.profiles.append(target)

    target.name = form.get("name", "").strip() or "Unnamed"
    target.api_token = form.get("api_token", "").strip()
    target.zone_id = form.get("zone_id", "").strip()
    target.record_type = form.get("record_type", "A").strip().upper()
    target.record_names_csv = form.get("record_names_csv", "").strip()
    target.ttl = int(form.get("ttl", "1") or 1)
    target.proxied = form.get("proxied") == "on"
    target.interval_seconds = max(30, int(form.get("interval_seconds", "300") or 300))
    target.enabled = form.get("enabled") == "on"

    data.selected_profile_id = target.id
    store.save(data)
    add_log(f"Profile saved: {target.name}")
    return redirect(url_for("index"))


@app.post("/profile/new")
@login_required
def new_profile():
    data = store.load()
    profile = ProfileConfig(id=uuid.uuid4().hex, name="New Profile")
    data.profiles.append(profile)
    data.selected_profile_id = profile.id
    store.save(data)
    add_log("New profile created")
    return redirect(url_for("index", profile_id=profile.id))


@app.post("/profile/delete")
@login_required
def delete_profile():
    data = store.load()
    profile_id = request.form.get("profile_id", "").strip()
    if len(data.profiles) <= 1:
        add_log("Delete blocked: at least one profile must remain")
        return redirect(url_for("index"))

    remaining = [profile for profile in data.profiles if profile.id != profile_id]
    if len(remaining) == len(data.profiles):
        return redirect(url_for("index"))

    data.profiles = remaining
    if data.selected_profile_id == profile_id:
        data.selected_profile_id = data.profiles[0].id
    store.save(data)
    add_log("Profile deleted")
    return redirect(url_for("index"))


@app.post("/profile/run-now")
@login_required
def run_now():
    data = store.load()
    profile_id = request.form.get("profile_id", "").strip()
    profile = next((item for item in data.profiles if item.id == profile_id), None)
    if profile:
        run_update(profile)
    return redirect(url_for("index", profile_id=profile_id))


@app.post("/auth/change")
@login_required
def change_auth():
    data = store.load()
    current_password = request.form.get("current_password", "")
    new_username = request.form.get("new_username", "").strip()
    new_password = request.form.get("new_password", "")

    if not check_password_hash(data.auth.password_hash, current_password):
        add_log("Auth change failed: current password mismatch")
        return redirect(url_for("index"))

    if new_username:
        data.auth.username = new_username
    if new_password:
        data.auth.password_hash = generate_password_hash(new_password)

    store.save(data)
    add_log("Authentication settings updated")
    return redirect(url_for("index"))


if __name__ == "__main__":
    start_scheduler_once()
    app.run(host="0.0.0.0", port=8080, debug=False)
