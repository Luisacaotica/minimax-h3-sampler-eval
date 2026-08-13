#!/usr/bin/env python3
"""
sync_videos.py — copy freshly rendered ComfyUI clips into the site and keep it in sync.

ComfyUI writes renders as  <sampler>_00001.mp4  in its output folder
(e.g. res_multistep_00001.mp4). This script:

  1. finds each rendered sampler in the source folder,
  2. copies the newest clip to  videos/<scene>--<sampler>.mp4,
  3. generates a poster thumbnail  posters/<scene>--<sampler>.jpg  (needs ffmpeg),
  4. rewrites the RENDERED array in data.js so the pages show the clip.

Usage:
    python tools/sync_videos.py                 # source = ComfyUI output samplertest folder (../)
    python tools/sync_videos.py --source "C:/path/to/output/samplertest"
    python tools/sync_videos.py --dry-run       # show what would happen, change nothing
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
DATA = SITE / "data.js"
VIDEOS = SITE / "videos"
POSTERS = SITE / "posters"


def read_data() -> tuple[str, list[str], list[str]]:
    """Return (scene_id, samplers, rendered) parsed from data.js."""
    text = DATA.read_text(encoding="utf-8")

    m = re.search(r'const SCENES = \[\s*\{\s*id:\s*"([^"]+)"', text)
    if not m:
        sys.exit("could not find scene id in data.js")
    scene = m.group(1)

    def grab(name):
        m = re.search(r"const " + name + r" = \[(.*?)\];", text, re.S)
        if not m:
            sys.exit("could not find " + name + " in data.js")
        return re.findall(r'"([^"]+)"', m.group(1))

    return scene, grab("SAMPLERS"), grab("RENDERED")


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # bundled binary, often available via ComfyUI's env

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def norm_name(name: str) -> str:
    """'euler-cfg-pp' / 'euler cfg pp' -> 'euler_cfg_pp' (match data.js slugs)."""
    return re.sub(r"[\s-]+", "_", name.strip().lower()).strip("_")


def read_times(folder: Path, samplers: list[str]) -> dict[str, float]:
    """Parse Time_taken.txt ('name - seconds' per line) into {sampler: seconds}."""
    txt = folder / "Time_taken.txt"
    times: dict[str, float] = {}
    if not txt.exists():
        return times
    slugs = {norm_name(s): s for s in samplers}
    for line in txt.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.lower().startswith("in seconds") or line.startswith("#"):
            continue
        parts = line.rsplit(None, 1)
        if len(parts) != 2:
            print(f"  skip (unparseable): {line!r}")
            continue
        name, val = parts
        try:
            secs = float(val)
        except ValueError:
            print(f"  skip (bad seconds): {line!r}")
            continue
        slug = norm_name(re.sub(r"-\s*$", "", name))
        s = slugs.get(slug)
        if s is None:
            print(f"  WARNING: '{line}' does not match any sampler in data.js")
            continue
        times[s] = secs
    return times


def times_block(times: dict[str, float]) -> str:
    if not times:
        return "const TIMES = {};"
    inner = "".join(
        f'  "{s}": {int(v) if float(v).is_integer() else v},\n' for s, v in times.items()
    )
    return "const TIMES = {\n" + inner + "};"


def newest_match(folder: Path, sampler: str) -> Path | None:
    """Newest <sampler>[_NNNNN].mp4 in folder, or None."""
    cands = list(folder.glob(re.escape(sampler) + "_*.mp4")) + list(
        folder.glob(re.escape(sampler) + ".mp4")
    )
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def make_poster(video: Path, poster: Path, ffmpeg: str) -> bool:
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(poster)],
        check=False,
    )
    return poster.exists()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(SITE.parent),
                    help="folder with ComfyUI renders (default: %(default)s)")
    ap.add_argument("--dry-run", action="store_true", help="only report, don't copy or edit")
    args = ap.parse_args()

    source = Path(args.source).resolve()
    if not source.is_dir():
        sys.exit("source folder not found: " + str(source))

    scene, samplers, rendered = read_data()
    ffmpeg = find_ffmpeg()

    VIDEOS.mkdir(exist_ok=True)
    POSTERS.mkdir(exist_ok=True)

    new_rendered: list[str] = []
    copied, updated, made_posts = [], [], []
    missing = []

    for s in samplers:
        src = newest_match(source, s)
        if src is None:
            continue
        new_rendered.append(s)
        dst = VIDEOS / f"{scene}--{s}.mp4"
        poster = POSTERS / f"{scene}--{s}.jpg"

        need_copy = not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime
        if need_copy:
            if args.dry_run:
                updated.append(f"{src.name} -> {dst.name}")
            else:
                shutil.copy2(src, dst)
                copied.append(dst.name)

        if ffmpeg and (not poster.exists() or (not args.dry_run and need_copy)):
            if args.dry_run:
                made_posts.append(f"{poster.name} (poster)")
            else:
                if make_poster(dst, poster, ffmpeg):
                    made_posts.append(poster.name)

    # keep any rendered entries the data file already listed (e.g. hand-placed videos)
    for r in rendered:
        if r in samplers and r not in new_rendered:
            if (VIDEOS / f"{scene}--{r}.mp4").exists():
                new_rendered.append(r)
    new_rendered.sort(key=lambda s: samplers.index(s))

    # report
    print(f"scene: {scene}   source: {source}")
    print(f"rendered: {len(new_rendered)}/{len(samplers)}")
    print(f"times provided: {len(read_times(source, samplers))}")
    if args.dry_run:
        for x in updated:
            print("  copy  " + x)
        for x in made_posts:
            print("  make  " + x)
        print("(dry run — nothing changed)")
        return 0
    for x in copied:
        print("  copied " + x)
    for x in made_posts:
        print("  poster " + x)

    # rewrite RENDERED + TIMES in data.js
    text = DATA.read_text(encoding="utf-8")
    block = "const RENDERED = [\n" + "".join(f'  "{r}",\n' for r in new_rendered) + "];"
    new_text, n = re.subn(r"const RENDERED = \[.*?\];", block, text, count=1, flags=re.S)

    times = read_times(source, samplers)
    new_text, n2 = re.subn(
        r"const TIMES = \{.*?\};", times_block(times), new_text, count=1, flags=re.S
    )
    if n2 != 1:
        print("WARNING: could not update TIMES in data.js — add 'const TIMES = {};' to data.js")

    if n != 1:
        print("WARNING: could not update RENDERED in data.js — edit it manually")
    else:
        DATA.write_text(new_text, encoding="utf-8")
        print(f"updated data.js (RENDERED: {len(new_rendered)}, TIMES: {len(times)})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
