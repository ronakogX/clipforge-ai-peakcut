"""Boundaries for the notebook adapter. No Google account or network is used."""
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('colab_runner',Path(__file__).resolve().parents[1]/'tools/colab_runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class NotebookBoundaries(unittest.TestCase):
    def test_large_sources_are_bounded_without_loading_them(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4'
            with source.open('wb') as f: f.truncate(runner.MAX_BYTES+1)
            with self.assertRaises(ValueError): runner.source_file(source)
            source.write_bytes(b'fixture')
            self.assertEqual(runner.source_file(source),source.resolve())

    def test_nan_and_infinite_ranges_are_rejected(self):
        for value in (float('nan'),float('inf'),-1,61):
            with self.assertRaises(ValueError): runner.finite(value,0,60,'time')

    def test_srt_tracks_original_timestamps_after_trim(self):
        words=[dict(w='before',s=599,e=599.9),dict(w='hello',s=600.2,e=600.7),dict(w='world',s=601,e=601.5),dict(w='after',s=604,e=605)]
        result=runner.srt(words,600,602)
        self.assertIn('00:00:00,200 --> 00:00:01,500',result)
        self.assertIn('hello world',result)
        self.assertNotIn('before',result)
        self.assertNotIn('after',result)

    def test_ranking_can_select_a_moment_after_ten_minutes(self):
        os.environ['PEAKCUT_DATA']=tempfile.mkdtemp(prefix='cf-global-rank-')
        runner.configure()
        from studio import brain
        import numpy as np
        words=[]
        for start in (20,610):
            words += [dict(w=w,s=start+i*.8,e=start+i*.8+.7) for i,w in enumerate('A player reacts to a surprising victory and tells the whole story.'.split())]
        levels=np.full(700,-60.)
        levels[610:625]=0
        candidates,_=brain.find_clips(words,levels,700,max_clips=1,min_len=5,max_len=15,log=lambda x:None)
        self.assertTrue(candidates)
        self.assertGreater(candidates[0]['start'],590)


if __name__=='__main__': unittest.main()
