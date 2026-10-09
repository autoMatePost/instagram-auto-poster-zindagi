import os
import time
import json
import requests
from pathlib import Path
from urllib.parse import quote


GRAPH_URL = "https://graph.instagram.com"

STATE_FILE = Path("state.json")
LINKS_FILE = Path("links.txt")


def get_reels():

    folder = Path("images")

    files = [
        file
        for file in folder.iterdir()
        if file.is_file()
        and file.suffix.lower() == ".mp4"
    ]

    return sorted(
        files,
        key=lambda file: file.name.lower()
    )


def load_state():

    if not STATE_FILE.exists():
        return {
            "posted_files": []
        }

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return {
            "posted_files": []
        }


def save_state(posted_files):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "posted_files": posted_files
            },
            f,
            indent=2,
            ensure_ascii=False
        )


def save_link(filename, permalink):

    with open(
        LINKS_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            f"{filename} -> {permalink}\n"
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


def get_permalink(
    media_id,
    token
):

    response = requests.get(
        f"{GRAPH_URL}/{media_id}",
        params={
            "fields": "permalink",
            "access_token": token,
        },
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    permalink = data.get(
        "permalink"
    )

    if not permalink:

        raise RuntimeError(
            f"Instagram permalink not found: "
            f"{data}"
        )

    return permalink


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

    # Create Reel container
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

    # Wait until Instagram finishes processing
    wait_for_container(
        creation_id,
        token
    )

    # Publish Reel
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

    media_id = response.json().get(
        "id"
    )

    if not media_id:

        raise RuntimeError(
            f"Published media ID missing "
            f"for {filename}"
        )

    print(
        f"Published Media ID: "
        f"{media_id}"
    )

    # Get actual Instagram Reel URL
    permalink = get_permalink(
        media_id,
        token
    )

    print(
        f"INSTAGRAM LINK: "
        f"{permalink}"
    )

    return permalink


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

    repository = os.environ[
        "GITHUB_REPOSITORY"
    ]

    branch = os.getenv(
        "GITHUB_REF_NAME",
        "main"
    )

    # ==============================
    # FIXED CAPTION
    # ==============================

    caption = (
        "#あらゆる追いかけっこを繰り広げる"
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
    # GET ALL MP4 REELS
    # ==============================

    reels = get_reels()

    if not reels:

        raise RuntimeError(
            "No MP4 files found "
            "in images folder."
        )

    print(
        f"\nTotal MP4 Reels: "
        f"{len(reels)}"
    )

    # ==============================
    # LOAD POSTED FILES
    # ==============================

    state = load_state()

    posted_files = state.get(
        "posted_files",
        []
    )

    # ==============================
    # REMOVE ALREADY POSTED REELS
    # ==============================

    pending_reels = [
        reel
        for reel in reels
        if reel.name not in posted_files
    ]

    print(
        f"Already posted: "
        f"{len(posted_files)}"
    )

    print(
        f"Pending Reels: "
        f"{len(pending_reels)}"
    )

    if not pending_reels:

        print(
            "\n=========================================="
        )

        print(
            "ALL REELS HAVE ALREADY BEEN POSTED."
        )

        print(
            "=========================================="
        )

        return

    # ==============================
    # POST ONE BY ONE
    # ==============================

    for index, reel in enumerate(
        pending_reels,
        start=1
    ):

        safe_filename = quote(
            reel.name
        )

        file_url = (
            f"https://raw.githubusercontent.com/"
            f"{repository}/"
            f"{branch}/images/"
            f"{safe_filename}"
        )

        print(
            "\n=========================================="
        )

        print(
            f"REEL {index}/{len(pending_reels)}"
        )

        print(
            f"FILE: {reel.name}"
        )

        print(
            "=========================================="
        )

        try:

            # Publish Reel
            permalink = publish_reel(
                user_id,
                file_url,
                caption,
                token,
                reel.name
            )

            # Save Instagram link
            save_link(
                reel.name,
                permalink
            )

            # Mark file as posted
            posted_files.append(
                reel.name
            )

            save_state(
                posted_files
            )

            print(
                "\n=========================================="
            )

            print(
                "SUCCESS"
            )

            print(
                f"FILE: {reel.name}"
            )

            print(
                f"LINK: {permalink}"
            )

            print(
                "Saved to links.txt"
            )

            print(
                "=========================================="
            )

            # Immediately continue to next Reel

        except Exception as e:

            print(
                "\n=========================================="
            )

            print(
                f"FAILED: {reel.name}"
            )

            print(
                str(e)
            )

            print(
                "Stopping workflow."
            )

            raise

    print(
        "\n=========================================="
    )

    print(
        f"ALL {len(pending_reels)} REELS COMPLETED"
    )

    print(
        "Instagram links saved in links.txt"
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
