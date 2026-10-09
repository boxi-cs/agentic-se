"""Write weeks/NN/poster.jpg (960x540) from each film's frame at the end of its first beat.

    ~/Documents/agentic-se-videos/.venv/bin/python tools/posters.py --videos ~/Documents/agentic-se-videos

Needs PyAV and Pillow (the video repository's environment has both).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import av

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", type=Path, required=True)
    args = parser.parse_args()
    for film in sorted((args.videos / "media/episodes").glob("*/Episode.mp4")):
        week = int(film.parent.name[:2])
        timeline = json.loads((film.parent / "Episode.json").read_text())
        first_scene = [b for b in timeline if b["id"].startswith("s0_")]
        at = first_scene[-1]["end"] - 0.2
        with av.open(str(film)) as container:
            stream = container.streams.video[0]
            container.seek(int(max(at - 1, 0) / stream.time_base), stream=stream)
            image = None
            for frame in container.decode(stream):
                if frame.time >= at:
                    image = frame.to_image().resize((960, 540))
                    break
        if image is None:
            raise SystemExit(f"{film}: no frame at {at:.1f}s")
        out = ROOT / "weeks" / f"{week:02d}" / "poster.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(out, quality=82, optimize=True, progressive=True)
        print(out.relative_to(ROOT), f"{at:.1f}s")


if __name__ == "__main__":
    main()
