
import os
import time
import json
import requests
from pathlib import Path
from urllib.parse import quote
from requests.exceptions import RequestException


GRAPH_URL = "https://graph.instagram.com"

STATE_FILE = Path("state.json")
LINKS_FILE = Path("links.txt")

MAX_CONTAINER_CHECKS = 20
CONTAINER_CHECK_INTERVAL = 30
PUBLISH_RETRIES = 3


def get_reels():
    folder = Path("images")

    if not folder.exists():
        raise RuntimeError("images folder does not exist.")

    files = [
        file
        for file in folder.iterdir()
        if file.is_file()
        and file.suffix.lower() == ".mp4"
    ]

    return sorted(files, key=lambda file: file.name.lower())


def load_state():
    if not STATE_FILE.exists():
        return {"posted_files": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        posted = state.get("posted_files", [])

        if not isinstance(posted, list):
            raise ValueError("posted_files must be a list.")

        return {"posted_files": posted}

    except Exception as exc:
        # Do not silently reset state; that could cause duplicates.
        raise RuntimeError(
            f"Could not safely read {STATE_FILE}: {exc}"
        ) from exc


def save_state(posted_files):
    temp_file = STATE_FILE.with_suffix(".tmp")

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(
            {"posted_files": posted_files},
            f,
            indent=2,
            ensure_ascii=False
        )

    temp_file.replace(STATE_FILE)


def save_link(filename, permalink):
    # Avoid duplicate link entries if the same URL is already saved.
    existing = set()

    if LINKS_FILE.exists():
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            existing = {
                line.strip()
                for line in f
                if line.strip()
            }

    entry = f"{filename} -> {permalink}"

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
            params={
                "fields": "status_code,status",
                "access_token": token,
            },
            timeout=60,
        )

        response.raise_for_status()
        data = response.json()

        status_code = data.get("status_code")
        status_message = data.get("status", "")

        print(
            f"Container {creation_id} "
            f"check {attempt + 1}/{MAX_CONTAINER_CHECKS}: "
            f"{data}"
        )

        if status_code in ("FINISHED", "PUBLISHED"):
            return

        if status_code in ("ERROR", "EXPIRED"):
            raise RuntimeError(
                f"Instagram container processing failed. "
                f"Container ID={creation_id}; "
                f"status_code={status_code}; "
                f"status={status_message}"
            )

        time.sleep(CONTAINER_CHECK_INTERVAL)

    raise RuntimeError(
        f"Container {creation_id} did not finish in time."
    )


def get_permalink(media_id, token):
    response = requests.get(
        f"{GRAPH_URL}/{media_id}",
        params={
            "fields": "permalink",
            "access_token": token,
        },
        timeout=60,
    )

    if not response.ok:
        print("Permalink API error:", api_error(response))

    response.raise_for_status()

    permalink = response.json().get("permalink")

    if not permalink:
        raise RuntimeError(
            f"Permalink not returned for media ID {media_id}."
        )

    return permalink


