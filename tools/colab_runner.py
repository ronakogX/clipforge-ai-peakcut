"""Private, key-free batch processing for the CLIPFORGE Colab notebook. No web server."""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAX_BYTES = 2 * 1024**3


def log(message):
    print(message, flush=True)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def source_file(value):
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("Choose a video file no larger than 2 GiB.")
    if path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".ts"}:
        raise ValueError("Choose an MP4, MOV, MKV, WebM, M4V, AVI or TS video.")
    return path


def finite(value, low, high, name):
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return number


def copy_source(source, destination):
    digest = hashlib.sha256()
    total, last = 0, 0
    size = source.stat().st_size
    if shutil.disk_usage(destination.parent).free < size + 2 * 1024**3:
        raise RuntimeError("The runtime needs room for the source plus at least 2 GiB of working space.")
    with source.open("rb") as incoming, destination.open("wb") as outgoing:
        while block := incoming.read(8 * 1024**2):
            outgoing.write(block)
            digest.update(block)
            total += len(block)
            if total - last >= 128 * 1024**2 or total == size:
                log(f"Staging video: {total / 1024**2:.0f} / {size / 1024**2:.0f} MiB")
                last = total
    return digest.hexdigest()


def configure():
    # A notebook must never reuse a key or paid model endpoint from another session.
    os.environ.update(DATABASE_URL="", PEAKCUT_AI_PROVIDER="gemini", PEAKCUT_AI_MODELS="", PEAKCUT_AI_KEY="",
                      PEAKCUT_AI_KEY_FILE="", PEAKCUT_AI_BASE_URL="", PEAKCUT_ASR_URL="",
                      PEAKCUT_ASR_THREADS="2", PEAKCUT_ASR_COPIES="1", PEAKCUT_RENDER_THREADS="2",
                      PEAKCUT_RENDER_WORKERS="1", PEAKCUT_JOB_WORKERS="1", PEAKCUT_UPDATE_CHECK="0",
                      PEAKCUT_MAX_VIDEO_HOURS="12", PEAKCUT_ACCOUNTS="0")


