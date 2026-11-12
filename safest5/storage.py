"""Read data from the NRL repo and read/write this site's picks log on GitHub.

Config lives in Streamlit secrets (or environment variables):

    [github]
    token = "github_pat_..."              # needs Contents: read on Nrl-match-data,
                                          # read and write on safest-5-picks
    data_repo  = "johnpaullichaa-source/Nrl-match-data"   # optional
    data_branch = "main"                                   # optional
    site_repo  = "johnpaullichaa-source/safest-5-picks"    # optional
    site_branch = "main"                                   # optional

Without a token, files are read from a local ./data folder (handy for
development) and picks are saved to a local file that lasts until restart.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA = ROOT / "data"

DEFAULTS = {
    "data_repo": "johnpaullichaa-source/Nrl-match-data",
    "data_branch": "main",
    "site_repo": "johnpaullichaa-source/safest-5-picks",
    "site_branch": "main",
}


def _secret(key: str, default=None):
    try:
        sec = st.secrets.get("github", {})
        if key in sec and sec[key]:
            return str(sec[key]).strip()
        flat = st.secrets.get(f"GITHUB_{key.upper()}")
        if flat:
            return str(flat).strip()
    except Exception:
        pass
    env = os.environ.get(f"GITHUB_{key.upper()}")
    return env.strip() if env else default


def config() -> dict:
    cfg = {k: _secret(k, v) for k, v in DEFAULTS.items()}
    cfg["token"] = _secret("token")
    return cfg


def _headers(token: str, raw: bool = False) -> dict:
    return {
        "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }


def _hint(status: int, repo: str) -> str:
    return {
        401: "GitHub rejected the token (401): it's expired or mistyped.",
        403: f"The token doesn't have permission on {repo} (403).",
        404: f"Not found on {repo} (404): check the file name and that the token can see the repo.",
    }.get(status, f"GitHub returned {status}.")


@st.cache_data(ttl=600, show_spinner="Loading data from your NRL repo…")
def _fetch_raw(repo: str, branch: str, path: str, token: str) -> bytes:
    r = requests.get(f"https://api.github.com/repos/{repo}/contents/{path}",
                     headers=_headers(token, raw=True), params={"ref": branch}, timeout=30)
    if r.status_code == 200:
        return r.content
    raise FileNotFoundError(_hint(r.status_code, repo))


def read_data_file(path: str) -> tuple[bytes | None, str]:
    """Bytes of a file in the NRL data repo (or ./data locally) and where it came from."""
    cfg = config()
    if cfg["token"]:
        try:
            return _fetch_raw(cfg["data_repo"], cfg["data_branch"], path, cfg["token"]), f"{cfg['data_repo']}/{path}"
        except FileNotFoundError as e:
            local = LOCAL_DATA / path
            if local.exists():
                return local.read_bytes(), f"local copy ({e})"
            return None, str(e)
    local = LOCAL_DATA / path
    if local.exists():
        return local.read_bytes(), f"local data/{path}"
    return None, "No GitHub token set and no local copy."


def refresh_data() -> None:
    _fetch_raw.clear()
    _fetch_json.clear()


# ---------------------------------------------------------------------------
# Picks log (stored in this site's own repo)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner=False)
def _fetch_json(repo: str, branch: str, path: str, token: str) -> dict:
    r = requests.get(f"https://api.github.com/repos/{repo}/contents/{path}",
                     headers=_headers(token, raw=True), params={"ref": branch}, timeout=15)
    if r.status_code == 200:
        return json.loads(r.text) if r.text.strip() else {}
    if r.status_code == 404:
        return {}
    raise RuntimeError(_hint(r.status_code, repo))


def load_json(path: str) -> dict:
    cfg = config()
    if cfg["token"]:
        try:
            return _fetch_json(cfg["site_repo"], cfg["site_branch"], path, cfg["token"])
        except Exception as e:
            st.warning(f"Couldn't read {path} from GitHub, using the local copy. {e}")
    local = ROOT / path
    if local.exists():
        try:
            return json.loads(local.read_text() or "{}")
        except Exception:
            return {}
    return {}


def save_json(path: str, data: dict, message: str) -> tuple[bool, str]:
    payload = json.dumps(data, indent=2, sort_keys=True)
    try:
        (ROOT / path).write_text(payload)
    except Exception:
        pass
    cfg = config()
    if not cfg["token"]:
        return True, "Saved on this server only (no GitHub token set), so it'll be lost when the app restarts."
    url = f"https://api.github.com/repos/{cfg['site_repo']}/contents/{path}"
    h = _headers(cfg["token"])
    for _ in range(2):
        sha = None
        g = requests.get(url, headers=h, params={"ref": cfg["site_branch"]}, timeout=15)
        if g.status_code == 200:
            sha = g.json().get("sha")
        body = {"message": message, "branch": cfg["site_branch"],
                "content": base64.b64encode(payload.encode()).decode()}
        if sha:
            body["sha"] = sha
        r = requests.put(url, headers=h, json=body, timeout=20)
        if r.status_code in (200, 201):
            _fetch_json.clear()
            return True, f"Saved to {cfg['site_repo']}."
        if r.status_code != 409:
            return False, _hint(r.status_code, cfg["site_repo"])
    return False, "GitHub kept reporting a conflict. Try again."


def status_line() -> str:
    cfg = config()
    if cfg["token"]:
        return f"Data: {cfg['data_repo']} · Picks saved to: {cfg['site_repo']}"
    return "No GitHub token set: reading ./data and saving locally only."
