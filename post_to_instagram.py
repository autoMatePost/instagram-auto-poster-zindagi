import os
import sys
import time
import requests
from pathlib import Path


GRAPH_URL = "https://graph.instagram.com"


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

    caption = os.getenv(
        "ZINDAGI_CAPTION",
        ""
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
            f"but only {len(reels)} are available."
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
    # POST REELS
    # ==============================

    for index, reel in enumerate(
        reels[:count],
        start=1
    ):

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
        f"\nDONE! {count} Reels posted "
        f"to zindagikibaatein_."
    )


if __name__ == "__main__":
    main()