def analyze(settings):
    from studio import ai, brain, facecam, fetch_model, media, render, transcribe
    if ai.ready():
        raise RuntimeError("External AI must be off for this free notebook.")
    source = source_file(settings["source"])
    count = int(finite(settings.get("count", 3), 1, 8, "Clip count"))
    maximum = finite(settings.get("duration", 45), 15, 60, "Clip duration")
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    work = Path(settings["work_root"]).resolve() / run_id
    destination = Path(settings["output_root"]).resolve() / run_id
    work.mkdir(parents=True)
    destination.mkdir(parents=True)
    local = work / ("source" + source.suffix.lower())
    checksum = copy_source(source, local)
    info = media.probe(local)
    if not 3 <= info["duration"] <= 12 * 3600:
        raise ValueError("The video must be between 3 seconds and 12 hours.")
    start = finite(settings.get("start", 0), 0, info["duration"] - 1, "Analysis start")
    stop = float(settings.get("end", 0)) or info["duration"]
    stop = finite(stop, start + 1, info["duration"], "Analysis end")
    log(f"Analyzing {start:.1f}–{stop:.1f}s of {info['duration']:.1f}s. No 300-second cutoff.")
    fetch_model.ensure()
    log("Extracting source audio")
    wav = work / "audio.wav"
    media.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", str(local), "-t", str(stop-start),
               "-vn", "-ac", "1", "-ar", "16000", "-af", "aresample=async=1:first_pts=0", "-c:a", "pcm_s16le", str(wav)])
    audio = media.load_audio(wav)
    levels = media.loudness_per_second(audio)
    words = []
    block_size = 600 * 16000
    for offset in range(0, len(audio), block_size):
        end = min(len(audio), offset + block_size)
        log(f"Transcribing {start+offset/16000:.1f}–{start+end/16000:.1f}s")
        heard = transcribe.transcribe(audio[offset:end], lang="en")
        words += [dict(w, s=round(w["s"]+offset/16000, 3), e=round(w["e"]+offset/16000, 3)) for w in heard]
        write_json(destination / "transcript-checkpoint.json",
                   {"source_sha256": checksum, "completed_until_seconds": start+end/16000,
                    "words": [dict(w, s=w["s"]+start, e=w["e"]+start) for w in words]})
    del audio
    log("Ranking moments across the complete selected range using speech and audio loudness")
    candidates, ranking = brain.find_clips(words, levels, stop-start, source.stem,
                                          max_clips=count, min_len=min(15, maximum-5), max_len=maximum)
    for i, clip in enumerate(candidates):
        clip.update(id=f"clip{i+1:02d}", start=round(clip["start"]+start, 3), end=round(clip["end"]+start, 3))
    words = [dict(w, s=round(w["s"]+start, 3), e=round(w["e"]+start, 3)) for w in words]
    log("Checking for a webcam region")
    detected = facecam.detect(local)
    region = None
    if detected and detected.get("conf") == "high":
        try:
            region = render.validate_facecam([detected[k] for k in ("x", "y", "w", "h")], info["width"], info["height"])
        except ValueError:
            pass
    thumbnail = work / "source.jpg"
    media.run(["ffmpeg", "-y", "-v", "error", "-ss", str(candidates[0]["start"] if candidates else start),
               "-i", str(local), "-frames:v", "1", "-vf", "scale=960:-2", str(thumbnail)])
    data = {"run_id": run_id, "source_name": source.name, "source_original": str(source), "source": str(local),
            "source_sha256": checksum, "work": str(work), "output": str(destination), "info": info,
            "analysis_start": start, "analysis_end": stop,
            "words": words, "highlights": candidates, "facecam": region,
            "ranking_note": ranking.get("note", ""), "thumbnail": str(thumbnail)}
    write_json(work / "analysis.json", data)
    write_json(destination / "analysis.json", data)
    write_json(Path(settings["work_root"]) / "latest.json", data)
    log(f"Analysis saved. {len(candidates)} candidate(s); webcam {'found — review it' if region else 'not found — gameplay-only is available'}.")
    if not candidates:
        log("No spoken highlight was selected. You can still enter a manual interval in the render controls.")
    return data


def srt(words, start, end):
    def stamp(t):
        ms = max(0, round(t*1000))
        return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
    inside = [w for w in words if w["e"] > start and w["s"] < end]
    lines = []
    for a in range(0, len(inside), 5):
        group = inside[a:a+5]
        lo, hi = max(0, group[0]["s"]-start), min(end-start, group[-1]["e"]-start)
        if hi > lo:
            lines.append(f"{len(lines)+1}\n{stamp(lo)} --> {stamp(hi)}\n"+" ".join(w["w"] for w in group)+"\n")
    return "\n".join(lines)


