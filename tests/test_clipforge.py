"""CLIPFORGE crop validation, dual-output reliability and private source access."""
import os
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

os.environ.update(PEAKCUT_DATA=tempfile.mkdtemp(prefix="clipforge-check-"), DATABASE_URL="", PEAKCUT_ACCOUNTS="0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from studio import account, auth, ctx, db, jobs, load, media, render, server


class Clipforge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()

    def test_crop_and_shape_validation(self):
        for crop in ([-1, 0, 20, 20], [0, 0, 2000, 20], [0, 0, float("nan"), 20], [0, 0, 20]):
            with self.assertRaises(ValueError):
                render.validate_facecam(crop, 1280, 720)
        self.assertEqual(render.validate_facecam([0, 0, 300, 170], 1280, 720), [0, 0, 300, 170])
        for options in ({"aspect": "1:1"}, {"split_ratio": float("nan")}, {"split_ratio": .9}):
            with self.assertRaises(ValueError):
                jobs.clean_options(options)
        self.assertEqual(jobs.clean_options({"aspect": "16:9"})["aspect"], "16:9")

    def test_host_resources_cannot_hide_container_limits(self):
        folder = Path(os.environ["PEAKCUT_DATA"]) / "cgroup-fixture"
        folder.mkdir(exist_ok=True)
        for name, value in {"cpu.max":"200000 100000", "cpu.stat":"usage_usec 8000000\n",
                            "memory.max":"10000000000", "memory.current":"7000000000"}.items():
            (folder/name).write_text(value)
        with patch.object(load,"CGROUP_ROOT",folder), patch.object(load.time,"monotonic",return_value=20), patch.object(load.os,"sched_getaffinity",return_value={0,1,2},create=True):
            self.assertEqual(load._container_cpu_times(),(8_000_000,40_000_000))
            self.assertEqual(load._container_ram_free_gb(),3.)
            (folder/"cpu.max").write_text("max 100000")
            self.assertIsNone(load._container_cpu_times())

    def fixture(self):
        job = jobs.create({"type": "file", "name": "authorized.mp4"}, {}, enqueue=False)
        clip = dict(id="clip01", start=10., end=20., layout="webcam_top", aspect="9:16", quality=360,
                    facecam=[0, 0, 300, 170], captions=False, title="Test", description="", hashtags=[], hook="", score=50)
        source = Path(job["dir"]) / "source.mp4"
        (Path(job["dir"]) / "clips").mkdir()
        source.write_bytes(b"test fixture only")
        job.update(source_path=str(source), width=1280, height=720, duration=30., clips=[clip], status="done")
        return job, clip

    def test_both_orders_share_the_interval_and_failure_is_not_success(self):
        with ctx.as_user(auth.local_user().id):
            job, clip = self.fixture()
            calls = []
            def encode(src, folder, name, settings, words, width, height):
                calls.append(settings)
                return {"file": name+".mp4", "cover": name+".jpg", "layout": settings["layout"]}
            with patch.object(render, "render_clip", side_effect=encode):
                jobs.render_one(job, clip, [])
            self.assertEqual(clip["status"], "done")
            self.assertEqual([c["layout"] for c in calls], ["webcam_top", "gameplay_top"])
            self.assertEqual([(c["start"],c["end"]) for c in calls], [(10.,20.),(10.,20.)])
            self.assertEqual(len(clip["variants"]), 2)
            with patch.object(render, "render_clip", side_effect=[{}, RuntimeError("second encode failed")]):
                jobs.render_one(job, clip, [])
            self.assertEqual(clip["status"], "error")
            self.assertIn("second encode failed", clip["error"])

    def test_private_source_and_variant_deletion(self):
        with ctx.as_user(auth.local_user().id):
            job, clip = self.fixture()
            self.assertEqual(Path(server.source_preview(job["id"]).path), Path(job["source_path"]))
            folder = Path(job["dir"]) / "clips"
            clip.update(status="done", file="clip01.mp4", cover="clip01.jpg",
                        variants=[{"file":"clip01_gameplay_top.mp4", "cover":"clip01_gameplay_top.jpg"}])
            for name in ("clip01.mp4", "clip01.jpg", "clip01_gameplay_top.mp4", "clip01_gameplay_top.jpg", "clip01_gameplay_top.ass"):
                (folder/name).write_bytes(b"fixture")
            self.assertTrue(account.delete_clip(job["id"],clip["id"]))
            self.assertEqual(list(folder.iterdir()), [])
        with ctx.as_user("a-different-user"):
            with self.assertRaises(HTTPException) as error:
                server.source_preview(job["id"])
            self.assertEqual(error.exception.status_code,404)

    def test_no_webcam_has_no_invented_region(self):
        f = render._filter("webcam_top", 1920, None)
        self.assertNotIn("vstack", f)
        self.assertNotIn("overlay", f)
        self.assertIn("scale=1080:1920",f)

    def test_landscape_fit_preserves_a_four_by_three_source(self):
        import numpy as np
        folder = Path(os.environ["PEAKCUT_DATA"]) / "aspect-fixture"
        folder.mkdir(exist_ok=True)
        src = folder / "source.mp4"
        subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i","color=red:s=320x240:r=30",
                        "-f","lavfi","-i","sine=frequency=440","-t","1","-c:v","libx264","-c:a","aac",str(src)],check=True)
        render.install_fonts()
        out = render.render_clip(src, folder, "landscape", dict(start=0.,end=1.,aspect="16:9",layout="fit",quality=360,captions=False),[],320,240)
        raw = subprocess.check_output(["ffmpeg","-v","error","-i",str(folder/out["file"]),"-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","-"])
        frame = np.frombuffer(raw,dtype=np.uint8).reshape(360,640,3)
        self.assertLess(frame[:,20,:].mean(),5)
        self.assertGreater(frame[:,90,0].mean(),200)
        self.assertGreater(frame[:,550,0].mean(),200)
        self.assertLess(frame[:,620,:].mean(),5)

    def test_youtube_does_not_accept_cookies_or_claim_media_access(self):
        with ctx.as_user(auth.local_user().id), patch.object(server,"_quota"), patch.object(server,"_need_verified"):
            with self.assertRaises(HTTPException) as error:
                server.create_from_link({"url":"https://youtu.be/authorized-but-no-media-adapter"})
            self.assertEqual(error.exception.status_code,400)
            self.assertIn("permitted media-access adapter",error.exception.detail)
        self.assertEqual(media.cookie_opts(),{})


if __name__ == "__main__":
    unittest.main()
