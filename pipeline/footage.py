"""Pexels stock footage: hook gets fast 1.5-2s cuts (3-second rule on steroids);
body sections get 2.5-3s cuts. Each section has multiple `queries` and the picker
rotates through them per sub-segment for visual variety. Dedupe by Pexels video_id
across the whole reel with an adjacency fallback. Downloads run in parallel and
cache by video_id under work/.clip_cache/."""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

PEXELS_API_URL = "https://api.pexels.com/videos/search"
CACHE_DIR_NAME = ".clip_cache"

# Hard-block specific Pexels videos from EVER being selected. Add a video_id
# here when its content is off-brand (visible carrier names like Verizon /
# AT&T, app logos, bank/credit-card notifications, watermarks, branded
# clothing). The full Pexels page URL of each chosen clip is logged on every
# render — copy the offending video_id from the log into this set.
#
# Example: BLOCKED_VIDEO_IDS = {1234567, 7654321}
BLOCKED_VIDEO_IDS: set[int] = set()

# Within-section xfade overlap. Must match assemble.py.
XFADE_DURATION = 0.15

# Body section cut params
BODY_MIN_CLIP_S = 2.5
BODY_MAX_CLIP_S = 3.0
BODY_TARGET_AVG_S = 2.75

# Hook section cut params (faster, punchier — 3-second rule on steroids)
HOOK_MIN_CLIP_S = 1.5
HOOK_MAX_CLIP_S = 2.0
HOOK_TARGET_AVG_S = 1.75

DOWNLOAD_WORKERS = 5


def split_section_into_subs(duration: float, is_hook: bool = False) -> list[float]:
    """Split a section's video duration into sub-segment clip durations.

    With xfade overlap of XFADE_DURATION between consecutive clips,
    sum(returned) - (N-1)*XFADE = duration. Hook sections use 1.5-2s cuts;
    body sections use 2.5-3s cuts. Returns [duration] if too short to split.
    """
    if is_hook:
        min_clip, max_clip, target = HOOK_MIN_CLIP_S, HOOK_MAX_CLIP_S, HOOK_TARGET_AVG_S
    else:
        min_clip, max_clip, target = BODY_MIN_CLIP_S, BODY_MAX_CLIP_S, BODY_TARGET_AVG_S

    if duration <= max_clip + 0.3:
        return [duration]

    N = max(2, round(duration / target))
    total_clip_time = duration + (N - 1) * XFADE_DURATION
    base = total_clip_time / N
    jitter = (max_clip - min_clip) / 4  # half the spread
    durations = [base + (jitter if i % 2 == 0 else -jitter) for i in range(N)]
    durations[-1] = total_clip_time - sum(durations[:-1])
    return durations


def _search(api_key: str, query: str) -> list[dict]:
    r = requests.get(
        PEXELS_API_URL,
        params={"query": query, "orientation": "portrait", "per_page": 15},
        headers={"Authorization": api_key},
        timeout=30,
    )
    r.raise_for_status()
    videos = r.json().get("videos", [])
    # Strip globally-blocked videos at the search boundary so they never
    # enter dedupe / adjacency / selection logic.
    return [v for v in videos if v.get("id") not in BLOCKED_VIDEO_IDS]


def _pick(
    candidates: list[dict],
    min_duration: float,
    used_ids: set[int],
    avoid_id: int | None,
) -> dict | None:
    """Pick the best candidate honouring used_ids (whole-reel dedupe) and adjacency."""
    fresh = [v for v in candidates if v.get("id") not in used_ids and v.get("id") != avoid_id]
    if fresh:
        eligible = [v for v in fresh if v.get("duration", 0) >= min_duration]
        return eligible[0] if eligible else max(fresh, key=lambda v: v.get("duration", 0))
    non_adj = [v for v in candidates if v.get("id") != avoid_id]
    if non_adj:
        eligible = [v for v in non_adj if v.get("duration", 0) >= min_duration]
        return eligible[0] if eligible else max(non_adj, key=lambda v: v.get("duration", 0))
    return None


def _select_for_section(
    api_key: str,
    queries: list[str],
    sub_durations: list[float],
    used_ids: set[int],
    last_id: int | None,
) -> tuple[list[dict], int | None]:
    """Pick N videos for the section's sub-segments, rotating through `queries`.

    Each unique query is searched once per section (cached in-call). The picker
    honours global dedupe and adjacency. Falls back to clip reuse with a WARN if
    Pexels variety is insufficient.
    """
    if not queries:
        raise RuntimeError("section has no queries")

    query_results: dict[str, list[dict]] = {}

    def results_for(q: str) -> list[dict]:
        if q in query_results:
            return query_results[q]
        videos = _search(api_key, q)
        if not videos:
            short = " ".join(q.split()[:2])
            if short and short != q:
                videos = _search(api_key, short)
        query_results[q] = videos
        return videos

    chosen: list[dict] = []
    avoid = last_id
    warned = False
    for i, sub_dur in enumerate(sub_durations):
        query = queries[i % len(queries)]
        videos = results_for(query)
        if not videos:
            # Try the other queries in this section as a fallback before giving up
            for alt in queries:
                if alt == query:
                    continue
                videos = results_for(alt)
                if videos:
                    break
        if not videos:
            raise RuntimeError(
                f"Pexels returned 0 results for any query in section: {queries!r}"
            )

        pick = _pick(videos, sub_dur, used_ids, avoid)
        if pick is None:
            pick = videos[0]
            if not warned:
                print(
                    f"[footage] WARN: limited Pexels variety across queries "
                    f"{queries!r}; reusing clips with adjacency relaxed",
                    file=sys.stderr,
                )
                warned = True
        chosen.append(pick)
        used_ids.add(pick["id"])
        avoid = pick["id"]
    return chosen, avoid


