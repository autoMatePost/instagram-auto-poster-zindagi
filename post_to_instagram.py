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