def render_selected(settings):
    from studio import auth, ctx, db, jobs, media, render
    data = json.loads(Path(settings["analysis"]).read_text(encoding="utf-8"))
    if not Path(data["source"]).is_file():
        raise RuntimeError("This runtime's source copy is gone. Run the analysis step again; saved Drive clips remain available.")
    selected = settings.get("selected", [])
    if not isinstance(selected, list) or any(not isinstance(i, int) or not 0 <= i < len(data["highlights"]) for i in selected):
        raise ValueError("Choose valid highlight checkboxes.")
    clips = [dict(data["highlights"][i]) for i in dict.fromkeys(selected)]
    if settings.get("manual_end", 0):
        lo = finite(settings.get("manual_start", 0), data["analysis_start"], data["analysis_end"]-3, "Manual start")
        hi = finite(settings["manual_end"], lo+3, min(data["analysis_end"], lo+180), "Manual end")
        clips.append(dict(start=lo, end=hi, title="Manual clip", hook="", description="", hashtags=[], score=0,
                          reason="Selected manually"))
    if not 1 <= len(clips) <= 9:
        raise ValueError("Select at least one highlight or add a manual interval.")
    aspects = ["9:16", "16:9"] if settings.get("aspect") == "both" else [settings.get("aspect", "9:16")]
    if any(a not in ("9:16", "16:9") for a in aspects):
        raise ValueError("Choose 9:16 or 16:9.")
    quality = int(settings.get("quality", 720))
    if quality not in (360, 720, 1080):
        raise ValueError("Choose 360p, 720p or 1080p.")
    style = settings.get("style", "bounce")
    if style not in render.STYLES:
        raise ValueError("Choose a listed caption style.")
    mode = settings.get("webcam_mode", "auto")
    face = data["facecam"] if mode == "auto" else None
    if mode == "manual":
        norm = settings.get("webcam", [])
        if not isinstance(norm, list) or len(norm) != 4:
            raise ValueError("The webcam needs four normalized crop values.")
        norm = [finite(v, 0, 1, "Crop coordinate") for v in norm]
        face = render.validate_facecam([round(v*data["info"]["width" if i%2 == 0 else "height"]) for i,v in enumerate(norm)],
                                      data["info"]["width"], data["info"]["height"])
    elif mode not in ("auto", "none"):
        raise ValueError("Choose automatic, manual or no webcam.")
    ratio = finite(settings.get("split_ratio", .35), .2, .6, "Webcam share")
    output = Path(data["output"]) / ("exports-"+time.strftime("%H%M%S")+"-"+uuid.uuid4().hex[:5])
    output.mkdir(parents=True)
    manifest = {"status": "rendering", "outputs": [], "errors": [], "output_folder": str(output),
                "ranking_note": data["ranking_note"], "source_sha256": data["source_sha256"]}
    manifest_path = Path(data["work"]) / "exports.json"
    db.init()
    render.install_fonts()
    with ctx.as_user(auth.local_user().id):
        job = jobs.create({"type":"file", "name":data["source_name"], "path":data["source"]}, {}, enqueue=False)
        job.update(source_path=data["source"], width=data["info"]["width"], height=data["info"]["height"],
                   duration=data["info"]["duration"], status="done")
        for i, candidate in enumerate(clips):
            for aspect in aspects:
                clip = dict(candidate, id=f"clip{i+1:02d}_{aspect.replace(':','x')}", layout="webcam_top", aspect=aspect,
                            quality=quality, style=style, facecam=face, split_ratio=ratio, captions=bool(settings.get("captions", True)))
                log(f"Rendering clip {i+1}/{len(clips)}, {aspect}, {quality}p" + (", both webcam orders" if face else ", gameplay only"))
                job["clips"] = [clip]
                jobs.render_one(job, clip, data["words"])
                if clip.get("status") != "done":
                    manifest["errors"].append(clip.get("error") or "Render failed")
                    continue
                for variant in clip.get("variants") or [clip]:
                    name = variant["file"]
                    src = Path(job["dir"]) / "clips" / name
                    info = media.probe(src)
                    if abs(info["duration"]-(clip["end"]-clip["start"])) > .5:
                        raise RuntimeError("An output failed its duration check.")
                    final = output / name
                    shutil.copyfile(src, final)
                    manifest["outputs"].append(dict(file=str(final), layout=variant["layout"], aspect=aspect,
                                                    width=info["width"], height=info["height"], start=clip["start"], end=clip["end"]))
                    log(f"Saved real MP4: {final.name}")
                (output / (clip["id"]+".srt")).write_text(srt(data["words"],clip["start"],clip["end"]), encoding="utf-8")
                write_json(output / "manifest.json", manifest)
                write_json(manifest_path, manifest)
    manifest["status"] = "failed" if manifest["errors"] else "completed"
    write_json(output / "manifest.json", manifest)
    write_json(manifest_path, manifest)
    if manifest["errors"]:
        raise RuntimeError("Some renders failed: "+"; ".join(manifest["errors"]))
    log(f"Finished. {len(manifest['outputs'])} MP4(s) saved to {output}")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("analyze", "render"))
    parser.add_argument("settings", type=Path)
    args = parser.parse_args()
    configure()
    settings = json.loads(args.settings.read_text(encoding="utf-8"))
    if args.command == "analyze":
        analyze(settings)
    else:
        render_selected(settings)


if __name__ == "__main__":
    main()
