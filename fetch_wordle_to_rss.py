import os
import sys
import datetime as _dt
from email.utils import format_datetime

import requests
import xml.etree.ElementTree as ET


WORDLE_URL = "https://www.nytimes.com/games/wordle/index.html"
WORDLE_API_TEMPLATE = "https://www.nytimes.com/svc/wordle/v2/{date}.json"
FEED_PATH = "wordle_feed.xml"


def _load_or_create_feed(path: str) -> ET.ElementTree:
    """
    Load an existing RSS feed from ``path`` or create a new one.
    Returns an ElementTree whose root is the <rss> element.
    """
    if os.path.exists(path):
        tree = ET.parse(path)
        root = tree.getroot()
    else:
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = "Daily Wordle feed"
        ET.SubElement(channel, "link").text = WORDLE_URL
        ET.SubElement(channel, "description").text = (
            "Automatically collected links to the New York Times Wordle puzzle."
        )
        tree = ET.ElementTree(root)

    # Ensure basic structure exists even for an existing feed.
    channel = root.find("channel")
    if channel is None:
        channel = ET.SubElement(root, "channel")

    if channel.find("title") is None:
        ET.SubElement(channel, "title").text = "Daily Wordle feed"
    if channel.find("link") is None:
        ET.SubElement(channel, "link").text = WORDLE_URL
    if channel.find("description") is None:
        ET.SubElement(channel, "description").text = (
            "Automatically collected links to the New York Times Wordle puzzle."
        )

    return tree


def _guid_for_date(day: _dt.date) -> str:
    """Return a GUID string for a specific Wordle date."""
    return f"wordle-{day.isoformat()}"


def _fetch_today_answer(today: _dt.date | None = None) -> str | None:
    """
    Query the official NYT Wordle JSON endpoint for today's answer.

    Returns the solution as an uppercase string, or None if it cannot be
    retrieved for any reason (network error, unexpected payload, etc.).
    """
    if today is None:
        today = _dt.date.today()

    url = WORDLE_API_TEMPLATE.format(date=today.isoformat())
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    answer = data.get("solution")
    if isinstance(answer, str):
        return answer.upper()
    return None


def _ensure_last_build_date(channel: ET.Element) -> ET.Element:
    """
    Ensure a <lastBuildDate> element exists directly after the core metadata
    (title/link/description) at the top of the channel, and return it.
    """
    last_build = channel.find("lastBuildDate")

    # Remove it temporarily so we can reinsert in the right place.
    if last_build is not None:
        channel.remove(last_build)
    else:
        last_build = ET.Element("lastBuildDate")

    children = list(channel)
    insert_idx = 0
    for idx, child in enumerate(children):
        if child.tag in {"description"}:
            insert_idx = idx + 1

    channel.insert(insert_idx, last_build)
    return last_build


def add_wordle_to_feed_for_date(
    target_date: _dt.date | None = None,
    feed_path: str = FEED_PATH,
    wordle_url: str = WORDLE_URL,
) -> None:
    """
    Fetch the current day's Wordle page and append an item to the RSS feed.

    - Requests the HTML of ``wordle_url``.
    - Ensures an RSS 2.0 feed exists at ``feed_path``.
    - Adds a new <item> for today's date if one does not already exist.
    """
    if target_date is None:
        target_date = _dt.date.today()

    tree = _load_or_create_feed(feed_path)
    root = tree.getroot()
    channel = root.find("channel")
    assert channel is not None

    guid_value = _guid_for_date(target_date)

    # Do not duplicate an entry for the same day.
    existing_item = None
    for item in channel.findall("item"):
        guid = item.find("guid")
        if guid is not None and guid.text == guid_value:
            existing_item = item
            break

    if existing_item is not None:
        # Already present; nothing to do.
        return

    now = _dt.datetime.now(_dt.timezone.utc)

    # Best-effort attempt to fetch answer for the requested date.
    answer = _fetch_today_answer(target_date)

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = f"Wordle for {target_date.isoformat()}"
    ET.SubElement(item, "link").text = wordle_url
    ET.SubElement(item, "guid").text = guid_value
    ET.SubElement(item, "pubDate").text = format_datetime(now)
    description_text = "Link to the New York Times Wordle puzzle for this date."
    if answer:
        description_text += f" Answer: {answer}"
        ET.SubElement(item, "answer").text = answer
    ET.SubElement(item, "description").text = description_text

    # Update channel metadata, keeping <lastBuildDate> with the other metadata
    last_build = _ensure_last_build_date(channel)
    last_build.text = format_datetime(now)

    tree.write(feed_path, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    # Optional CLI: python fetch_wordle_to_rss.py [YYYY-MM-DD]
    cli_date: _dt.date | None = None
    if len(sys.argv) >= 2:
        try:
            cli_date = _dt.date.fromisoformat(sys.argv[1])
        except ValueError:
            raise SystemExit(
                "Invalid date format. Use YYYY-MM-DD, e.g. 2024-01-15."
            ) from None

    add_wordle_to_feed_for_date(cli_date)

