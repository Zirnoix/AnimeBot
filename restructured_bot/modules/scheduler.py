# restructured_bot/modules/scheduler.py

from datetime import datetime, timedelta
import pytz
import json
import os

from . import core

SCHEDULE_FILE = os.path.join(core.DATA_DIR, "schedule.json")
TIMEZONE = core.TIMEZONE


def load_schedule() -> list[dict]:
    """Load the full anime schedule from the JSON file."""
    return core.load_json(SCHEDULE_FILE, [])


def save_schedule(schedule: list[dict]) -> None:
    """Save the full anime schedule to the JSON file."""
    core.save_json(SCHEDULE_FILE, schedule)


def update_schedule(animes: list[dict]) -> None:
    """
    Update the schedule file with the upcoming episodes.

    Args:
        animes: List of anime dicts containing airing info.
    """
    schedule = []
    for anime in animes:
        airing_time = datetime.fromtimestamp(anime["airingAt"], tz=pytz.utc).astimezone(TIMEZONE)
        schedule.append({
            "id": anime["id"],
            "title": anime["title"],
            "episode": anime["episode"],
            "airingAt": airing_time.isoformat(),
            "genres": anime.get("genres", []),
            "image": anime.get("image")
        })
    save_schedule(schedule)


def get_today_schedule() -> list[dict]:
    """Return all episodes scheduled for today."""
    schedule = load_schedule()
    today = datetime.now(TIMEZONE).date()
    return [
        ep for ep in schedule
        if datetime.fromisoformat(ep["airingAt"]).astimezone(TIMEZONE).date() == today
    ]


def get_upcoming_schedule(hours_ahead: int = 48) -> list[dict]:
    """Return all episodes airing within the next X hours."""
    now = datetime.now(TIMEZONE)
    future = now + timedelta(hours=hours_ahead)
    return [
        ep for ep in load_schedule()
        if now <= datetime.fromisoformat(ep["airingAt"]).astimezone(TIMEZONE) <= future
    ]
