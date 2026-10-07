#!/usr/bin/env python3
"""
Metal Quest Completer - Discord Quest Auto-Completer Bot
"""

import discord
from discord.ext import commands
from discord import app_commands
import requests
import json
import time
import random
import sys
import os
import re
import base64
import traceback
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
import concurrent.futures
from keep_alive import keep_alive

# ── Config ───────────────────────────────────────────────────────────────────────────────
API_BASE = "https://discord.com/api/v9"
HEARTBEAT_INTERVAL = 20
AUTO_ACCEPT = True
LOG_PROGRESS = True
DEBUG = False
REQUIRED_GUILD_ID = 1545775528320041050
REQUIRED_GUILD_INVITE = "https://discord.gg/uppjxW3R6u"
MAX_QUESTS_PER_DAY_NON_PREMIUM = 10
MAX_CONCURRENT_TASKS = 50
QUEST_IMAGE_URL = "https://cdn.discordapp.com/attachments/1529790261113126995/1536925877164580975/1534757582441419064.jpg?ex=6a7d2d43&is=6a7bdbc3&hm=fe19ae63a0c1eb3dbded5216757c48f8f78a200de5c54fdb487e573ec95c82fc"

SUPPORTED_TASKS = [
    "WATCH_VIDEO",
    "PLAY_ON_DESKTOP",
    "STREAM_ON_DESKTOP",
    "PLAY_ACTIVITY",
    "WATCH_VIDEO_ON_MOBILE",
]

TOKENS_FILE = "tokens.json"
QUEUE_FILE = "queue.json"
SETTINGS_FILE = "settings.json"

# ── Custom animated emojis ──────────────────────────────────────────────
EMOJI_ERROR = "❌"
EMOJI_PREMIUM = "💎"
EMOJI_BOOST = "🚀"
EMOJI_DISCORD = "🎮"
EMOJI_HELP = "❓"
EMOJI_HELPER = "🆘"
EMOJI_HELPY = "🤖"
EMOJI_LOADING = "⏳"
EMOJI_NITRO = "💨"
EMOJI_QUESTS = "🎯"
EMOJI_TICK = "✅"
EMOJI_CROSS = "❌"
EMOJI_EVENT = "📅"
EMOJI_DEV = "🛠️"
EMOJI_PARTNER = "🤝"
EMOJI_ADMIN = "🛡️"
EMOJI_ORB = "🔮"

# ── Logging ──────────────────────────────────────────────────────────────────────────────
class Colors:
    RESET  = "\033[0m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"


def log(msg: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {
        "info":     f"{Colors.CYAN}[INFO]{Colors.RESET}",
        "ok":       f"{Colors.GREEN}[  OK]{Colors.RESET}",
        "warn":     f"{Colors.YELLOW}[WARN]{Colors.RESET}",
        "error":    f"{Colors.RED}[ ERR]{Colors.RESET}",
        "progress": f"{Colors.DIM}[PROG]{Colors.RESET}",
        "debug":    f"{Colors.DIM}[DBG ]{Colors.RESET}",
    }.get(level, f"[{level.upper()}]")
    if level == "debug" and not DEBUG:
        return
    if LOG_PROGRESS or level != "progress":
        print(f"{Colors.DIM}{ts}{Colors.RESET} {prefix} {msg}")


# ── File handling ────────────────────────────────────────────────────────────────────────
def load_json_file(filename: str, default: dict = None) -> dict:
    if default is None:
        default = {}
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            json.dump(default, f, indent=4)
        return default
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def save_json_file(filename: str, data: dict):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)


def load_tokens() -> dict:
    return load_json_file(TOKENS_FILE, {})


def save_tokens(tokens: dict):
    save_json_file(TOKENS_FILE, tokens)


def load_queue() -> dict:
    return load_json_file(QUEUE_FILE, {"queue": []})


def save_queue(queue_data: dict):
    save_json_file(QUEUE_FILE, queue_data)


def load_settings() -> dict:
    return load_json_file(SETTINGS_FILE, {
        "autoquest": {},
        "premium": {},
        "staff_roles": {},
        "owner_id": None,
        "quest_counts": {}
    })


def save_settings(settings: dict):
    save_json_file(SETTINGS_FILE, settings)


# ── Global build number cache ─────────────────────────────────────────────────────────
_BUILD_NUMBER = None

def get_build_number() -> int:
    global _BUILD_NUMBER
    if _BUILD_NUMBER is None:
        _BUILD_NUMBER = fetch_latest_build_number()
    return _BUILD_NUMBER


def fetch_latest_build_number() -> int:
    FALLBACK = 504649
    try:
        log("Fetching latest build number...", "info")
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        r = requests.get("https://discord.com/app", headers={"User-Agent": ua}, timeout=15)
        if r.status_code != 200:
            log(f"Could not fetch Discord page ({r.status_code}), using fallback", "warn")
            return FALLBACK
        scripts = re.findall(r'/assets/([a-f0-9]+)\.js', r.text)
        if not scripts:
            scripts_alt = re.findall(r'src="(/assets/[^"]+\.js)"', r.text)
            scripts = [s.split('/')[-1].replace('.js', '') for s in scripts_alt]
        if not scripts:
            log("No JS assets found, using fallback", "warn")
            return FALLBACK
        for asset_hash in scripts[-5:]:
            try:
                ar = requests.get(
                    f"https://discord.com/assets/{asset_hash}.js",
                    headers={"User-Agent": ua}, timeout=15
                )
                m = re.search(r'buildNumber["\s:]+["\s]*(\d{5,7})', ar.text)
                if m:
                    bn = int(m.group(1))
                    log(f"Build number: {Colors.BOLD}{bn}{Colors.RESET}", "ok")
                    return bn
            except Exception:
                continue
        log(f"Build number not found, using fallback {FALLBACK}", "warn")
        return FALLBACK
    except Exception as e:
        log(f"Error getting build number: {e}, using fallback {FALLBACK}", "warn")
        return FALLBACK


def make_super_properties(build_number: int) -> str:
    obj = {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": "1.0.9175",
        "os_version": "10.0.26100",
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-US",
        "browser_user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "discord/1.0.9175 Chrome/128.0.6613.186 "
            "Electron/32.2.7 Safari/537.36"
        ),
        "browser_version": "32.2.7",
        "client_build_number": build_number,
        "native_build_number": 59498,
        "client_event_source": None,
    }
    return base64.b64encode(json.dumps(obj).encode()).decode()


# ── HTTP helpers ──────────────────────────────────────────────────────────────────────
class DiscordAPI:
    def __init__(self, token: str, build_number: int):
        self.token = token
        self.session = requests.Session()
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "discord/1.0.9175 Chrome/128.0.6613.186 "
            "Electron/32.2.7 Safari/537.36"
        )
        sp = make_super_properties(build_number)
        self.session.headers.update({
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": ua,
            "X-Super-Properties": sp,
            "X-Discord-Locale": "en-US",
            "X-Discord-Timezone": "Asia/Ho_Chi_Minh",
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/channels/@me",
        })

    def get(self, path: str, **kwargs) -> requests.Response:
        url = f"{API_BASE}{path}"
        log(f"GET {path}", "debug")
        r = self.session.get(url, **kwargs)
        log(f"  -> {r.status_code} ({len(r.content)} bytes)", "debug")
        return r

    def post(self, path: str, payload: Optional[dict] = None, **kwargs) -> requests.Response:
        url = f"{API_BASE}{path}"
        log(f"POST {path}", "debug")
        r = self.session.post(url, json=payload, **kwargs)
        log(f"  -> {r.status_code} ({len(r.content)} bytes)", "debug")
        return r

    def validate_token(self) -> tuple[bool, Optional[dict]]:
        try:
            r = self.get("/users/@me")
            if r.status_code == 200:
                user = r.json()
                log(f"Logged in: {Colors.BOLD}{user.get('username', '?')}{Colors.RESET} (ID: {user['id']})", "ok")
                return True, user
            else:
                log(f"Invalid token (status {r.status_code})", "error")
                return False, None
        except Exception as e:
            log(f"Cannot connect to Discord: {e}", "error")
            return False, None


# ── Quest helpers ─────────────────────────────────────────────────────────────────────
def _get(d: Optional[dict], *keys):
    if d is None:
        return None
    for k in keys:
        if k in d:
            return d[k]
    return None


def get_task_config(quest: dict) -> Optional[dict]:
    cfg = quest.get("config", {})
    return _get(cfg, "taskConfig", "task_config", "taskConfigV2", "task_config_v2")


def get_quest_name(quest: dict) -> str:
    cfg = quest.get("config", {})
    msgs = cfg.get("messages", {})
    name = _get(msgs, "questName", "quest_name")
    if name:
        return name.strip()
    game = _get(msgs, "gameTitle", "game_title")
    if game:
        return game.strip()
    app_name = cfg.get("application", {}).get("name")
    if app_name:
        return app_name
    return f"Quest#{quest.get('id', '?')}"


def get_expires_at(quest: dict) -> Optional[str]:
    cfg = quest.get("config", {})
    return _get(cfg, "expiresAt", "expires_at")


