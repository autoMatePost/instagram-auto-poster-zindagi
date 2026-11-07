import os
import time
import json
import random
import requests

from pathlib import Path
from urllib.parse import quote
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from requests.exceptions import RequestException

GRAPH_URL = "https://graph.instagram.com"
STATE_FILE = Path("state.json")
LINKS_FILE = Path("links.txt")
IST = ZoneInfo("Asia/Kolkata")

START_TIME = dt_time(16, 0)
STOP_TIME = dt_time(20, 0)

MAX_CONTAINER_CHECKS = 20
CONTAINER_CHECK_INTERVAL = 30
PUBLISH_RETRIES = 3
TOTAL_POST_LIMIT = 70


def now_ist():
    return datetime.now(IST)


def get_reels():
    folder = Path("images")
    if not folder.exists():
        raise RuntimeError("images folder does not exist.")

    return sorted(
        [f for f in folder.iterdir()
         if f.is_file() and f.suffix.lower() == ".mp4"],
        key=lambda f: f.name.lower()
    )


def load_state():
    """
    Start a fresh 70-Reel batch if state.json contains only the old
    posted_files history. Old history is intentionally ignored.
    """
    current_files = [f.name for f in get_reels()]

    if not STATE_FILE.exists():
        return {
            "batch_files": current_files,
            "batch_posted_files": [],
            "daily_posts": {}
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            old_state = json.load(f)

        # New batch tracking is authoritative. Legacy posted_files data
        # is deliberately not used for the new 70-Reel batch.
        if "batch_files" not in old_state:
            return {
                "batch_files": current_files,
                "batch_posted_files": [],
                "daily_posts": {}
            }

        batch_files = old_state.get("batch_files", [])
        batch_posted = old_state.get("batch_posted_files", [])
        daily = old_state.get("daily_posts", {})

        if (
            not isinstance(batch_files, list)
            or not isinstance(batch_posted, list)
            or not isinstance(daily, dict)
        ):
            raise ValueError("Invalid new batch state structure.")

        return {
            "batch_files": batch_files,
            "batch_posted_files": batch_posted,
            "daily_posts": daily
        }

    except Exception as exc:
        raise RuntimeError(
            f"Could not read state.json safely: {exc}"
        ) from exc


def save_state(state):
    temp = STATE_FILE.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    temp.replace(STATE_FILE)


def save_link(filename, permalink, media_id=None):
    if permalink:
        entry = f"{filename} -> {permalink}"
    else:
        # Instagram confirmed publishing, but permalink lookup did not
        # return a URL. Store the media ID to prevent duplicate posting.
        entry = f"{filename} -> PUBLISHED; media_id={media_id}; permalink_pending"

    existing = set()
    if LINKS_FILE.exists():
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            existing = {line.strip() for line in f if line.strip()}

    if entry not in existing:
        with open(LINKS_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n")


def api_error(response):
    try:
        return response.json()
    except ValueError:
        return response.text


def wait_for_container(creation_id, token):
    for attempt in range(MAX_CONTAINER_CHECKS):
        response = requests.get(
            f"{GRAPH_URL}/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        status = data.get("status_code")

        print(f"Container check {attempt + 1}: {data}")

        if status in ("FINISHED", "PUBLISHED"):
            return

        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram container failed: {data}")

        time.sleep(CONTAINER_CHECK_INTERVAL)

    raise RuntimeError(f"Container {creation_id} did not finish.")


def get_permalink(media_id, token):
    last_error = None

    for attempt in range(1, 4):
        try:
            response = requests.get(
                f"{GRAPH_URL}/{media_id}",
                params={"fields": "permalink", "access_token": token},
                timeout=60
            )
            response.raise_for_status()
            permalink = response.json().get("permalink")

            if permalink:
                return permalink

            last_error = "Permalink field was empty."

        except (RequestException, ValueError) as exc:
            last_error = str(exc)

        print(f"Permalink lookup attempt {attempt} failed: {last_error}")
        if attempt < 3:
            time.sleep(5)

    return None


def publish_reel(user_id, file_url, caption, token, filename):
    print(f"\nUploading: {filename}")

    response = requests.post(
        f"{GRAPH_URL}/{user_id}/media",
        params={
            "media_type": "REELS",
            "video_url": file_url,
            "caption": caption,
            "access_token": token
        },
        timeout=60
    )

    if not response.ok:
        print("Container creation error:", api_error(response))

    response.raise_for_status()
    creation_id = response.json().get("id")

    if not creation_id:
        raise RuntimeError(f"Container ID missing for {filename}.")

    wait_for_container(creation_id, token)

    for attempt in range(1, PUBLISH_RETRIES + 1):
        try:
            response = requests.post(
                f"{GRAPH_URL}/{user_id}/media_publish",
                params={
                    "creation_id": creation_id,
                    "access_token": token
                },
                timeout=60
            )
        except RequestException as exc:
            raise RuntimeError(
                f"Publish outcome uncertain for {filename}; "
                f"check Instagram before retrying: {exc}"
            ) from exc

        if response.ok:
            media_id = response.json().get("id")
            if not media_id:
                raise RuntimeError(
                    "Instagram returned success but no media ID. "
                    "Check Instagram before retrying this file."
                )

            permalink = get_permalink(media_id, token)
            if permalink:
                print("INSTAGRAM LINK:", permalink)
            else:
                print(
                    "Instagram confirmed publishing, but permalink "
                    "lookup failed. Media ID:", media_id
                )

            # A confirmed media_publish success is treated as posted,
            # even if permalink lookup is temporarily unavailable.
            return media_id, permalink

        error_data = api_error(response)
        print(f"Publish attempt {attempt}: {error_data}")

        error = error_data.get("error", {}) if isinstance(error_data, dict) else {}

        if error.get("code") == 9 or error.get("error_subcode") == 2207042:
            raise RuntimeError("Instagram publishing limit reached.")

        if response.status_code not in (429, 500, 502, 503, 504):
            raise RuntimeError(f"Instagram rejected {filename}: {error_data}")

        if attempt < PUBLISH_RETRIES:
            time.sleep(30 * attempt)

    raise RuntimeError("Publish failed after retries.")


def get_requested_count():
    manual = os.getenv("MANUAL_POST_COUNT", "").strip().upper()
    requested = manual or os.getenv("DAILY_POST_COUNT", "15").strip().upper()

    if requested == "ALL":
        return "ALL"

    try:
        count = int(requested)
    except ValueError:
        raise ValueError("Daily count must be a positive number or ALL.")

    if count < 1:
        raise ValueError("Daily count must be at least 1.")

    return count


def main():
    token = os.environ["ZINDAGI_ACCESS_TOKEN"]
    user_id = os.environ["ZINDAGI_USER_ID"]
    repository = os.environ["GITHUB_REPOSITORY"]
    branch = os.getenv("GITHUB_REF_NAME", "main")

    min_gap = int(os.getenv("MIN_GAP_SECONDS", "120"))
    max_gap = int(os.getenv("MAX_GAP_SECONDS", "360"))

    if min_gap < 120 or max_gap > 360 or max_gap < min_gap:
        raise ValueError("Gap must be between 120 and 360 seconds.")

    current = now_ist()
    today = current.strftime("%Y-%m-%d")

    print("India time:", current.strftime("%Y-%m-%d %H:%M:%S"))
    print("Posting window: 4 PM to 8 PM IST")

    if current.time() < START_TIME or current.time() >= STOP_TIME:
        print("Outside posting window. No Reels will be posted.")
        return

    test = requests.get(
        f"{GRAPH_URL}/me",
        params={"fields": "user_id,username", "access_token": token},
        timeout=60
    )
    print("Instagram account:", test.text)
    test.raise_for_status()

    state = load_state()
    batch_files = state["batch_files"]
    batch_posted_files = state["batch_posted_files"]
    daily_posts = state["daily_posts"]

    total_posted = len(batch_posted_files)
    today_posted = int(daily_posts.get(today, 0))

    if total_posted >= TOTAL_POST_LIMIT:
        print("70 Reels from this batch have been posted. Automation stopped.")
        return

    requested = get_requested_count()
    remaining_batch = TOTAL_POST_LIMIT - total_posted

    pending_names = [
        name for name in batch_files
        if name not in batch_posted_files and (Path("images") / name).is_file()
    ]

    daily_limit = len(pending_names) if requested == "ALL" else requested
    remaining_today = max(0, daily_limit - today_posted)

    if remaining_today == 0:
        print("Today's posting limit already reached.")
        return

    selected_names = pending_names[:min(remaining_today, remaining_batch)]

    print("Files in this batch:", len(batch_files))
    print("MP4 files pending:", len(pending_names))
    print("Successfully posted from this batch:", total_posted)
    print("Posted today:", today_posted)
    print("Today's limit:", daily_limit)
    print("Selected this run:", len(selected_names))

    if not selected_names:
        print("No pending Reels from this batch.")
        return

    success_count = 0
    failed_files = []

    for index, filename in enumerate(selected_names, start=1):
        if now_ist().time() >= STOP_TIME:
            print("8 PM reached. Stopping.")
            break

        reel = Path("images") / filename
        file_url = (
            f"https://raw.githubusercontent.com/{repository}/"
            f"{quote(branch, safe='')}/images/{quote(filename, safe='')}"
        )

        print(f"\nREEL {index}/{len(selected_names)}: {filename}")

        try:
            media_id, permalink = publish_reel(
                user_id,
                file_url,
                "#あらゆる追いかけっこを繰り広げる",
                token,
                filename
            )

            save_link(filename, permalink, media_id)

            if filename not in batch_posted_files:
                batch_posted_files.append(filename)

            daily_posts[today] = int(daily_posts.get(today, 0)) + 1

            save_state({
                "batch_files": batch_files,
                "batch_posted_files": batch_posted_files,
                "daily_posts": daily_posts
            })

            if reel.exists():
                reel.unlink()

            success_count += 1
            print("SUCCESS:", filename)
            print("LINK:", permalink or f"Permalink pending; media ID: {media_id}")
            print("Deleted from images.")

        except Exception as exc:
            print("FAILED:", filename)
            print("REASON:", exc)
            print("Keeping file for a future run.")
            failed_files.append(filename)

        if len(batch_posted_files) >= TOTAL_POST_LIMIT:
            print("70 successful Reels from this batch reached. Stopping permanently.")
            break

        if today_posted + success_count >= daily_limit:
            print("Today's successful-post limit reached.")
            break

        if index < len(selected_names):
            gap = random.randint(min_gap, max_gap)

            now = now_ist()
            stop = datetime.combine(now.date(), STOP_TIME, tzinfo=IST)
            remaining_seconds = (stop - now).total_seconds()

            if remaining_seconds <= gap:
                print("Not enough time for another Reel before 8 PM.")
                break

            print(f"Waiting {gap} seconds before next Reel.")
            time.sleep(gap)

    print("\n========== DAILY SUMMARY ==========")
    print("Successful this run:", success_count)
    print("Failed this run:", len(failed_files))
    print("Successfully posted today:", daily_posts.get(today, 0))
    print("Successfully posted from this batch:", len(batch_posted_files))
    print("Remaining to 70:", max(0, TOTAL_POST_LIMIT - len(batch_posted_files)))
    print("===================================")


if __name__ == "__main__":
    main()
