"""Audio Cutter safe range and format tests; no user data."""
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
import wave

src=Path(__file__).resolve().parents[1]/"apps"/"audio_cutter"/"audio_engine.py"
spec=importlib.util.spec_from_file_location("haseeb_audio_engine",src)
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

class AudioCutterTests(unittest.TestCase):
    def test_times(self):
        self.assertEqual(engine.parse_time("01:02:03.500"),3723.5)
        self.assertEqual(engine.parse_time("1:30.250"),90.25)
        self.assertEqual(engine.stamp(3723.5),"01:02:03.500")
        for bad in ("","ab","-3","1:65","1:2:80","NaN","inf","1:2:3:4"):
            with self.subTest(value=bad),self.assertRaises(ValueError):
                engine.parse_time(bad)

    def test_ranges(self):
        self.assertAlmostEqual(engine.range_length(.3,1.2,3),.9)
        for vals in ((1,1,3),(-1,2,4),(3,5,4),(0,2,0),(math.nan,2,5)):
            with self.subTest(values=vals),self.assertRaises(ValueError):
                engine.range_length(*vals)

    def test_wav(self):
        with tempfile.TemporaryDirectory() as folder:
            src=Path(folder)/"tone.wav"
            with wave.open(str(src),"wb") as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
                w.writeframes(b"\0\0"*12000)
            self.assertEqual(engine.duration(src),1.5)

    def test_originals_protected(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"sample.mp3"
            source.write_bytes(b"owner-data")
            with self.assertRaises(ValueError):
                engine.export(source,source,0,1,2)
            with self.assertRaises(FileExistsError):
                engine.export(Path(folder)/"other.mp3",source,0,1,2)
            self.assertEqual(source.read_bytes(),b"owner-data")

if __name__=="__main__":
    unittest.main()
