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


def wait_until_6pm():

    now = datetime.now(IST)

    target = now.replace(
        hour=18,
        minute=0,
        second=0,
        microsecond=0
    )

    # If workflow is already started after 6 PM,
    # do not wait.
    if now >= target:
        print(
            "\nCurrent time is already 6:00 PM or later."
        )
        return

    wait_seconds = (
        target - now
    ).total_seconds()

    print(
        "\n=========================================="
    )

    print(
        "Waiting for 6:00 PM IST..."
    )

    print(
        f"Current IST time: "
        f"{now.strftime('%I:%M:%S %p')}"
    )

    print(
        f"Reels will start at: "
        f"06:00:00 PM IST"
    )

    print(
        f"Waiting approximately "
        f"{int(wait_seconds // 60)} minutes."
    )

    print(
        "=========================================="
    )

    while True:

        remaining = (
            target -
            datetime.now(IST)
        ).total_seconds()

        if remaining <= 0:
            break

        time.sleep(
            min(remaining, 30)
        )

    print(
        "\n=========================================="
    )

    print(
        "6:00 PM IST reached!"
    )

    print(
        "Starting Reel posting..."
    )

    print(
        "=========================================="
    )


def wait_for_container(
    creation_id,
    token
):

    for attempt in range(20):

        response = requests.get(
            f"{GRAPH_URL}/{creation_id}",
            params={
                "fields":
                    "status_code,status",
                "access_token":
                    token,
            },
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        print(
            f"Container status "
            f"{attempt + 1}/20: {data}"
        )

        status_code = data.get(
            "status_code"
        )

        if status_code == "FINISHED":
            return

        if status_code in (
            "ERROR",
            "EXPIRED"
        ):
            raise RuntimeError(
                f"Instagram container failed: "
                f"{data}"
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

    print(
        f"\nUploading: {filename}"
    )

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

        print(
            "\nInstagram API Error:"
        )

        print(
            response.text
        )

    response.raise_for_status()

    creation_id = response.json().get(
        "id"
    )

    if not creation_id:

        raise RuntimeError(
            f"Container ID missing "
            f"for {filename}"
        )

    print(
        f"Container created: "
        f"{creation_id}"
    )

    wait_for_container(
        creation_id,
        token
    )

    response = requests.post(
        f"{GRAPH_URL}/{user_id}/media_publish",
        params={
            "creation_id":
                creation_id,
            "access_token":
                token,
        },
        timeout=60,
    )

    if not response.ok:

        print(
            "\nPublish Error:"
        )

        print(
            response.text
        )

    response.raise_for_status()

    print(
        f"SUCCESS: {filename}"
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

    count = int(
        os.getenv(
            "POST_COUNT",
            "1"
        )
    )

    # ==============================
    # TEST INSTAGRAM ACCOUNT
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
            "fields":
                "user_id,username",
            "access_token":
                token,
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
            "Instagram account/token "
            "test failed."
        )

    # ==============================
    # GET REELS
    # ==============================

    reels = get_reels()

    if not reels:

        raise RuntimeError(
            "No numbered MP4 files found "
            "in images folder."
        )

    if count > len(reels):

        raise RuntimeError(
            f"You requested {count} Reels, "
            f"but only {len(reels)} "
            f"are available."
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

    print(
        f"\nTotal available Reels: "
        f"{len(reels)}"
    )

    print(
        f"Reels requested: "
        f"{count}"
    )

    # ==============================
    # WAIT UNTIL 6 PM IST
    # ==============================

    wait_until_6pm()

    # ==============================
    # CALCULATE POSTING GAP
    # ==============================

    if count > 1:

        # Use 115 minutes instead of
        # the full 120 minutes so the
        # final Reel has some buffer.

        total_window_seconds = (
            115 * 60
        )

        gap_seconds = (
            total_window_seconds
            / (count - 1)
        )

    else:

        gap_seconds = 0

    print(
        "\n=========================================="
    )

    print(
        "Posting schedule:"
    )

    print(
        f"Number of Reels: {count}"
    )

    print(
        f"Gap between Reel starts: "
        f"{gap_seconds / 60:.2f} minutes"
    )

    print(
        "Target window: "
        "6:00 PM - approximately 7:55 PM IST"
    )

    print(
        "=========================================="
    )

    # ==============================
    # POST REELS
    # ==============================

    schedule_start = datetime.now(
        IST
    )

    for index, reel in enumerate(
        reels[:count],
        start=1
    ):

        # Calculate the desired start
        # time for this Reel.

        if index > 1:

            desired_time = (
                schedule_start
                + timedelta(
                    seconds=
                    gap_seconds
                    * (index - 1)
                )
            )

            while True:

                now = datetime.now(
                    IST
                )

                remaining = (
                    desired_time - now
                ).total_seconds()

                if remaining <= 0:
                    break

                print(
                    f"\nWaiting "
                    f"{int(remaining)} seconds "
                    f"for Reel {index}..."
                )

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
            f"{index}/{count} =========="
        )

        print(
            f"Time: "
            f"{datetime.now(IST).strftime('%I:%M:%S %p')}"
        )

        print(
            f"File: {reel.name}"
        )

        print(
            f"URL: {file_url}"
        )

        publish_reel(
            user_id,
            file_url,
            caption,
            token,
            reel.name
        )

    # ==============================
    # DONE
    # ==============================

    print(
        "\n=========================================="
    )

    print(
        f"DONE! {count} Reels posted "
        f"to zindagikibaatein_."
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