def publish_reel(user_id, file_url, caption, token, filename):
    print(f"\nUploading: {filename}")

    # Create a new container for this Reel.
    response = requests.post(
        f"{GRAPH_URL}/{user_id}/media",
        params={
            "media_type": "REELS",
            "video_url": file_url,
            "caption": caption,
            "access_token": token,
        },
        timeout=60,
    )

    if not response.ok:
        print("Container creation error:", api_error(response))

    response.raise_for_status()

    creation_id = response.json().get("id")

    if not creation_id:
        raise RuntimeError(
            f"Container ID missing for {filename}."
        )

    print(f"Container created: {creation_id}")

    wait_for_container(creation_id, token)

    # Retry publish only when the API explicitly rejects the request.
    # A network timeout is ambiguous: Instagram may already have published.
    for attempt in range(1, PUBLISH_RETRIES + 1):
        try:
            response = requests.post(
                f"{GRAPH_URL}/{user_id}/media_publish",
                params={
                    "creation_id": creation_id,
                    "access_token": token,
                },
                timeout=60,
            )

        except RequestException as exc:
            raise RuntimeError(
                f"Publish outcome is uncertain for {filename}. "
                f"Check Instagram before retrying. Details: {exc}"
            ) from exc

        if response.ok:
            media_id = response.json().get("id")

            if not media_id:
                raise RuntimeError(
                    f"Publish response had no media ID: "
                    f"{response.text}"
                )

            print(f"Published Media ID: {media_id}")
            permalink = get_permalink(media_id, token)
            print(f"INSTAGRAM LINK: {permalink}")

            return permalink

        error_data = api_error(response)
        print(
            f"Publish attempt {attempt}/{PUBLISH_RETRIES} failed: "
            f"{error_data}"
        )

        # Do not repeatedly submit a request if the API reports a
        # publishing limit or another non-retryable error.
        try:
            error = error_data.get("error", {})
        except AttributeError:
            error = {}

        error_code = error.get("code")
        error_subcode = error.get("error_subcode")

        if error_code == 9 or error_subcode == 2207042:
            raise RuntimeError(
                "Instagram publishing limit reached. "
                "Stop and try again later."
            )

        if response.status_code not in (429, 500, 502, 503, 504):
            raise RuntimeError(
                f"Instagram rejected publishing for {filename}: "
                f"{error_data}"
            )

        if attempt < PUBLISH_RETRIES:
            time.sleep(30 * attempt)

    raise RuntimeError(
        f"Publish failed after {PUBLISH_RETRIES} attempts: {filename}"
    )


def main():
    token = os.environ["ZINDAGI_ACCESS_TOKEN"]
    user_id = os.environ["ZINDAGI_USER_ID"]
    repository = os.environ["GITHUB_REPOSITORY"]
    branch = os.getenv("GITHUB_REF_NAME", "main")

    caption = "#あらゆる追いかけっこを繰り広げる"

    print("\n==========================================")
    print("Testing Instagram account...")
    print("==========================================")

    test_response = requests.get(
        f"{GRAPH_URL}/me",
        params={
            "fields": "user_id,username",
            "access_token": token,
        },
        timeout=60,
    )

    print("Instagram account response:", test_response.text)
    test_response.raise_for_status()

    reels = get_reels()

    if not reels:
        raise RuntimeError("No MP4 files found in images folder.")

    state = load_state()
    posted_files = state["posted_files"]

    pending_reels = [
        reel for reel in reels
        if reel.name not in posted_files
    ]

    print(f"Total MP4 Reels: {len(reels)}")
    print(f"Already posted: {len(posted_files)}")
    print(f"Pending Reels: {len(pending_reels)}")

    if not pending_reels:
        print("All current Reels have already been posted.")
        return

    failed_files = []

    for index, reel in enumerate(pending_reels, start=1):
        safe_filename = quote(reel.name, safe="")

        file_url = (
            f"https://raw.githubusercontent.com/"
            f"{repository}/{quote(branch, safe='')}/"
            f"images/{safe_filename}"
        )

        print("\n==========================================")
        print(f"REEL {index}/{len(pending_reels)}")
        print(f"FILE: {reel.name}")
        print("==========================================")

        try:
            permalink = publish_reel(
                user_id,
                file_url,
                caption,
                token,
                reel.name
            )

            # Save permalink first, then mark file as posted.
            save_link(reel.name, permalink)

            if reel.name not in posted_files:
                posted_files.append(reel.name)

            save_state(posted_files)

            print(f"SUCCESS: {reel.name}")
            print(f"LINK: {permalink}")
            print("Link and state saved.")

        except Exception as exc:
            print(f"FAILED: {reel.name}")
            print(f"REASON: {exc}")
            print("Skipping this Reel and continuing.")
            failed_files.append(reel.name)

    print("\n==========================================")
    print(f"Successfully posted: {len(pending_reels) - len(failed_files)}")
    print(f"Failed Reels: {len(failed_files)}")
    print("Instagram links are saved in links.txt.")
    print("==========================================")

    if failed_files:
        print("Failed filenames:")
        for filename in failed_files:
            print(f"- {filename}")


if __name__ == "__main__":
    main()