def get_user_status(quest: dict) -> dict:
    us = _get(quest, "userStatus", "user_status")
    return us if isinstance(us, dict) else {}


def is_completable(quest: dict) -> bool:
    expires = get_expires_at(quest)
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt <= datetime.now(timezone.utc):
                return False
        except Exception:
            pass
    tc = get_task_config(quest)
    if not tc or "tasks" not in tc:
        return False
    tasks = tc["tasks"]
    return any(tasks.get(t) is not None for t in SUPPORTED_TASKS)


def is_enrolled(quest: dict) -> bool:
    us = get_user_status(quest)
    return bool(_get(us, "enrolledAt", "enrolled_at"))


def is_completed(quest: dict) -> bool:
    us = get_user_status(quest)
    return bool(_get(us, "completedAt", "completed_at"))


def get_task_type(quest: dict) -> Optional[str]:
    tc = get_task_config(quest)
    if not tc or "tasks" not in tc:
        return None
    for t in SUPPORTED_TASKS:
        if tc["tasks"].get(t) is not None:
            return t
    return None


def get_seconds_needed(quest: dict) -> int:
    tc = get_task_config(quest)
    task_type = get_task_type(quest)
    if not tc or not task_type:
        return 0
    return tc["tasks"][task_type].get("target", 0)


def get_seconds_done(quest: dict) -> float:
    task_type = get_task_type(quest)
    if not task_type:
        return 0
    us = get_user_status(quest)
    progress = us.get("progress", {})
    if not progress:
        progress = {}
    return progress.get(task_type, {}).get("value", 0)


def get_enrolled_at(quest: dict) -> Optional[str]:
    us = get_user_status(quest)
    return _get(us, "enrolledAt", "enrolled_at")


# ── Core logic ──────────────────────────────────────────────────────────────────────────
class QuestAutocompleter:
    def __init__(self, token: str, user_id: str, username: str, build_number: int,
                 user: discord.User = None, bot_loop: asyncio.AbstractEventLoop = None,
                 stop_event: asyncio.Event = None, on_progress: callable = None):
        self.token = token
        self.user_id = user_id
        self.username = username
        self.user = user
        self.bot_loop = bot_loop
        self.build_number = build_number
        self.api = DiscordAPI(token, self.build_number)
        self.completed_ids: set = set()
        self.stop_event = stop_event or asyncio.Event()
        self.on_progress = on_progress

    async def _send_dm(self, content: str):
        if self.user and self.bot_loop:
            future = asyncio.run_coroutine_threadsafe(self.user.send(content), self.bot_loop)
            try:
                await asyncio.wrap_future(future)
            except Exception:
                pass

    def _call_progress(self, quest_name: str, progress: float, total: int, quest: dict = None):
        if self.on_progress and self.bot_loop:
            asyncio.run_coroutine_threadsafe(
                self.on_progress(quest_name, progress, total, quest),
                self.bot_loop
            )

    def fetch_quests(self) -> list:
        try:
            r = self.api.get("/quests/@me")
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    return data.get("quests", [])
                elif isinstance(data, list):
                    return data
                return []
            elif r.status_code == 429:
                retry_after = r.json().get("retry_after", 10)
                wait = retry_after + random.uniform(0.5, 2.0)
                log(f"Rate limited – waiting {wait:.1f}s", "warn")
                time.sleep(wait)
                return self.fetch_quests()
            else:
                return []
        except Exception:
            return []

    def enroll_quest(self, quest: dict) -> bool:
        name = get_quest_name(quest)
        qid = quest["id"]
        for _ in range(3):
            try:
                r = self.api.post(f"/quests/{qid}/enroll", {
                    "location": 11,
                    "is_targeted": False,
                    "metadata_raw": None,
                    "metadata_sealed": None,
                    "traffic_metadata_raw": quest.get("traffic_metadata_raw"),
                    "traffic_metadata_sealed": quest.get("traffic_metadata_sealed"),
                })
                if r.status_code == 429:
                    retry_after = r.json().get("retry_after", 5)
                    wait = retry_after + 1
                    log(f"Rate limited enrolling \"{name}\" – waiting {wait}s", "warn")
                    time.sleep(wait)
                    continue
                if r.status_code in (200, 201, 204):
                    log(f"Enrolled: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                    return True
                return False
            except Exception:
                return False
        return False

    def auto_accept(self, quests: list) -> list:
        if not AUTO_ACCEPT:
            return quests
        unaccepted = [
            q for q in quests
            if not is_enrolled(q) and not is_completed(q) and is_completable(q)
        ]
        if not unaccepted:
            return quests
        log(f"Found {len(unaccepted)} unaccepted quests – auto-accepting...", "info")
        for q in unaccepted:
            if self.stop_event.is_set():
                break
            self.enroll_quest(q)
            time.sleep(3)
        time.sleep(2)
        return self.fetch_quests()

    def complete_video(self, quest: dict):
        name = get_quest_name(quest)
        qid = quest["id"]
        seconds_needed = get_seconds_needed(quest)
        seconds_done = get_seconds_done(quest)
        enrolled_at_str = get_enrolled_at(quest)
        if enrolled_at_str:
            enrolled_ts = datetime.fromisoformat(enrolled_at_str.replace("Z", "+00:00")).timestamp()
        else:
            enrolled_ts = time.time()
        log(f"🎬 Video: {Colors.BOLD}{name}{Colors.RESET} ({seconds_done:.0f}/{seconds_needed}s)", "info")
        asyncio.run_coroutine_threadsafe(
            self._send_dm(f"▶ Starting quest: **{name}** (video)"), self.bot_loop
        )
        self._call_progress(name, seconds_done, seconds_needed, quest)
        max_future = 10
        speed = 7
        interval = 1
        while seconds_done < seconds_needed:
            if self.stop_event.is_set():
                return
            max_allowed = (time.time() - enrolled_ts) + max_future
            diff = max_allowed - seconds_done
            timestamp = seconds_done + speed
            if diff >= speed:
                try:
                    r = self.api.post(f"/quests/{qid}/video-progress", {
                        "timestamp": min(seconds_needed, timestamp + random.random())
                    })
                    if r.status_code == 200:
                        body = r.json()
                        if body.get("completed_at"):
                            log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                            asyncio.run_coroutine_threadsafe(
                                self._send_dm(f"✅ Completed quest: **{name}**"), self.bot_loop
                            )
                            self._call_progress(name, seconds_needed, seconds_needed, quest)
                            return
                        seconds_done = min(seconds_needed, timestamp)
                        log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                        self._call_progress(name, seconds_done, seconds_needed, quest)
                    elif r.status_code == 429:
                        retry_after = r.json().get("retry_after", 5)
                        wait = retry_after + 1
                        log(f"  Rate limited – waiting {wait}s", "warn")
                        time.sleep(wait)
                        continue
                except Exception:
                    pass
            if timestamp >= seconds_needed:
                break
            time.sleep(interval)
        if not self.stop_event.is_set():
            try:
                self.api.post(f"/quests/{qid}/video-progress", {"timestamp": seconds_needed})
            except Exception:
                pass
            log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
            asyncio.run_coroutine_threadsafe(
                self._send_dm(f"✅ Completed quest: **{name}**"), self.bot_loop
            )
            self._call_progress(name, seconds_needed, seconds_needed, quest)

    def complete_heartbeat(self, quest: dict):
        name = get_quest_name(quest)
        qid = quest["id"]
        task_type = get_task_type(quest)
        seconds_needed = get_seconds_needed(quest)
        seconds_done = get_seconds_done(quest)
        remaining = max(0, seconds_needed - seconds_done)
        log(f"🎮 {task_type}: {Colors.BOLD}{name}{Colors.RESET} (~{remaining // 60} min left)", "info")
        asyncio.run_coroutine_threadsafe(
            self._send_dm(f"▶ Starting quest: **{name}** ({task_type})"), self.bot_loop
        )
        self._call_progress(name, seconds_done, seconds_needed, quest)
        pid = random.randint(1000, 30000)
        while seconds_done < seconds_needed:
            if self.stop_event.is_set():
                return
            try:
                r = self.api.post(f"/quests/{qid}/heartbeat", {
                    "stream_key": f"call:0:{pid}",
                    "terminal": False,
                })
                if r.status_code == 200:
                    body = r.json()
                    progress_data = body.get("progress", {})
                    if progress_data and task_type in progress_data:
                        seconds_done = progress_data[task_type].get("value", seconds_done)
                    log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                    self._call_progress(name, seconds_done, seconds_needed, quest)
                    if body.get("completed_at") or seconds_done >= seconds_needed:
                        log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                        asyncio.run_coroutine_threadsafe(
                            self._send_dm(f"✅ Completed quest: **{name}**"), self.bot_loop
                        )
                        self._call_progress(name, seconds_needed, seconds_needed, quest)
                        return
                elif r.status_code == 429:
                    retry_after = r.json().get("retry_after", 10)
                    wait = retry_after + 1
                    log(f"  Rate limited – waiting {wait}s", "warn")
                    time.sleep(wait)
                    continue
            except Exception:
                pass
            time.sleep(HEARTBEAT_INTERVAL)
        if not self.stop_event.is_set():
            try:
                self.api.post(f"/quests/{qid}/heartbeat", {
                    "stream_key": f"call:0:{pid}",
                    "terminal": True,
                })
            except Exception:
                pass
            log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
            asyncio.run_coroutine_threadsafe(
                self._send_dm(f"✅ Completed quest: **{name}**"), self.bot_loop
            )
            self._call_progress(name, seconds_needed, seconds_needed, quest)

    def complete_activity(self, quest: dict):
        name = get_quest_name(quest)
        qid = quest["id"]
        seconds_needed = get_seconds_needed(quest)
        seconds_done = get_seconds_done(quest)
        remaining = max(0, seconds_needed - seconds_done)
        log(f"🕹️ Activity: {Colors.BOLD}{name}{Colors.RESET} (~{remaining // 60} min left)", "info")
        asyncio.run_coroutine_threadsafe(
            self._send_dm(f"▶ Starting quest: **{name}** (activity)"), self.bot_loop
        )
        self._call_progress(name, seconds_done, seconds_needed, quest)
        stream_key = "call:0:1"
        while seconds_done < seconds_needed:
            if self.stop_event.is_set():
                return
            try:
                r = self.api.post(f"/quests/{qid}/heartbeat", {
                    "stream_key": stream_key,
                    "terminal": False,
                })
                if r.status_code == 200:
                    body = r.json()
                    progress_data = body.get("progress", {})
                    if progress_data and "PLAY_ACTIVITY" in progress_data:
                        seconds_done = progress_data["PLAY_ACTIVITY"].get("value", seconds_done)
                    log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                    self._call_progress(name, seconds_done, seconds_needed, quest)
                    if body.get("completed_at") or seconds_done >= seconds_needed:
                        break
                elif r.status_code == 429:
                    retry_after = r.json().get("retry_after", 10)
                    wait = retry_after + 1
                    log(f"  Rate limited – waiting {wait}s", "warn")
                    time.sleep(wait)
                    continue
            except Exception:
                pass
            time.sleep(HEARTBEAT_INTERVAL)
        if not self.stop_event.is_set():
            try:
                self.api.post(f"/quests/{qid}/heartbeat", {
                    "stream_key": stream_key,
                    "terminal": True,
                })
            except Exception:
                pass
            log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
            asyncio.run_coroutine_threadsafe(
                self._send_dm(f"✅ Completed quest: **{name}**"), self.bot_loop
            )
            self._call_progress(name, seconds_needed, seconds_needed, quest)

    def process_quest(self, quest: dict):
        qid = quest.get("id")
        name = get_quest_name(quest)
        task_type = get_task_type(quest)
        if not task_type or qid in self.completed_ids:
            return
        log(f"━━━ Starting: {Colors.BOLD}{name}{Colors.RESET} (task: {task_type}) ━━━", "info")
        if task_type in ("WATCH_VIDEO", "WATCH_VIDEO_ON_MOBILE"):
            self.complete_video(quest)
        elif task_type in ("PLAY_ON_DESKTOP", "STREAM_ON_DESKTOP"):
            self.complete_heartbeat(quest)
        elif task_type == "PLAY_ACTIVITY":
            self.complete_activity(quest)
        self.completed_ids.add(qid)

    def run_once(self) -> Dict:
        log(f"Starting quest cycle for {self.username}", "info")
        quests = self.fetch_quests()
        if not quests:
            log("No quests found", "info")
            return {"status": "no_quests", "quests": []}
        quests = self.auto_accept(quests)
        actionable = [
            q for q in quests
            if is_enrolled(q) and not is_completed(q) and is_completable(q)
            and q.get("id") not in self.completed_ids
        ]
        if actionable:
            log(f"\n{len(actionable)} quest(s) to complete:", "info")
            for q in actionable:
                if self.stop_event.is_set():
                    break
                self.process_quest(q)
            return {"status": "completed", "quests": []}
        else:
            log("No quests to complete at this time", "info")
            return {"status": "no_action", "quests": []}

    def get_quests_status(self) -> Dict:
        try:
            quests = self.fetch_quests()
            completed = []
            in_progress = []
            available = []
            for q in quests:
                name = get_quest_name(q)
                task = get_task_type(q) or "?"
                expires = get_expires_at(q)
                is_expired = False
                if expires:
                    try:
                        exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                        if exp_dt <= datetime.now(timezone.utc):
                            is_expired = True
                    except Exception:
                        pass
                if is_completed(q):
                    completed.append({"name": name, "task": task})
                elif is_expired:
                    continue
                elif is_enrolled(q):
                    seconds_done = get_seconds_done(q)
                    seconds_needed = get_seconds_needed(q)
                    progress = f"{seconds_done:.0f}/{seconds_needed}s" if seconds_needed > 0 else "In progress"
                    in_progress.append({"name": name, "task": task, "progress": progress})
                elif is_completable(q):
                    available.append({"name": name, "task": task})
            return {
                "completed": completed,
                "in_progress": in_progress,
                "available": available,
                "total": len(quests)
            }
        except Exception as e:
            log(f"Error in get_quests_status: {e}", "error")
            return {"completed": [], "in_progress": [], "available": [], "total": 0}

    # ── Single quest completion ────────────────────────────────────────────────────
    def _process_single_quest_sync(self, quest: dict):
        qid = quest.get("id")
        name = get_quest_name(quest)
        task_type = get_task_type(quest)
        if not task_type or qid in self.completed_ids:
            return
        log(f"━━━ Starting: {Colors.BOLD}{name}{Colors.RESET} (task: {task_type}) ━━━", "info")
        if not is_enrolled(quest):
            self.enroll_quest(quest)
        if task_type in ("WATCH_VIDEO", "WATCH_VIDEO_ON_MOBILE"):
            self.complete_video(quest)
        elif task_type in ("PLAY_ON_DESKTOP", "STREAM_ON_DESKTOP"):
            self.complete_heartbeat(quest)
        elif task_type == "PLAY_ACTIVITY":
            self.complete_activity(quest)
        self.completed_ids.add(qid)

    async def complete_single_quest(self, quest: dict, on_progress: callable = None):
        self.on_progress = on_progress
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._process_single_quest_sync, quest)


