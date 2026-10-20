"""Haseeb Audio Cutter: safe audio file trimming via bundled FFmpeg."""
from array import array
from pathlib import Path
import math
import re
import shutil
import subprocess
import sys
import wave

INPUTS=(".mp3",".wav",".m4a",".aac",".flac",".ogg",".opus",".wma",".aiff")
OUTPUTS=(".mp3",".wav",".m4a",".flac",".ogg")
RE_DURATION=re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")

def ffmpeg():
    local=Path(__file__).resolve().parent/"bin"/"ffmpeg.exe"
    if local.is_file():
        return str(local)
    found=shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("FFmpeg missing from Audio Cutter package")

def parse_time(value):
    parts=value.strip().split(":")
    if not 1<=len(parts)<=3:
        raise ValueError("Use HH:MM:SS.mmm or MM:SS")
    try:
        values=[float(x) for x in parts]
    except ValueError as exc:
        raise ValueError("Invalid time") from exc
    if any(not math.isfinite(x) or x<0 for x in values) or any(x>=60 for x in values[1:]):
        raise ValueError("Invalid minutes or seconds")
    n=0
    for x in values:
        n=n*60+x
    return n

def stamp(seconds):
    msecs=round(max(0,seconds)*1000)
    hh,rem=divmod(msecs,3600000)
    mm,rem=divmod(rem,60000)
    ss,ms=divmod(rem,1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"

def range_length(start,end,duration):
    if not all(map(math.isfinite,(start,end,duration))) or duration<=0 or start<0 or end<=start or end>duration+.02:
        raise ValueError("Choose a valid start and end within the recording")
    return end-start

def duration(source):
    source=Path(source)
    if not source.is_file():
        raise FileNotFoundError("Audio source not found")
    if source.suffix.lower()==".wav":
        try:
            with wave.open(str(source),"rb") as sound:
                n=sound.getnframes()/sound.getframerate()
                if n>0: return n
        except (wave.Error,ValueError,EOFError):
            pass
    result=subprocess.run([ffmpeg(),"-hide_banner","-nostdin","-i",str(source)],
                          capture_output=True,text=True,errors="replace",timeout=35)
    found=RE_DURATION.search(result.stderr+result.stdout)
    if not found:
        raise ValueError("Could not read recording duration")
    hh,mm,ss=found.groups()
    return int(hh)*3600+int(mm)*60+float(ss)

def waveform(source,total,bars=750):
    cmd=[ffmpeg(),"-hide_banner","-loglevel","error","-nostdin","-i",str(source),
         "-t",str(min(total,7200)),"-vn","-ac","1","-ar","800","-f","s16le","pipe:1"]
    proc=subprocess.run(cmd,capture_output=True,timeout=100)
    if proc.returncode:
        raise RuntimeError("Could not decode waveform: "+proc.stderr.decode(errors="replace")[-250:])
    data=proc.stdout[:11520000]
    samples=array("h")
    samples.frombytes(data[:len(data)//2*2])
    if not samples: return [0.01]*bars
    window=max(1,math.ceil(len(samples)/bars))
    values=[min(1.,max(abs(v) for v in samples[i:i+window])/32768)
            for i in range(0,len(samples),window)]
    return (values+[0.]*bars)[:bars]

def export(source,target,start,end,total,soft=True):
    source,target=Path(source),Path(target)
    length=range_length(start,end,total)
    if source.resolve()==target.resolve():
        raise ValueError("Cannot overwrite original recording")
    if target.exists():
        raise FileExistsError("Output already exists. Choose another filename.")
    if not target.parent.is_dir():
        raise FileNotFoundError("Export folder unavailable")
    formats={
        ".mp3":["-c:a","libmp3lame","-b:a","192k"],
        ".wav":["-c:a","pcm_s16le"],
        ".m4a":["-c:a","aac","-b:a","192k"],
        ".flac":["-c:a","flac"],
        ".ogg":["-c:a","libvorbis","-q:a","5"],
    }
    if target.suffix.lower() not in formats:
        raise ValueError("Unsupported export format")
    command=[ffmpeg(),"-hide_banner","-loglevel","error","-nostdin","-n",
             "-i",str(source),"-ss",f"{start:.3f}","-t",f"{length:.3f}",
             "-vn","-sn","-dn","-map","0:a:0"]
    if soft and length>.4:
        fade=min(.25,length/4)
        command+=["-af",f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={length-fade:.3f}:d={fade:.3f}"]
    command+=formats[target.suffix.lower()]+[str(target)]
    try:
        result=subprocess.run(command,capture_output=True,text=True,errors="replace",timeout=1200)
        if result.returncode:
            raise RuntimeError("FFmpeg export failed: "+result.stderr[-500:])
        if not target.exists() or target.stat().st_size<50:
            raise RuntimeError("Export produced no usable audio")
        return target
    except Exception:
        if target.exists(): target.unlink()
        raise
