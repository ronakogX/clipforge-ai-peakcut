"""Run the real pipeline on an authorized local fixture; no mocked models or encoders.

Usage: PEAKCUT_ASR_THREADS=2 PEAKCUT_ASR_COPIES=1 python tools/verify_real_video.py video.mp4
Requires the English speech model to have been downloaded first. Output stays in the private data folder.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio import auth, ctx, db, fetch_model, jobs, media, render


def main():
    source = Path(sys.argv[1]).resolve()
    assert source.is_file(), "Supply a real video fixture."
    assert fetch_model.ready(), "Download the English model first: python -m studio.fetch_model"
    db.init()
    render.install_fonts()
    started = time.monotonic()
    with ctx.as_user(auth.local_user().id):
        job = jobs.create({"type": "file", "name": source.name, "path": str(source)},
                          {"max_clips": 1, "min_len": 5, "max_len": 15, "quality": 360}, enqueue=False)
        jobs._run_job(job)
        words = json.loads((Path(job["dir"]) / "words.json").read_text())
        assert words, "No real speech was transcribed."
        assert job["clips"], "No highlight was selected."
        assert all(c["status"] == "done" for c in job["clips"]), jobs.public(job)
        clip = job["clips"][0]
        folder = Path(job["dir"]) / "clips"
        results = []
        for aspect in ("9:16", "16:9"):
            # Verify both orders on the same real-media interval, using an explicitly supplied
            # crop to exercise rendering. This does not claim the trailer has a streamer webcam.
            for layout in ("webcam_top", "gameplay_top"):
                settings = dict(clip, aspect=aspect, layout=layout, facecam=[0, 0, 200, 150], quality=360)
                out = render.render_clip(source, folder, aspect.replace(":", "_") + layout,
                                         settings, words, job["width"], job["height"])
                info = media.probe(folder / out["file"])
                assert info["width"] == out["width"] and info["height"] == out["height"]
                assert abs(info["duration"] - (clip["end"] - clip["start"])) < .3
                assert (folder / out["file"]).stat().st_size > 1000
                results.append(out)
        summary = {"job_id": job["id"], "seconds": round(time.monotonic()-started, 1),
                   "transcript": " ".join(w["w"] for w in words), "highlight": clip,
                   "outputs": results, "fixture": str(source)}
        (Path(job["dir"]) / "verification.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
