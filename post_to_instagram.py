import os
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


GRAPH_URL = "https://graph.instagram.com"
IST = ZoneInfo("Asia/Kolkata")


def get_reels():
    folder = Path("images")

    files = [
        file
        for file in folder.iterdir()
        if file.is_file()
        and file.suffix.lower() == ".mp4"
        and file.stem.isdigit()
    ]

    return sorted(
        files,
        key=lambda file: int(file.stem)
    )


def wait_for_container(creation_id, token):

    for attempt in range(20):

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

        print(
            f"Container status "
            f"{attempt + 1}/20: {data}"
        )

        status_code = data.get("status_code")

        if status_code == "FINISHED":
            return

        if status_code in ("ERROR", "EXPIRED"):
            raise RuntimeError(
                f"Instagram container failed: {data}"
            )

        time.sleep(30)

    raise RuntimeError(
        "Instagram container did not finish."
    )


def publish_reel(
    user_id,
    file_url,
    caption,
    token,
    filename
):

    print(f"\nUploading: {filename}")

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
        print("\nInstagram API Error:")
        print(response.text)

    response.raise_for_status()

    creation_id = response.json().get("id")

    if not creation_id:
        raise RuntimeError(
            f"Container ID missing for {filename}"
        )

    print(
        f"Container created: {creation_id}"
    )

    wait_for_container(
        creation_id,
        token
    )

    response = requests.post(
        f"{GRAPH_URL}/{user_id}/media_publish",
        params={
            "creation_id": creation_id,
            "access_token": token,
        },
        timeout=60,
    )

    if not response.ok:
        print("\nPublish Error:")
        print(response.text)

    response.raise_for_status()

    print(f"SUCCESS: {filename}")


def get_batch():

    schedule = os.getenv(
        "SCHEDULE_TIME",
        ""
    )

    # 06:00 AM IST
    if schedule == "30 0 2 10 *":
        return 0, 12, "06:00 AM - 08:00 AM"

    # 12:00 PM IST
    if schedule == "30 6 2 10 *":
        return 12, 24, "12:00 PM - 02:00 PM"

    # 06:00 PM IST
    if schedule == "30 12 2 10 *":
        return 24, 36, "06:00 PM - 08:00 PM"

    # Manual workflow
    manual_start = int(
        os.getenv("BATCH_START", "0")
    )

    manual_count = int(
        os.getenv("POST_COUNT", "12")
    )

    return (
        manual_start,
        manual_start + manual_count,
        "MANUAL"
    )


def main():

    # ==============================
    # ENVIRONMENT VARIABLES
    # ==============================

    token = os.environ[
        "ZINDAGI_ACCESS_TOKEN"
    ]

    user_id = os.environ[
        "ZINDAGI_USER_ID"
    ]

    # ==============================
    # FIXED CAPTION
    # ==============================

    caption = (
        "#あらゆる追いかけっこを繰り広げる "
        "#reel #japan #america #usa #video"
    )

    # ==============================
    # INSTAGRAM ACCOUNT TEST
    # ==============================

    print(
        "\n=========================================="
    )

    print(
        "Testing Instagram account..."
    )

    print(
        "=========================================="
    )

    test_response = requests.get(
        f"{GRAPH_URL}/me",
        params={
            "fields": "user_id,username",
            "access_token": token,
        },
        timeout=60,
    )

    print(
        "\nInstagram account response:"
    )

    print(
        test_response.text
    )

    if not test_response.ok:
        raise RuntimeError(
            "Instagram account/token test failed."
        )

    # ==============================
    # GET ALL REELS
    # ==============================

    reels = get_reels()

    if not reels:
        raise RuntimeError(
            "No numbered MP4 files found "
            "in images folder."
        )

    print(
        f"\nTotal available Reels: "
        f"{len(reels)}"
    )

    # ==============================
    # SELECT BATCH
    # ==============================

    start, end, window = get_batch()

    if start >= len(reels):
        raise RuntimeError(
            f"No Reels available for batch "
            f"{start + 1}-{end}."
        )

    selected = reels[start:min(end, len(reels))]

    print(
        "\n=========================================="
    )

    print(
        f"Selected batch: "
        f"{start + 1}-{start + len(selected)}"
    )

    print(
        f"Posting window: {window}"
    )

    print(
        f"Reels in this batch: "
        f"{len(selected)}"
    )

    print(
        "=========================================="
    )

    # ==============================
    # CALCULATE GAP
    # ==============================

    count = len(selected)

    if count > 1:

        # 115 minutes gives a small buffer
        # inside the 2-hour window.

        total_window_seconds = 115 * 60

        gap_seconds = (
            total_window_seconds
            / (count - 1)
        )

    else:

        gap_seconds = 0

    print(
        f"\nGap between Reel starts: "
        f"{gap_seconds / 60:.2f} minutes"
    )

    # ==============================
    # GITHUB INFORMATION
    # ==============================

    repository = os.environ[
        "GITHUB_REPOSITORY"
    ]

    branch = os.getenv(
        "GITHUB_REF_NAME",
        "main"
    )

    # ==============================
    # POST SELECTED REELS
    # ==============================

    schedule_start = datetime.now(IST)

    for index, reel in enumerate(
        selected,
        start=0
    ):

        if index > 0:

            desired_time = (
                schedule_start
                + timedelta(
                    seconds=
                    gap_seconds * index
                )
            )

            while True:

                now = datetime.now(IST)

                remaining = (
                    desired_time - now
                ).total_seconds()

                if remaining <= 0:
                    break

                time.sleep(
                    min(remaining, 30)
                )

        file_url = (
            f"https://raw.githubusercontent.com/"
            f"{repository}/"
            f"{branch}/images/"
            f"{reel.name}"
        )

        print(
            f"\n========== "
            f"{start + index + 1}/"
            f"{start + len(selected)} "
            f"=========="
        )

        print(
            f"Time: "
            f"{datetime.now(IST).strftime('%I:%M:%S %p')}"
        )

        print(
            f"File: {reel.name}"
        )

        publish_reel(
            user_id,
            file_url,
            caption,
            token,
            reel.name
        )

    print(
        "\n=========================================="
    )

    print(
        f"DONE! {len(selected)} Reels posted."
    )

    print(
        f"Finished at: "
        f"{datetime.now(IST).strftime('%I:%M:%S %p')}"
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
