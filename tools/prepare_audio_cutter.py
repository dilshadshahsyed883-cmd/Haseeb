"""Create self-contained Windows Audio Cutter release using pinned FFmpeg."""
from pathlib import Path
import shutil
import subprocess
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"apps"/"audio_cutter"

def main():
    source=Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not source.is_file() or source.suffix.lower()!=".exe":
        raise RuntimeError("Expected self-contained Windows FFmpeg executable")
    dest=APP/"bin"/"ffmpeg.exe"
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,dest)
    license_text=subprocess.run([str(dest),"-L"],capture_output=True,text=True,timeout=30,check=True)
    (APP/"FFMPEG_LICENSE.txt").write_text(license_text.stdout+"\n"+license_text.stderr,encoding="utf-8")
    print(f"Bundled Windows FFmpeg: {dest.stat().st_size:,} bytes; legal notice included")

if __name__=="__main__":
    main()
