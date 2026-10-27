"""The authoring-agent clip (~50 s): describe a task -> the agent builds it live -> approval
-> saved workflow -> fixing a failed run. Same look as the main demo (make_video.py).

Inputs: demo/out/raw/20-agent.webm (+ marks) and 21-fix.webm from capture_agent.py.
Output: demo/out/watchonce-agent.mp4

    uv run --no-project --with edge-tts --with imageio-ffmpeg --with numpy \\
        python demo/scripts/make_agent_video.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_video as mv  # noqa: E402
from make_video import Segment, Sub  # noqa: E402

mv.EDIT = mv.ROOT / "demo" / "out" / "edit-agent"
mv.run.__defaults__ = (mv.EDIT,)  # its default working folder was bound at import
OUT = mv.ROOT / "demo" / "out" / "watchonce-agent.mp4"
m = json.loads((mv.RAW / "20-agent-marks.json").read_text())
fix = json.loads((mv.RAW / "21-fix-marks.json").read_text())

SEGMENTS = [
    Segment("00-title", kind="card", min_seconds=3.5,
            card=("New in WatchOnce", "Describe it. It builds it.", "An agent that does the task while you watch")),
    Segment("01-describe", "Now you don't even have to record. Just describe the task, one step per line, and press build.",
            "Describe the task. Press build.", [Sub("20-agent", m["open_form"], m["submit"] + 0.6)]),
    Segment("02-build", "The agent does it once, in a real browser, while you watch. It logs in with a saved login, so the password never leaves the vault, and fills in the invoice, field by field.",
            "It does the task live, while you watch", [Sub("20-agent", m["building"], m["approval"] - 0.2)]),
    Segment("03-approve", "Before it submits anything, it stops and asks you.",
            "It asks before anything risky", [Sub("20-agent", m["approval"] - 0.2, m["approved"] + 1.2, 1.0)]),
    Segment("04-saved", "Then it saves a normal workflow, with inputs and outputs. Every later run replays these steps, with no AI at all.",
            "Saved as a workflow. Later runs need no AI.", [Sub("20-agent", m["approved"] + 1.2, m["end"])]),
    Segment("05-fix", "And when a run fails, just tell it what changed. It redoes the task live, and saves a new version.",
            "A run failed? Tell it what to change.", [Sub("21-fix", fix["start"], fix["end"])]),
    Segment("06-end", "WatchOnce. Show it once, or just describe it.", kind="card", min_seconds=4.5,
            card=("WatchOnce", "Show it once. Or just describe it.", "github.com/khurram-Shahid09/watchonce")),
]  # fmt: skip


def main() -> None:
    mv.EDIT.mkdir(parents=True, exist_ok=True)
    built = []
    for seg in SEGMENTS:
        path, seconds = mv.build_segment(seg, mv.make_voice(seg))
        built.append((path, seconds))
        print(f"{seg.name:12s} {seconds:5.1f}s", flush=True)
    listing = mv.EDIT / "segments.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p, _ in built), encoding="utf-8")
    joined = mv.EDIT / "joined.mp4"
    mv.run(
        [mv.FF, "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined)]
    )
    total = sum(s for _, s in built)
    music = mv.make_music(total)
    mv.run([
        mv.FF, "-y", "-i", str(joined), "-i", str(music), "-filter_complex",
        "[1:a]aresample=48000,volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(OUT),
    ])  # fmt: skip
    print(f"\n{OUT} ({total:.0f}s)")


if __name__ == "__main__":
    main()