def best_video_file_url(video: dict) -> str:
    files = video.get("video_files", [])
    portrait = [f for f in files if f.get("height", 0) >= f.get("width", 0)]
    candidates = portrait or files
    candidates = sorted(
        candidates,
        key=lambda f: -(f.get("height", 0) * f.get("width", 0)),
    )
    if not candidates:
        raise RuntimeError(f"No video files on Pexels video id={video.get('id')}")
    return candidates[0]["link"]


def _download_one(url: str, out_path: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)


def fetch_clips(
    api_key: str,
    sections: list[dict],
    section_durations: list[float],
    work_dir: Path,
) -> list[tuple[Path, float, int]]:
    """Plan sub-segments for the whole reel and return them in playback order.

    Each tuple is (clip_path, sub_duration, section_idx). Section index 0 is the
    hook (Ken Burns + fast cuts). Downloads run in parallel and skip already-cached
    clips at work/.clip_cache/{video_id}.mp4.
    """
    cache_dir = work_dir.parent / CACHE_DIR_NAME
    cache_dir.mkdir(exist_ok=True)

    used_ids: set[int] = set()
    last_id: int | None = None
    plan: list[tuple[dict, float, int]] = []

    for section_idx, (sec, dur) in enumerate(zip(sections, section_durations)):
        is_hook = section_idx == 0
        sub_durs = split_section_into_subs(dur, is_hook=is_hook)
        queries: list[str] = sec["queries"]
        videos, last_id = _select_for_section(
            api_key, queries, sub_durs, used_ids, last_id
        )
        for v, sd in zip(videos, sub_durs):
            plan.append((v, sd, section_idx))

    unique_videos: dict[int, dict] = {}
    for v, _, _ in plan:
        unique_videos[v["id"]] = v

    pending: list[tuple[str, Path]] = []
    for vid_id, video in unique_videos.items():
        out = cache_dir / f"{vid_id}.mp4"
        if not out.exists():
            pending.append((best_video_file_url(video), out))

    cached_count = len(unique_videos) - len(pending)
    if cached_count:
        print(
            f"[footage] {cached_count} clip(s) cached; downloading {len(pending)} new",
            file=sys.stderr,
        )
    else:
        print(f"[footage] Downloading {len(pending)} clip(s) in parallel...", file=sys.stderr)

    # Log every chosen video's Pexels page URL so off-brand clips (carrier
    # logos, app UIs, watermarks) can be identified and added to the blocklist
    # in this module. Format chosen for easy copy-paste into BLOCKED_VIDEO_IDS.
    for v, _, section_idx in plan:
        label = f"section[{section_idx}]"
        print(
            f"[footage] picked {label}  video_id={v['id']:>10}  "
            f"{v.get('url', '(no url)')}",
            file=sys.stderr,
        )

    if pending:
        with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
            futures = [pool.submit(_download_one, u, o) for u, o in pending]
            for fut in as_completed(futures):
                fut.result()

    return [(cache_dir / f"{v['id']}.mp4", sd, si) for v, sd, si in plan]


def search_only(
    api_key: str,
    sections: list[dict],
    section_durations: list[float],
) -> list[dict]:
    """Dry-run: preview the cut plan + queries + chosen videos without downloading."""
    used_ids: set[int] = set()
    last_id: int | None = None
    results: list[dict] = []
    for section_idx, (sec, dur) in enumerate(zip(sections, section_durations)):
        is_hook = section_idx == 0
        sub_durs = split_section_into_subs(dur, is_hook=is_hook)
        try:
            videos, last_id = _select_for_section(
                api_key, sec["queries"], sub_durs, used_ids, last_id
            )
            results.append(
                {
                    "section": sec,
                    "is_hook": is_hook,
                    "sub_durations": [round(d, 2) for d in sub_durs],
                    "clips": [
                        {
                            "video_id": v.get("id"),
                            "video_url": v.get("url"),
                            "duration": v.get("duration"),
                            "width": v.get("width"),
                            "height": v.get("height"),
                        }
                        for v in videos
                    ],
                }
            )
        except Exception as e:
            results.append({"section": sec, "error": str(e)})
    return results