# ── Discord Bot ────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class QuestBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=';', intents=intents)
        self.remove_command('help')
        self.queue = []
        self.active_tasks = {}  # user_id -> asyncio.Task
        self.active_users = set()  # user_id set
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)
        self.stop_events = {}
        self.build_number = get_build_number()
        self.settings = load_settings()
        self.user_messages = {}  # user_id -> (channel_id, message_id)

    async def setup_hook(self):
        await self.tree.sync()
        print("Synced slash commands")
        asyncio.create_task(self.process_queue())

    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        print(f'Bot is in {len(self.guilds)} guilds')
        queue_data = load_queue()
        self.queue = queue_data.get("queue", [])
        log(f"Loaded {len(self.queue)} users from queue", "info")

    # ── Required guild check for token account ──────────────────────────────────────
    async def check_token_account_in_guild(self, token_user_id: str) -> tuple[bool, str]:
        guild = self.get_guild(REQUIRED_GUILD_ID)
        if not guild:
            return False, f"{EMOJI_ERROR} Bot is not in the required server. Please ask the owner to add it."
        member = guild.get_member(int(token_user_id))
        if member:
            return True, ""
        else:
            return False, f"{EMOJI_CROSS} The account you linked is not in the required server.\n\nPlease join: {REQUIRED_GUILD_INVITE}"

    # ── Quest limit and stats ──────────────────────────────────────────────────────
    async def check_quest_limit(self, user_id: str) -> tuple[bool, str]:
        if self.is_premium(user_id):
            return True, ""
        settings = load_settings()
        if "quest_counts" not in settings:
            settings["quest_counts"] = {}
        now = datetime.now()
        user_data = settings["quest_counts"].get(user_id, {})
        count = user_data.get("count", 0)
        reset_time_str = user_data.get("reset_time")
        if reset_time_str:
            reset_time = datetime.fromisoformat(reset_time_str)
            if now < reset_time:
                if count >= MAX_QUESTS_PER_DAY_NON_PREMIUM:
                    remaining = reset_time - now
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    return False, f"{EMOJI_CROSS} You've reached your daily limit of **{MAX_QUESTS_PER_DAY_NON_PREMIUM}** quests. Reset in **{hours}h {minutes}m**."
                else:
                    return True, ""
            else:
                settings["quest_counts"][user_id] = {"count": 0, "reset_time": (now + timedelta(hours=24)).isoformat()}
                save_settings(settings)
                self.settings = settings
                return True, ""
        else:
            settings["quest_counts"][user_id] = {"count": 0, "reset_time": (now + timedelta(hours=24)).isoformat()}
            save_settings(settings)
            self.settings = settings
            return True, ""

    async def increment_quest_count(self, user_id: str):
        if self.is_premium(user_id):
            return
        settings = load_settings()
        if "quest_counts" not in settings:
            settings["quest_counts"] = {}
        user_data = settings["quest_counts"].get(user_id, {})
        count = user_data.get("count", 0) + 1
        total_success = user_data.get("total_success", 0) + 1
        reset_time = user_data.get("reset_time")
        if not reset_time:
            reset_time = (datetime.now() + timedelta(hours=24)).isoformat()
        settings["quest_counts"][user_id] = {
            "count": count,
            "reset_time": reset_time,
            "total_success": total_success,
            "total_attempts": user_data.get("total_attempts", 0)
        }
        save_settings(settings)
        self.settings = settings

    async def increment_total_attempts(self, user_id: str):
        settings = load_settings()
        if "quest_counts" not in settings:
            settings["quest_counts"] = {}
        user_data = settings["quest_counts"].get(user_id, {})
        total_attempts = user_data.get("total_attempts", 0) + 1
        settings["quest_counts"][user_id] = {
            "count": user_data.get("count", 0),
            "reset_time": user_data.get("reset_time"),
            "total_success": user_data.get("total_success", 0),
            "total_attempts": total_attempts
        }
        save_settings(settings)
        self.settings = settings

    def get_user_stats(self, user_id: str) -> dict:
        settings = load_settings()
        user_data = settings.get("quest_counts", {}).get(user_id, {})
        return {
            "total_attempts": user_data.get("total_attempts", 0),
            "total_success": user_data.get("total_success", 0)
        }

    # ── Announce command ────────────────────────────────────────────────────────────
    async def announce(self, ctx_or_interaction, message: str, attachment: discord.Attachment = None):
        guild = ctx_or_interaction.guild
        if not guild:
            await ctx_or_interaction.send(f"{EMOJI_ERROR} This command must be used in a server.")
            return
        if not self.is_owner(str(ctx_or_interaction.author.id)):
            await ctx_or_interaction.send(f"{EMOJI_CROSS} Only the bot owner can use this command.")
            return

        success_count = 0
        fail_count = 0
        total = len([m for m in guild.members if not m.bot])
        embed = discord.Embed(
            title=f"{EMOJI_EVENT} Announcement",
            description=f"Sending announcement to **{total}** members...",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=ctx_or_interaction.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
            msg = await ctx_or_interaction.original_response()
        else:
            msg = await ctx_or_interaction.send(embed=embed)

        file_to_send = None
        if attachment:
            if attachment.size > 8 * 1024 * 1024:
                await msg.edit(embed=discord.Embed(
                    title=f"{EMOJI_ERROR} File too large",
                    description="Attachment exceeds 8MB limit.",
                    color=discord.Color.red()
                ))
                return
            try:
                file_data = await attachment.read()
                file_to_send = discord.File(file_data, filename=attachment.filename)
            except Exception as e:
                await msg.edit(embed=discord.Embed(
                    title=f"{EMOJI_ERROR} Error",
                    description=f"Could not download attachment: {e}",
                    color=discord.Color.red()
                ))
                return

        for member in guild.members:
            if member.bot or member.id == self.user.id:
                continue
            try:
                if file_to_send:
                    await member.send(content=message, file=file_to_send)
                else:
                    await member.send(message)
                success_count += 1
            except Exception:
                fail_count += 1
            await asyncio.sleep(0.5)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Announcement Complete",
            description=f"**Message:**\n{message}",
            color=discord.Color.green()
        )
        embed.add_field(name="Successful", value=str(success_count), inline=True)
        embed.add_field(name="Failed", value=str(fail_count), inline=True)
        embed.add_field(name="Total attempted", value=str(total), inline=True)
        embed.set_thumbnail(url=ctx_or_interaction.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await msg.edit(embed=embed)

    # ── Concurrent queue processor ────────────────────────────────────────────────
    async def process_queue(self):
        await self.wait_until_ready()
        while True:
            try:
                # Clean up finished tasks
                finished = [uid for uid, task in self.active_tasks.items() if task.done()]
                for uid in finished:
                    del self.active_tasks[uid]
                    self.active_users.discard(uid)
                    if uid in self.user_messages:
                        del self.user_messages[uid]
                    if uid in self.stop_events:
                        del self.stop_events[uid]

                # Start new tasks if under limit
                while self.queue and len(self.active_tasks) < MAX_CONCURRENT_TASKS:
                    user_id = self.queue.pop(0)
                    if user_id in self.active_users:
                        continue
                    self.stop_events[user_id] = asyncio.Event()
                    task = asyncio.create_task(self._process_user(user_id))
                    self.active_tasks[user_id] = task
                    self.active_users.add(user_id)
                    save_queue({"queue": self.queue})

                await asyncio.sleep(1)
            except Exception as e:
                log(f"Queue processor error: {e}", "error")
                await asyncio.sleep(5)

    async def _process_user(self, user_id: str):
        try:
            tokens = load_tokens()
            if str(user_id) not in tokens:
                log(f"User {user_id} not found in tokens", "warn")
                return
            token_data = tokens[str(user_id)]
            token = token_data.get("token")
            username = token_data.get("username", "Unknown")
            stop_event = self.stop_events.get(user_id)

            user = await self.fetch_user(int(user_id))
            if user:
                await user.send(f"{EMOJI_LOADING} Starting quest completion for **{username}**...")
            embed = discord.Embed(
                title=f"{EMOJI_QUESTS} Quest Completion",
                description=f"{EMOJI_LOADING} Starting quest completion...",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=user.display_avatar.url if user else None)
            embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
            await self.update_channel_message(user_id, embed=embed)

            async def progress_callback(quest_name, progress, total, quest):
                embed = self.build_quest_progress_embed(username, quest_name, progress, total, quest, user)
                await self.update_channel_message(user_id, embed=embed)

            loop = asyncio.get_event_loop()
            completer = QuestAutocompleter(
                token, str(user_id), username,
                build_number=self.build_number,
                user=user,
                bot_loop=loop,
                stop_event=stop_event,
                on_progress=progress_callback
            )
            result = await loop.run_in_executor(
                self.executor,
                completer.run_once
            )
            if result.get("status") == "completed":
                await self.increment_quest_count(user_id)
            status = completer.get_quests_status()
            embed = build_questlist_embed(username, status, user=user)
            if user:
                await user.send(embed=embed)
            await self.update_channel_message(user_id, embed=embed)

        except Exception as e:
            log(f"Error processing user {user_id}: {e}", "error")
            user = await self.fetch_user(int(user_id))
            if user:
                await user.send(f"{EMOJI_ERROR} An error occurred: {str(e)}")
        finally:
            self.active_users.discard(user_id)
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
            if user_id in self.user_messages:
                del self.user_messages[user_id]
            if user_id in self.stop_events:
                del self.stop_events[user_id]

    def build_quest_progress_embed(self, username: str, quest_name: str, progress: float, total: int, quest: dict, user: discord.User) -> discord.Embed:
        """Build a detailed quest progress embed like the screenshot."""
        task_type = get_task_type(quest) if quest else "Unknown"
        seconds_needed = get_seconds_needed(quest) if quest else total
        seconds_done = get_seconds_done(quest) if quest else progress
        percentage = int((progress / total) * 100) if total > 0 else 0

        # Build progress bar with emojis
        bar_length = 20
        filled = int((progress / total) * bar_length) if total > 0 else 0
        progress_bar = "█" * filled + "░" * (bar_length - filled)

        embed = discord.Embed(
            title=f"{EMOJI_QUESTS} Quest - {quest_name}",
            description=f"**Quest session started.**\nTask: {task_type} | Target: {total}s | Already done: {int(progress)}s",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=user.display_avatar.url if user else None)

        # Progress field with bar and percentage
        embed.add_field(
            name="Target progress",
            value=f"`{progress_bar}` **{percentage}%**",
            inline=False
        )

        # Progress log (show last few updates)
        embed.add_field(
            name="Progress",
            value=f"Progress: {int(progress)}/{total}s ({percentage}%)",
            inline=False
        )

        # Status field
        embed.add_field(
            name="Status",
            value=f"**ID**\nIn Progress\n{quest.get('id', 'N/A') if quest else 'N/A'}",
            inline=True
        )

        # Quest Details
        embed.add_field(
            name="Quest Details",
            value="Complete this quest to earn rewards!",
            inline=True
        )

        # Footer with orb emoji
        embed.set_footer(text=f"{EMOJI_ORB} Metal Quest Completer • Developed by abubakarmalikgul")

        # Set image at the bottom
        embed.set_image(url=QUEST_IMAGE_URL)

        return embed

    async def update_channel_message(self, user_id: str, embed: discord.Embed = None):
        if user_id not in self.user_messages:
            return
        channel_id, message_id = self.user_messages[user_id]
        channel = self.get_channel(channel_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(message_id)
            if embed:
                await msg.edit(embed=embed)
        except Exception as e:
            log(f"Failed to update channel message for {user_id}: {e}", "warn")

    # ── Queue management ───────────────────────────────────────────────────────────
    def add_to_queue(self, user_id: str) -> bool:
        if user_id not in self.queue and user_id not in self.active_users:
            self.queue.append(user_id)
            save_queue({"queue": self.queue})
            return True
        return False

    def remove_from_queue(self, user_id: str) -> bool:
        if user_id in self.queue:
            self.queue.remove(user_id)
            save_queue({"queue": self.queue})
            return True
        return False

    async def stop_questing(self, user_id: str) -> bool:
        self.remove_from_queue(user_id)
        if user_id in self.stop_events:
            self.stop_events[user_id].set()
            await asyncio.sleep(2)
            if user_id in self.active_tasks and not self.active_tasks[user_id].done():
                self.active_tasks[user_id].cancel()
        return True

    # ── Premium / staff / owner helpers ────────────────────────────────────────────
    def is_premium(self, user_id: str) -> bool:
        return self.settings.get("premium", {}).get(str(user_id), False)

    def set_premium(self, user_id: str, value: bool):
        if "premium" not in self.settings:
            self.settings["premium"] = {}
        self.settings["premium"][str(user_id)] = value
        save_settings(self.settings)

    def get_staff_role(self, guild_id: int) -> Optional[int]:
        return self.settings.get("staff_roles", {}).get(str(guild_id))

    def set_staff_role(self, guild_id: int, role_id: int):
        if "staff_roles" not in self.settings:
            self.settings["staff_roles"] = {}
        self.settings["staff_roles"][str(guild_id)] = role_id
        save_settings(self.settings)

    def remove_staff_role(self, guild_id: int):
        if "staff_roles" in self.settings and str(guild_id) in self.settings["staff_roles"]:
            del self.settings["staff_roles"][str(guild_id)]
            save_settings(self.settings)

    def is_owner(self, user_id: str) -> bool:
        return str(user_id) == self.settings.get("1423268431943176338")

    async def is_staff(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        if self.is_owner(str(interaction.user.id)):
            return True
        role_id = self.get_staff_role(interaction.guild.id)
        if not role_id:
            return False
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
        return any(role.id == role_id for role in member.roles)

    async def is_staff_ctx(self, ctx) -> bool:
        if not ctx.guild:
            return False
        if self.is_owner(str(ctx.author.id)):
            return True
        role_id = self.get_staff_role(ctx.guild.id)
        if not role_id:
            return False
        member = ctx.guild.get_member(ctx.author.id)
        if not member:
            return False
        return any(role.id == role_id for role in member.roles)


# ── Helper functions for embeds ──────────────────────────────────────────────────────
def build_questlist_embed(username: str, status: dict, user: discord.User = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI_QUESTS} Quest Status - {username}",
        color=discord.Color.blue()
    )
    if user:
        embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    total = status.get("total", 0)
    in_progress_count = len(status.get("in_progress", []))
    completed_count = len(status.get("completed", []))
    embed.add_field(name=f"{EMOJI_QUESTS} Total", value=str(total), inline=True)
    embed.add_field(name=f"{EMOJI_LOADING} In Progress", value=str(in_progress_count), inline=True)
    embed.add_field(name=f"{EMOJI_TICK} Completed", value=str(completed_count), inline=True)
    
    if status.get("in_progress"):
        text = ""
        for q in status["in_progress"]:
            text += f"• **{q['name']}** [{q['task']}] - {q['progress']}\n"
        embed.add_field(name=f"{EMOJI_LOADING} In Progress List", value=text[:1024] or "None", inline=False)
    else:
        embed.add_field(name=f"{EMOJI_LOADING} In Progress List", value="No quests in progress", inline=False)
    if status.get("completed"):
        text = ""
        for q in status["completed"]:
            text += f"• **{q['name']}** [{q['task']}]\n"
        embed.add_field(name=f"{EMOJI_TICK} Completed List", value=text[:1024] or "None", inline=False)
    else:
        embed.add_field(name=f"{EMOJI_TICK} Completed List", value="No completed quests", inline=False)
    if status.get("available"):
        text = ""
        for q in status["available"]:
            text += f"• **{q['name']}** [{q['task']}]\n"
        embed.add_field(name=f"{EMOJI_QUESTS} Available", value=text[:1024] or "None", inline=False)
    else:
        embed.add_field(name=f"{EMOJI_QUESTS} Available", value="No available quests", inline=False)
    embed.set_footer(text=f"Total Quests: {total} • Metal Quest Completer • abubakarmalikgul")
    embed.set_image(url=QUEST_IMAGE_URL)
    return embed


# ── Instantiate bot ──────────────────────────────────────────────────────────────────
bot = QuestBot()


# ── Interactive Quest Selection View ─────────────────────────────────────────────────
class QuestSelectionView(discord.ui.View):
    def __init__(self, user_id: str, quests: list, bot: QuestBot, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.quests = quests
        self.bot = bot
        self.selected_quest = None
        self.message = None  # This will be the message object we can edit
        self.is_slash = False
        self._interaction = None

        options = []
        for i, q in enumerate(quests):
            name = get_quest_name(q)
            task = get_task_type(q) or "?"
            label = name[:50]
            if len(name) > 50:
                label += "..."
            desc = f"{task} - {get_seconds_needed(q)}s"
            default = (i == 0)
            options.append(discord.SelectOption(label=label, value=q['id'], description=desc[:100], default=default))

        self.select = discord.ui.Select(placeholder="Select a quest to complete", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

        self.start_button = discord.ui.Button(label="Start Selected Quest", style=discord.ButtonStyle.green)
        self.start_button.callback = self.start_callback
        self.add_item(self.start_button)

        if quests:
            self.selected_quest = quests[0]

    async def select_callback(self, interaction: discord.Interaction):
        quest_id = self.select.values[0]
        quest = next((q for q in self.quests if q['id'] == quest_id), None)
        if not quest:
            await interaction.response.send_message(f"{EMOJI_ERROR} Quest not found.", ephemeral=True)
            return
        self.selected_quest = quest
        embed = self.build_detail_embed(quest, show_available=True)
        # We have the message reference, edit it directly
        if self.message:
            await self.message.edit(embed=embed, view=self)
            await interaction.response.defer()
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    def build_detail_embed(self, quest, show_available=False):
        name = get_quest_name(quest)
        task = get_task_type(quest) or "?"
        seconds_needed = get_seconds_needed(quest)
        seconds_done = get_seconds_done(quest)
        status = "Enrolled" if is_enrolled(quest) else "Not Enrolled"
        expired = False
        expires = get_expires_at(quest)
        if expires:
            try:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if exp_dt <= datetime.now(timezone.utc):
                    expired = True
            except Exception:
                pass
        if expired:
            status = "Expired"
        embed = discord.Embed(title=f"{EMOJI_QUESTS} Quest: {name}", color=discord.Color.blue())
        embed.add_field(name="Task", value=task, inline=True)
        embed.add_field(name="Progress", value=f"{seconds_done:.0f}/{seconds_needed}s", inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        if not expired and not is_completed(quest):
            time_left = seconds_needed - seconds_done
            embed.add_field(name="Estimated Time", value=f"{time_left // 60} min {time_left % 60}s" if time_left > 60 else f"{time_left}s", inline=False)
        if show_available:
            embed.add_field(name=f"{EMOJI_ORB} Available Quests", value=f"{len(self.quests)}", inline=True)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        embed.set_image(url=QUEST_IMAGE_URL)
        return embed

    async def start_callback(self, interaction: discord.Interaction):
        if not self.selected_quest:
            await interaction.response.send_message(f"{EMOJI_ERROR} Please select a quest first.", ephemeral=True)
            return
        can_proceed, msg = await self.bot.check_quest_limit(self.user_id)
        if not can_proceed:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        tokens = load_tokens()
        token_data = tokens.get(self.user_id)
        if not token_data:
            await interaction.response.send_message(f"{EMOJI_ERROR} Token not found. Please link your account again.", ephemeral=True)
            return
        token = token_data.get("token")
        username = token_data.get("username", "Unknown")
        discord_id = token_data.get("discord_id")
        if discord_id:
            in_guild, gmsg = await self.bot.check_token_account_in_guild(discord_id)
            if not in_guild:
                await interaction.response.send_message(gmsg, ephemeral=True)
                return
        await self.bot.increment_total_attempts(self.user_id)
        self.disable_all_items()
        # Store the interaction and message for later edits
        self._interaction = interaction
        # We already have self.message from the initial send, so we'll edit that.
        # Update the view to disable items
        if self.message:
            await self.message.edit(view=self)
            await interaction.response.defer()
        else:
            await interaction.response.edit_message(view=self)
        # Build initial progress embed
        embed = self.bot.build_quest_progress_embed(
            username,
            get_quest_name(self.selected_quest),
            0,
            get_seconds_needed(self.selected_quest),
            self.selected_quest,
            interaction.user
        )
        # Update the message with the progress embed
        if self.message:
            await self.message.edit(embed=embed)
        else:
            await interaction.edit_original_response(embed=embed)
        # Start the quest process
        asyncio.create_task(self.process_quest(interaction, token, username, self.selected_quest))

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def process_quest(self, interaction: discord.Interaction, token: str, username: str, quest: dict):
        # We'll keep a reference to the message for editing
        try:
            async def progress_callback(quest_name, progress, total, quest_obj):
                embed = self.bot.build_quest_progress_embed(
                    username,
                    quest_name,
                    progress,
                    total,
                    quest_obj,
                    interaction.user
                )
                # Edit the stored message directly
                if self.message:
                    try:
                        await self.message.edit(embed=embed)
                    except Exception as e:
                        log(f"Failed to edit message in progress: {e}", "warn")
                        # Fallback: try to edit original response
                        await interaction.edit_original_response(embed=embed)

            completer = QuestAutocompleter(token, self.user_id, username, bot.build_number,
                                           user=interaction.user, bot_loop=asyncio.get_event_loop())
            completer.on_progress = progress_callback
            await completer.complete_single_quest(quest)
            # Final embed
            final_embed = discord.Embed(
                title=f"{EMOJI_TICK} Quest Completed!",
                description=f"**{get_quest_name(quest)}**",
                color=discord.Color.green()
            )
            final_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            final_embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
            final_embed.set_image(url=QUEST_IMAGE_URL)
            if self.message:
                await self.message.edit(embed=final_embed)
            else:
                await interaction.edit_original_response(embed=final_embed)
            await self.bot.increment_quest_count(self.user_id)
            try:
                await interaction.followup.send(f"{EMOJI_TICK} ✅ Completed quest: **{get_quest_name(quest)}**", ephemeral=True)
            except:
                pass
        except Exception as e:
            log(f"Error processing single quest for {self.user_id}: {e}", "error")
            try:
                await interaction.followup.send(f"{EMOJI_ERROR} An error occurred: {str(e)}", ephemeral=True)
            except:
                pass


# ── Modals ───────────────────────────────────────────────────────────────────────────
class TokenModal(discord.ui.Modal, title="Link Your Discord Account"):
    token = discord.ui.TextInput(
        label="Discord Token",
        placeholder="Enter your Discord token here...",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=50,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        token = self.token.value.strip()
        user_id = str(interaction.user.id)
        api = DiscordAPI(token, bot.build_number)
        valid, user_data = api.validate_token()
        if not valid:
            embed = discord.Embed(
                title=f"{EMOJI_ERROR} Invalid Token",
                description="The provided token is invalid or expired.",
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        token_user_id = user_data.get('id')
        if token_user_id:
            in_guild, gmsg = await bot.check_token_account_in_guild(token_user_id)
            if not in_guild:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Account Not in Required Server",
                    description=gmsg,
                    color=discord.Color.red()
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await interaction.followup.send(embed=embed, ephemeral=True)
                try:
                    await interaction.user.send(gmsg)
                except:
                    pass
                return
        tokens = load_tokens()
        tokens[user_id] = {
            "token": token,
            "username": user_data.get("username", "Unknown"),
            "discord_id": user_data.get("id", user_id),
            "linked_at": datetime.now().isoformat()
        }
        save_tokens(tokens)
        embed = discord.Embed(
            title=f"{EMOJI_TICK} Account Linked Successfully!",
            description=f"Your Discord account **{user_data.get('username')}** has been linked.",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Username", value=user_data.get("username", "Unknown"), inline=True)
        embed.add_field(name="User ID", value=user_data.get("id", "Unknown"), inline=True)
        embed.add_field(name="📌 Next Step", value=f"Use `/quest` or `;quest` to select a quest! {EMOJI_QUESTS}", inline=False)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.followup.send(embed=embed, ephemeral=True)
        log(f"User {interaction.user.name} linked account {user_data.get('username')}", "ok")


class LinkButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label=f"🔗 Click Here to Link Your Account", style=discord.ButtonStyle.primary, custom_id="link_button")
    async def link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TokenModal())


# ── Slash Commands ────────────────────────────────────────────────────────────────────

# Token commands
@bot.tree.command(name="link", description="Link your Discord user token")
async def link(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())


@bot.tree.command(name="unlink", description="Remove your saved token")
async def unlink(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Not Linked",
            description="You don't have a linked account.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    bot.remove_from_queue(user_id)
    username = tokens[user_id].get("username", "Unknown")
    del tokens[user_id]
    save_tokens(tokens)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Unlinked",
        description=f"Account **{username}** has been unlinked.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="tokencheck", description="Check if your token is still valid")
async def tokencheck(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Not Linked",
            description="You haven't linked your account yet.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    token = tokens[user_id].get("token")
    api = DiscordAPI(token, bot.build_number)
    valid, user_data = api.validate_token()
    if valid:
        embed = discord.Embed(
            title=f"{EMOJI_TICK} Token Valid",
            description=f"Your token is valid for **{user_data.get('username')}**.",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Token Invalid",
            description="Your token is no longer valid. Please re-link with `/link`.",
            color=discord.Color.red()
        )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# Quest commands
@bot.tree.command(name="quest", description="Select and complete one quest (non-premium: 2/day)")
async def quest_slash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet. Use `/link`.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    token_data = tokens[user_id]
    token = token_data.get("token")
    username = token_data.get("username", "Unknown")
    discord_id = token_data.get("discord_id")
    if discord_id:
        in_guild, gmsg = await bot.check_token_account_in_guild(discord_id)
        if not in_guild:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Account Not in Required Server",
                description=gmsg,
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            try:
                await interaction.user.send(gmsg)
            except:
                pass
            return
    can_proceed, msg = await bot.check_quest_limit(user_id)
    if not can_proceed:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Quest Limit Reached",
            description=msg,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    completer = QuestAutocompleter(token, user_id, username, bot.build_number)
    quests = completer.fetch_quests()
    available = []
    for q in quests:
        if is_completed(q):
            continue
        expires = get_expires_at(q)
        if expires:
            try:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if exp_dt <= datetime.now(timezone.utc):
                    continue
            except:
                pass
        if is_completable(q):
            available.append(q)
    if not available:
        embed = discord.Embed(
            title=f"{EMOJI_QUESTS} No Quests Available",
            description="You have no quests available to complete right now.",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    view = QuestSelectionView(user_id, available, bot)
    embed = view.build_detail_embed(available[0], show_available=True)
    await interaction.response.send_message(embed=embed, view=view)
    # Store the message object for editing
    view.message = await interaction.original_response()
    view.is_slash = True
    view._interaction = interaction


@bot.tree.command(name="questall", description="Complete all quests at once (premium only)")
async def questall(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tokens = load_tokens()
    await interaction.response.defer()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet. Use `/link`.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    # Premium check
    if not bot.is_premium(user_id):
        embed = discord.Embed(
            title=f"{EMOJI_PREMIUM} Premium Required",
            description="This command is for **premium users only**.\nUse `/quest` or `;quest` to complete quests individually (2/day).",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    token_data = tokens[user_id]
    username = token_data.get("username", "Unknown")
    discord_id = token_data.get("discord_id")
    if discord_id:
        in_guild, gmsg = await bot.check_token_account_in_guild(discord_id)
        if not in_guild:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Account Not in Required Server",
                description=gmsg,
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            try:
                await interaction.user.send(gmsg)
            except:
                pass
            return
    if user_id in bot.active_users:
        embed = discord.Embed(
            title=f"{EMOJI_LOADING} Already Processing",
            description="Your quests are already being processed.",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    if user_id in bot.queue:
        position = bot.queue.index(user_id) + 1
        embed = discord.Embed(
            title=f"{EMOJI_LOADING} Already in Queue",
            description=f"You are at position **#{position}**.",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    token = token_data.get("token")
    api = DiscordAPI(token, bot.build_number)
    valid, _ = api.validate_token()
    if not valid:
        embed = discord.Embed(
            title=f"{EMOJI_ERROR} Token Expired",
            description="Your token is invalid. Use `/link` to update it.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    bot.add_to_queue(user_id)
    position = bot.queue.index(user_id) + 1
    embed = discord.Embed(
        title=f"{EMOJI_QUESTS} Quest Completion Started",
        description=f"{EMOJI_LOADING} Starting quest completion...",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(
        name="📍 Queue Position",
        value=f"#{position}" + ("" if position == 1 else f" (Waiting for {position-1} user(s) ahead)"),
        inline=True
    )
    embed.add_field(
        name="⏱️ Estimated Wait",
        value=f"~{position * 5} minutes" if position > 1 else "Starting soon...",
        inline=True
    )
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.followup.send(embed=embed)
    msg = await interaction.original_response()
    bot.user_messages[user_id] = (msg.channel.id, msg.id)
    user = await bot.fetch_user(int(user_id))
    if user:
        await user.send(embed=embed)


@bot.tree.command(name="status", description="View your quest status")
async def status_slash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tokens = load_tokens()
    await interaction.response.defer()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet. Use `/link`.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    token = tokens[user_id].get("token")
    username = tokens[user_id].get("username", "Unknown")
    completer = QuestAutocompleter(token, user_id, username, build_number=bot.build_number)
    status = completer.get_quests_status()
    embed = build_questlist_embed(username, status, user=interaction.user)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="stats", description="Show your total quest stats (attempts & successes)")
async def stats_slash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    stats = bot.get_user_stats(user_id)
    embed = discord.Embed(
        title=f"{EMOJI_QUESTS} Quest Stats",
        description=f"**Total Attempts:** {stats['total_attempts']}\n**Total Successful:** {stats['total_success']}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="questlist", description="View all your quests & status")
async def questlist(interaction: discord.Interaction):
    await status_slash(interaction)


@bot.tree.command(name="autoquest", description="Auto-complete new quests as they drop")
async def autoquest(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    settings = load_settings()
    if "autoquest" not in settings:
        settings["autoquest"] = {}
    current = settings["autoquest"].get(user_id, False)
    new_value = not current
    settings["autoquest"][user_id] = new_value
    save_settings(settings)
    bot.settings = settings
    status = "enabled" if new_value else "disabled"
    embed = discord.Embed(
        title=f"{EMOJI_QUESTS} AutoQuest",
        description=f"Auto‑complete is now **{status}**.",
        color=discord.Color.green() if new_value else discord.Color.red()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="stop", description="Stop the currently running quest completion")
async def stop_slash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You don't have a linked account.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await bot.stop_questing(user_id)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Quest Stopped",
        description="Your quest completion has been stopped.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# Premium & Staff commands
@bot.tree.command(name="premium", description="Check your premium status")
async def premium(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    is_prem = bot.is_premium(user_id)
    embed = discord.Embed(
        title=f"{EMOJI_PREMIUM} Premium Status",
        description=f"You are **{'premium' if is_prem else 'not premium'}**.",
        color=discord.Color.gold() if is_prem else discord.Color.light_grey()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="grant", description="Grant premium to a user (admin+)")
@app_commands.default_permissions(administrator=True)
async def grant(interaction: discord.Interaction, user: discord.Member):
    if not await bot.is_staff(interaction):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Permission Denied",
            description="You need the staff role or be the bot owner to use this command.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    bot.set_premium(str(user.id), True)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Premium Granted",
        description=f"**{user.display_name}** now has premium access.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="revoke", description="Remove premium from a user (staff)")
@app_commands.default_permissions(administrator=True)
async def revoke(interaction: discord.Interaction, user: discord.Member):
    if not await bot.is_staff(interaction):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Permission Denied",
            description="You need the staff role or be the bot owner to use this command.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    bot.set_premium(str(user.id), False)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Premium Revoked",
        description=f"**{user.display_name}** no longer has premium access.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="role", description="Set staff role (owner/extraowner/admin)")
@app_commands.default_permissions(administrator=True)
async def role(interaction: discord.Interaction, role: discord.Role):
    if not interaction.guild:
        embed = discord.Embed(
            title=f"{EMOJI_ERROR} Guild Only",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    if not await bot.is_staff(interaction):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Permission Denied",
            description="You need the staff role or be the bot owner to use this command.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    bot.set_staff_role(interaction.guild.id, role.id)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Staff Role Set",
        description=f"Staff role set to **{role.name}**.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="unrole", description="Remove staff role")
@app_commands.default_permissions(administrator=True)
async def unrole(interaction: discord.Interaction):
    if not interaction.guild:
        embed = discord.Embed(
            title=f"{EMOJI_ERROR} Guild Only",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    if not await bot.is_staff(interaction):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Permission Denied",
            description="You need the staff role or be the bot owner to use this command.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    bot.remove_staff_role(interaction.guild.id)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Staff Role Removed",
        description="Staff role has been removed.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed)


# Announce command
@bot.tree.command(name="announce", description="Send announcement to all members (owner only)")
async def announce_slash(interaction: discord.Interaction, message: str, attachment: discord.Attachment = None):
    await bot.announce(interaction, message, attachment)


# Utility commands
@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title=f"{EMOJI_DISCORD} Pong!",
        description=f"Latency: **{latency}ms**",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="You're already here")
async def help_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"{EMOJI_HELPY} Metal Quest Completer - Help",
        description="Here's everything I can do",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(
        name=f"{EMOJI_DISCORD} Token",
        value="`/link` / `;link` – Link your Discord user token\n`/unlink` / `;unlink` – Remove your saved token\n`/tokencheck` / `;tokencheck` – Check if your token is still valid",
        inline=False
    )
    embed.add_field(
        name=f"{EMOJI_QUESTS} Quests",
        value="`/quest` / `;quest` – Select and complete one quest (2/day for non‑premium)\n`/questall` / `;questall` – Complete all quests at once **premium only**\n`/status` / `;status` – View your current quest status\n`/stats` / `;stats` – View your total quest attempts & successes\n`/questlist` / `;questlist` – Alias for `/status`\n`/autoquest` / `;autoquest` – Auto‑complete new quests as they drop\n`/stop` / `;stop` – Stop the currently running quest completion",
        inline=False
    )
    embed.add_field(
        name=f"{EMOJI_PREMIUM} Premium & Staff",
        value="`/premium` / `;premium` – Check your premium status\n`/grant` / `;grant` – Grant premium (admin+)\n`/revoke` / `;revoke` – Remove premium (staff)\n`/role` / `;role` – Set staff role\n`/unrole` / `;unrole` – Remove staff role",
        inline=False
    )
    embed.add_field(
        name=f"{EMOJI_EVENT} Announce",
        value="`/announce` / `;announce` – Send a message to all members (owner only)",
        inline=False
    )
    embed.add_field(
        name=f"{EMOJI_DEV} Utility",
        value="`/ping` / `;ping` – Check bot latency\n`/help` / `;help` – You're already here",
        inline=False
    )
    embed.set_footer(text="Prefix: ; • Metal Quest Completer • Developed by abubakarmalikgul")
    await interaction.response.send_message(embed=embed)


# ── Prefix Commands ───────────────────────────────────────────────────────────────────
@bot.command(name='help')
async def prefix_help(ctx):
    embed = discord.Embed(
        title=f"{EMOJI_HELPY} Metal Quest Completer - Help",
        description="Here's everything I can do",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(
        name=f"{EMOJI_DISCORD} Token",
        value="`;link` – Link your Discord user token\n`;unlink` – Remove your saved token\n`;tokencheck` – Check if your token is still valid",
        inline=False
    )
    embed.add_field(
        name=f"{EMOJI_QUESTS} Quests",
        value="`;quest` – Select and complete one quest (2/day for non‑premium)\n`;questall` – Complete all quests at once **premium only**\n`;status` – View your current quest status\n`;stats` – View your total quest attempts & successes\n`;questlist` – Alias for `;status`\n`;autoquest` – Auto‑complete new quests as they drop\n`;stop` – Stop the currently running quest completion",
        inline=False
    )
    embed.add_field(
        name=f"{EMOJI_PREMIUM} Premium & Staff",
        value="`;premium` – Check your premium status\n`;grant` – Grant premium (admin+)\n`;revoke` – Remove premium (staff)\n`;role` – Set staff role\n`;unrole` – Remove staff role",
        inline=False
    )
    embed.add_field(
        name=f"{EMOJI_EVENT} Announce",
        value="`;announce` – Send a message to all members (owner only)",
        inline=False
    )
    embed.add_field(
        name=f"{EMOJI_DEV} Utility",
        value="`;ping` – Check bot latency\n`;help` – You're already here",
        inline=False
    )
    embed.set_footer(text="Prefix: ; • Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='link')
async def prefix_link(ctx):
    embed = discord.Embed(
        title=f"{EMOJI_DISCORD} Link Your Discord Account",
        description="Click the button below to enter your token.",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(
        name="📌 How to get your token",
        value="1. Open Discord in your browser\n2. Press `Ctrl+Shift+I` (Windows) or `Cmd+Option+I` (Mac)\n3. Go to **Application** → **Storage** → **Local Storage** → **https://discord.com**\n4. Find the key `token` and copy its value",
        inline=False
    )
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    view = LinkButton()
    await ctx.send(embed=embed, view=view)


@bot.command(name='unlink')
async def prefix_unlink(ctx):
    user_id = str(ctx.author.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Not Linked",
            description="You don't have a linked account.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    bot.remove_from_queue(user_id)
    username = tokens[user_id].get("username", "Unknown")
    del tokens[user_id]
    save_tokens(tokens)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Unlinked",
        description=f"Account **{username}** has been unlinked.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='tokencheck')
async def prefix_tokencheck(ctx):
    user_id = str(ctx.author.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Not Linked",
            description="You haven't linked your account yet.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    token = tokens[user_id].get("token")
    api = DiscordAPI(token, bot.build_number)
    valid, user_data = api.validate_token()
    if valid:
        embed = discord.Embed(
            title=f"{EMOJI_TICK} Token Valid",
            description=f"Your token is valid for **{user_data.get('username')}**.",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Token Invalid",
            description="Your token is no longer valid. Please re-link with `;link`.",
            color=discord.Color.red()
        )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='quest')
async def prefix_quest(ctx):
    user_id = str(ctx.author.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet. Use `;link`.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    token_data = tokens[user_id]
    token = token_data.get("token")
    username = token_data.get("username", "Unknown")
    discord_id = token_data.get("discord_id")
    if discord_id:
        in_guild, gmsg = await bot.check_token_account_in_guild(discord_id)
        if not in_guild:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Account Not in Required Server",
                description=gmsg,
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            try:
                await ctx.author.send(gmsg)
            except:
                pass
            return
    can_proceed, msg = await bot.check_quest_limit(user_id)
    if not can_proceed:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Quest Limit Reached",
            description=msg,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    completer = QuestAutocompleter(token, user_id, username, bot.build_number)
    quests = completer.fetch_quests()
    available = []
    for q in quests:
        if is_completed(q):
            continue
        expires = get_expires_at(q)
        if expires:
            try:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if exp_dt <= datetime.now(timezone.utc):
                    continue
            except:
                pass
        if is_completable(q):
            available.append(q)
    if not available:
        embed = discord.Embed(
            title=f"{EMOJI_QUESTS} No Quests Available",
            description="You have no quests available to complete right now.",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    view = QuestSelectionView(user_id, available, bot)
    embed = view.build_detail_embed(available[0], show_available=True)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg
    view.is_slash = False
    view._interaction = None


@bot.command(name='status')
async def prefix_status(ctx):
    user_id = str(ctx.author.id)
    tokens = load_tokens()
    await ctx.typing()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet. Use `;link`.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    token = tokens[user_id].get("token")
    username = tokens[user_id].get("username", "Unknown")
    completer = QuestAutocompleter(token, user_id, username, build_number=bot.build_number)
    status = completer.get_quests_status()
    embed = build_questlist_embed(username, status, user=ctx.author)
    await ctx.send(embed=embed)


@bot.command(name='stats')
async def prefix_stats(ctx):
    user_id = str(ctx.author.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    stats = bot.get_user_stats(user_id)
    embed = discord.Embed(
        title=f"{EMOJI_QUESTS} Quest Stats",
        description=f"**Total Attempts:** {stats['total_attempts']}\n**Total Successful:** {stats['total_success']}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='questlist')
async def prefix_questlist(ctx):
    await prefix_status(ctx)


@bot.command(name='questall', aliases=['start'])
async def prefix_questall(ctx):
    user_id = str(ctx.author.id)
    tokens = load_tokens()
    await ctx.typing()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet. Use `;link`.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    # Premium check
    if not bot.is_premium(user_id):
        embed = discord.Embed(
            title=f"{EMOJI_PREMIUM} Premium Required",
            description="This command is for **premium users only**.\nUse `;quest` to complete quests individually (2/day).",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    token_data = tokens[user_id]
    username = token_data.get("username", "Unknown")
    discord_id = token_data.get("discord_id")
    if discord_id:
        in_guild, gmsg = await bot.check_token_account_in_guild(discord_id)
        if not in_guild:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Account Not in Required Server",
                description=gmsg,
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            try:
                await ctx.author.send(gmsg)
            except:
                pass
            return
    if user_id in bot.active_users:
        embed = discord.Embed(
            title=f"{EMOJI_LOADING} Already Processing",
            description="Your quests are already being processed.",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    if user_id in bot.queue:
        position = bot.queue.index(user_id) + 1
        embed = discord.Embed(
            title=f"{EMOJI_LOADING} Already in Queue",
            description=f"You are at position **#{position}**.",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    token = token_data.get("token")
    api = DiscordAPI(token, bot.build_number)
    valid, _ = api.validate_token()
    if not valid:
        embed = discord.Embed(
            title=f"{EMOJI_ERROR} Token Expired",
            description="Your token is invalid. Use `;link` to update it.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    bot.add_to_queue(user_id)
    position = bot.queue.index(user_id) + 1
    embed = discord.Embed(
        title=f"{EMOJI_QUESTS} Quest Completion Started",
        description=f"{EMOJI_LOADING} Starting quest completion...",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(
        name="📍 Queue Position",
        value=f"#{position}" + ("" if position == 1 else f" (Waiting for {position-1} user(s) ahead)"),
        inline=True
    )
    embed.add_field(
        name="⏱️ Estimated Wait",
        value=f"~{position * 5} minutes" if position > 1 else "Starting soon...",
        inline=True
    )
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    msg = await ctx.send(embed=embed)
    bot.user_messages[user_id] = (msg.channel.id, msg.id)
    user = await bot.fetch_user(int(user_id))
    if user:
        await user.send(embed=embed)


@bot.command(name='stop')
async def prefix_stop(ctx):
    user_id = str(ctx.author.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You don't have a linked account.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    await bot.stop_questing(user_id)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Quest Stopped",
        description="Your quest completion has been stopped.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='autoquest')
async def prefix_autoquest(ctx):
    user_id = str(ctx.author.id)
    tokens = load_tokens()
    if user_id not in tokens:
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Account Not Linked",
            description="You haven't linked your account yet.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    settings = load_settings()
    if "autoquest" not in settings:
        settings["autoquest"] = {}
    current = settings["autoquest"].get(user_id, False)
    new_value = not current
    settings["autoquest"][user_id] = new_value
    save_settings(settings)
    bot.settings = settings
    status = "enabled" if new_value else "disabled"
    embed = discord.Embed(
        title=f"{EMOJI_QUESTS} AutoQuest",
        description=f"Auto‑complete is now **{status}**.",
        color=discord.Color.green() if new_value else discord.Color.red()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='premium')
async def prefix_premium(ctx):
    user_id = str(ctx.author.id)
    is_prem = bot.is_premium(user_id)
    embed = discord.Embed(
        title=f"{EMOJI_PREMIUM} Premium Status",
        description=f"You are **{'premium' if is_prem else 'not premium'}**.",
        color=discord.Color.gold() if is_prem else discord.Color.light_grey()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='grant')
@commands.has_permissions(administrator=True)
async def prefix_grant(ctx, user: discord.Member):
    if not await bot.is_staff_ctx(ctx):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Permission Denied",
            description="You need the staff role or be the bot owner to use this command.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    bot.set_premium(str(user.id), True)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Premium Granted",
        description=f"**{user.display_name}** now has premium access.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='revoke')
@commands.has_permissions(administrator=True)
async def prefix_revoke(ctx, user: discord.Member):
    if not await bot.is_staff_ctx(ctx):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Permission Denied",
            description="You need the staff role or be the bot owner to use this command.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    bot.set_premium(str(user.id), False)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Premium Revoked",
        description=f"**{user.display_name}** no longer has premium access.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='role')
@commands.has_permissions(administrator=True)
async def prefix_role(ctx, role: discord.Role):
    if not ctx.guild:
        embed = discord.Embed(
            title=f"{EMOJI_ERROR} Guild Only",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    if not await bot.is_staff_ctx(ctx):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Permission Denied",
            description="You need the staff role or be the bot owner to use this command.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    bot.set_staff_role(ctx.guild.id, role.id)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Staff Role Set",
        description=f"Staff role set to **{role.name}**.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='unrole')
@commands.has_permissions(administrator=True)
async def prefix_unrole(ctx):
    if not ctx.guild:
        embed = discord.Embed(
            title=f"{EMOJI_ERROR} Guild Only",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    if not await bot.is_staff_ctx(ctx):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Permission Denied",
            description="You need the staff role or be the bot owner to use this command.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await ctx.send(embed=embed)
        return
    bot.remove_staff_role(ctx.guild.id)
    embed = discord.Embed(
        title=f"{EMOJI_TICK} Staff Role Removed",
        description="Staff role has been removed.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


@bot.command(name='announce')
async def prefix_announce(ctx, *, message: str):
    attachment = None
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
    await bot.announce(ctx, message, attachment)


@bot.command(name='ping')
async def prefix_ping(ctx):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title=f"{EMOJI_DISCORD} Pong!",
        description=f"Latency: **{latency}ms**",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
    await ctx.send(embed=embed)


# ── Error handling ────────────────────────────────────────────────────────────────────
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title=f"{EMOJI_LOADING} Cooldown",
            description=f"Try again in {error.retry_after:.0f}s.",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title=f"{EMOJI_ERROR} Error",
            description=f"{str(error)}",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Metal Quest Completer • Developed by abubakarmalikgul")
        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            await interaction.followup.send(embed=embed, ephemeral=True)
        traceback.print_exc()


# ── Main entry point ──────────────────────────────────────────────────────────────────
def main():
    # ADD THIS LINE RIGHT HERE:
    keep_alive()

    print(f"""
{Colors.BOLD}{Colors.CYAN}╔═══════════════════════════════════════════════════════════════╗
║            Metal Quest Completer - Discord Quest Bot            ║
║         Auto-scan · Auto-enroll · Auto-complete        ║
║             Developed by abubakarmalikgul                     ║
╚═══════════════════════════════════════════════════════════════╝{Colors.RESET}
""")
    queue_data = load_queue()
    bot.queue = queue_data.get("queue", [])
    log(f"Loaded {len(bot.queue)} users from queue", "info")
    load_tokens()
    
    # Check for the token in Render Environment Variables first
    bot_token = os.environ.get("DISCORD_TOKEN")
    
    # Fallbacks for local testing
    if not bot_token and len(sys.argv) > 1:
        bot_token = sys.argv[1].strip()
    elif not bot_token and os.path.exists(".bot_token"):
        with open(".bot_token", "r") as f:
            bot_token = f.read().strip()
        log("Read bot token from .bot_token", "info")
        
    # If still no token is found, exit safely instead of crashing on input()
    if not bot_token:
        log("No DISCORD_TOKEN found - set it in Render env vars.", "error")
        sys.exit(1)

    try:
        bot.run(bot_token)
    except KeyboardInterrupt:
        print()
        log("Bot stopped.", "info")
        sys.exit(0)
    except Exception as e:
        log(f"Bot error: {e}", "error")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
