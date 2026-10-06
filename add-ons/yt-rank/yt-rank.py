"""Rank YouTube's 100 most popular videos by what Boku's data says you like.

Fetches the videos from the YouTube Data API, builds a short profile from
~/.boku/data, and asks Claude (the `claude` CLI) to summarise and rank them.
Prints the list and writes ~/boku-yt-rank/ranked.json.

    YOUTUBE_API_KEY=... uv run python add-ons/yt-rank/yt-rank.py [REGION]
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

DATA_DIR = Path.home() / ".boku" / "data"
OUT_PATH = Path.home() / "boku-yt-rank" / "ranked.json"
API_URL = "https://www.googleapis.com/youtube/v3/videos"
REGION = "US"
MODEL = "sonnet"
CLAUDE_TIMEOUT = 300
MAX_DESCRIPTION = 200
MAX_APPS = 30
MAX_FOLDERS = 150
MAX_EXTENSIONS = 20
FOLDER_DEPTH = 3


def fetch_videos(key, region):
    videos, token = [], ""
    while len(videos) < 100:
        params = {"part": "snippet", "chart": "mostPopular", "maxResults": 50,
                  "regionCode": region, "key": key}
        if token:
            params["pageToken"] = token
        with urllib.request.urlopen(f"{API_URL}?{urllib.parse.urlencode(params)}", timeout=30) as response:
            page = json.load(response)
        for item in page.get("items", []):
            snippet = item.get("snippet", {})
            videos.append({
                "id": item.get("id", ""),
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "description": " ".join(snippet.get("description", "").split())[:MAX_DESCRIPTION],
                "tags": snippet.get("tags", [])[:8],
            })
        token = page.get("nextPageToken", "")
        if not token:
            break
    return videos[:100]


def read_records(source):
    records = []
    try:
        with open(DATA_DIR / f"{source}.jsonl", encoding="utf-8") as file:
            for line in file:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and isinstance(record.get("data"), dict):
                    records.append(record)
    except OSError:
        pass
    return records


def build_profile():
    parts = []

    apps = Counter()
    for record in read_records("app_activity"):
        for event in record["data"].get("events", []):
            if event.get("event") == "activated" and event.get("name"):
                apps[event["name"]] += 1
    if apps:
        parts.append("Apps used (times switched to): "
                     + ", ".join(f"{name} ({count})" for name, count in apps.most_common(MAX_APPS)))

    paths = []
    for record in read_records("filetree"):
        if "paths" in record["data"]:
            paths = record["data"]["paths"]
    if paths:
        folders = [path for path in paths
                   if path.endswith("/") and path.count("/") <= FOLDER_DEPTH][:MAX_FOLDERS]
        extensions = Counter(Path(path).suffix.lower() for path in paths if not path.endswith("/"))
        extensions.pop("", None)
        parts.append("Folders in home directory: " + ", ".join(folders))
        parts.append("File types: "
                     + ", ".join(f"{ext} ({count})" for ext, count in extensions.most_common(MAX_EXTENSIONS)))

    return "\n".join(parts)


def rank(videos, profile):
    listing = "\n".join(
        f"{number}. {video['title']} | {video['channel']} | {video['description']} | {', '.join(video['tags'])}"
        for number, video in enumerate(videos, 1))
    prompt = (
        "Below is data about one person's computer use, then a numbered list of YouTube videos "
        "(title | channel | description | tags).\n"
        "Infer what this person is interested in and score every video from 0 to 100 for how much "
        "they would want to watch it.\n"
        "Reply with exactly one line per video and nothing else, in the form:\n"
        "number|score|summary of the video in at most 15 words\n\n"
        f"PERSON\n{profile or 'No data collected yet. Rank by general quality.'}\n\n"
        f"VIDEOS\n{listing}\n")
    result = subprocess.run(["claude", "-p", "--model", MODEL], input=prompt,
                            capture_output=True, text=True, timeout=CLAUDE_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "claude exited with an error")

    for line in result.stdout.splitlines():
        match = re.match(r"\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+)", line)
        if match and 1 <= int(match[1]) <= len(videos):
            video = videos[int(match[1]) - 1]
            video["score"] = int(match[2])
            video["summary"] = match[3].strip()
    # Videos Claude left out stay in the list, at the bottom.
    return sorted(videos, key=lambda video: video.get("score", -1), reverse=True)


def main():
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        sys.exit("Set YOUTUBE_API_KEY (YouTube Data API v3 key from console.cloud.google.com).")
    region = sys.argv[1].upper() if len(sys.argv) > 1 else REGION

    print(f"Fetching the most popular videos ({region})...", file=sys.stderr)
    try:
        videos = fetch_videos(key, region)
    except urllib.error.HTTPError as error:
        sys.exit(f"YouTube API error {error.code}: {error.read().decode(errors='replace')[:300]}")
    except OSError as error:
        sys.exit(f"Could not reach YouTube: {error}")
    if not videos:
        sys.exit("YouTube returned no videos.")

    profile = build_profile()
    if not profile:
        print(f"No Boku data found in {DATA_DIR}; ranking without a profile.", file=sys.stderr)

    print(f"Ranking {len(videos)} videos with Claude...", file=sys.stderr)
    try:
        ranked = rank(videos, profile)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        sys.exit(f"Ranking failed: {error}")

    for position, video in enumerate(ranked, 1):
        video["rank"] = position
        video["url"] = f"https://youtu.be/{video['id']}"
        score = video.get("score", "--")
        print(f"{position:>3}. [{score}] {video['title']} ({video['channel']})")
        print(f"     {video.get('summary', 'not ranked')}")
        print(f"     {video['url']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(ranked, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
