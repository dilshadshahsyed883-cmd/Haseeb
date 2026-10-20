"""Haseeb Audio Cutter — independent Windows desktop application."""
from pathlib import Path
import argparse
import math
import queue
import subprocess
import sys
import tempfile
import threading
import wave

from audio_engine import INPUTS, OUTPUTS, duration, export, ffmpeg, parse_time, stamp, range_length, waveform

BG="#0f1624"
PANEL="#1b2637"
SUB="#25344b"
ACCENT="#46dfc1"
TEXT="#edf5ff"
MUTED="#a1aec5"

def self_test():
    import struct
    with tempfile.TemporaryDirectory(prefix="haseeb-audio-check-") as tmp:
        src=Path(tmp)/"tone.wav"
        with wave.open(str(src),"wb") as sound:
            sound.setnchannels(1)
            sound.setsampwidth(2)
            sound.setframerate(16000)
            sound.writeframes(b"".join(struct.pack("<h",int(13000*math.sin(i*math.tau*440/16000))) for i in range(16000)))
        out=export(src,Path(tmp)/"clip.mp3",.2,.7,duration(src),True)
        if out.stat().st_size<500 or not .4<=duration(out)<=.7:
            raise RuntimeError("Actual FFmpeg MP3 trimming smoke test failed")
    print("Haseeb Audio Cutter PASS: decode, precise trim, verified MP3 output")

class Window:
    def __init__(self,root):
        import tkinter as tk
        from tkinter import filedialog,messagebox
        self.tk=tk
        self.ask=filedialog
        self.message=messagebox
        self.root=root
        self.source=None
        self.seconds=0.
        self.peaks=[]
        self.drag=None
        self.busy=False
        self.results=queue.Queue()
        self.start=tk.StringVar(value="00:00:00.000")
        self.end=tk.StringVar(value="00:00:00.000")
        self.file=tk.StringVar(value="No audio selected")
        self.info=tk.StringVar(value="MP3 · WAV · M4A · FLAC · OGG · AAC")
        self.selection=tk.StringVar(value="SELECTION  —")
        self.status=tk.StringVar(value="Ready. Choose your source audio.")
        self.ext=tk.StringVar(value="MP3")
        self.fade=tk.BooleanVar(value=True)
        self.build()
        root.after(120,self.poll)
        root.protocol("WM_DELETE_WINDOW",self.close)

    def label(self,parent,text,size=10,color=TEXT,bold=False,bg=PANEL):
        return self.tk.Label(parent,text=text,bg=bg,fg=color,
                             font=("Segoe UI",size,"bold" if bold else "normal"))

    def button(self,parent,text,callback,primary=False):
        return self.tk.Button(parent,text=text,command=callback,bg=ACCENT if primary else SUB,
                              fg=BG if primary else TEXT,activebackground="#82f3df" if primary else "#344968",
                              activeforeground=BG if primary else TEXT,bd=0,relief="flat",padx=16,pady=10,
                              font=("Segoe UI",10,"bold"),cursor="hand2",highlightthickness=0)

    def section(self,parent,title):
        f=self.tk.Frame(parent,bg=PANEL,padx=22,pady=16,
                        highlightthickness=1,highlightbackground="#30415c")
        self.label(f,title,11,ACCENT,True).pack(anchor="w")
        return f

    def build(self):
        tk=self.tk
        self.root.title("Haseeb | Audio Cutter")
        self.root.geometry("1090x740")
        self.root.minsize(820,625)
        self.root.configure(bg=BG)
        header=tk.Frame(self.root,bg=BG,padx=34,pady=24)
        header.pack(fill="x")
        self.label(header,"HASEEB  /  AUDIO CUTTER",22,TEXT,True,BG).pack(anchor="w")
        self.label(header,"Import  ·  Waveform  ·  Precise trim  ·  Preview  ·  Export",10,MUTED,bg=BG).pack(anchor="w",pady=(7,0))
        body=tk.Frame(self.root,bg=BG,padx=34)
        body.pack(fill="both",expand=True)
        filebox=self.section(body,"01   SOURCE AUDIO")
        filebox.pack(fill="x")
        self.button(filebox,"Browse audio…",self.open,True).pack(side="right",padx=(10,0))
        tk.Label(filebox,textvariable=self.file,bg=PANEL,fg=TEXT,anchor="w",
                 font=("Segoe UI",13,"bold")).pack(fill="x",pady=(9,4))
        tk.Label(filebox,textvariable=self.info,bg=PANEL,fg=MUTED,anchor="w",
                 font=("Segoe UI",9)).pack(fill="x")
        timeline=self.section(body,"02   WAVEFORM & SELECTION")
        timeline.pack(fill="both",expand=True,pady=(14,0))
        self.canvas=tk.Canvas(timeline,height=150,bg="#111c2c",bd=0,highlightthickness=0,cursor="crosshair")
        self.canvas.pack(fill="both",expand=True,pady=(14,0))
        self.canvas.bind("<Configure>",lambda event:self.draw())
        self.canvas.bind("<Button-1>",self.down)
        self.canvas.bind("<B1-Motion>",self.move)
        self.canvas.bind("<ButtonRelease-1>",lambda event:setattr(self,"drag",None))
        labels=tk.Frame(timeline,bg=PANEL)
        labels.pack(fill="x")
        self.label(labels,"0:00",9,MUTED).pack(side="left")
        self.last_time=self.label(labels,"0:00",9,MUTED)
        self.last_time.pack(side="right")
        self.label(timeline,"Drag a highlighted boundary handle, or type start/end timestamps.",9,MUTED).pack(anchor="w",pady=(7,0))
        settings=tk.Frame(body,bg=BG)
        settings.pack(fill="x",pady=(14,0))
        left=self.section(settings,"03   CUT RANGE")
        left.pack(side="left",fill="both",expand=True)
        times=tk.Frame(left,bg=PANEL)
        times.pack(fill="x",pady=(12,5))
        for caption,variable in (("START",self.start),("END",self.end)):
            group=tk.Frame(times,bg=PANEL)
            group.pack(side="left",fill="x",expand=True,padx=(0,11))
            self.label(group,caption,9,MUTED,True).pack(anchor="w")
            inp=tk.Entry(group,textvariable=variable,bg=SUB,fg=TEXT,insertbackground=TEXT,
                         relief="flat",font=("Consolas",13))
            inp.pack(fill="x",ipady=9,pady=(6,0))
            inp.bind("<Return>",self.changed)
            inp.bind("<FocusOut>",self.changed)
        tk.Label(left,textvariable=self.selection,bg=PANEL,fg=ACCENT,
                 font=("Segoe UI",10,"bold"),anchor="w").pack(fill="x",pady=(5,10))
        shortcuts=tk.Frame(left,bg=PANEL)
        shortcuts.pack(fill="x")
        for text,fn in (("Full audio",self.full),("First 30 sec",lambda:self.preset(False)),
                        ("Last 30 sec",lambda:self.preset(True))):
            self.button(shortcuts,text,fn).pack(side="left",padx=(0,8))
        right=self.section(settings,"04   EXPORT SETTINGS")
        right.configure(width=317)
        right.pack(side="left",fill="y",padx=(14,0))
        right.pack_propagate(False)
        fmt=tk.Frame(right,bg=PANEL)
        fmt.pack(fill="x",pady=(14,8))
        self.label(fmt,"Output format",10,MUTED).pack(side="left")
        chooser=tk.OptionMenu(fmt,self.ext,*[x[1:].upper() for x in OUTPUTS])
        chooser.configure(bg=SUB,fg=TEXT,bd=0,relief="flat",highlightthickness=0,width=7)
        chooser["menu"].configure(bg=SUB,fg=TEXT)
        chooser.pack(side="right")
        tk.Checkbutton(right,text="Soft fade at cut edges",variable=self.fade,bg=PANEL,
                       fg=TEXT,activebackground=PANEL,activeforeground=TEXT,
                       selectcolor=SUB,font=("Segoe UI",10)).pack(anchor="w")
        self.label(right,"Original files are never modified.",9,MUTED).pack(anchor="w",pady=(10,0))
        action=tk.Frame(body,bg=BG)
        action.pack(fill="x",pady=(15,0))
        self.button(action,"▶  Preview 30 sec",self.preview).pack(side="left",padx=(0,10))
        self.button(action,"■  Stop",self.stop).pack(side="left")
        self.button(action,"Export selected audio  →",self.save,True).pack(side="right")
        footer=tk.Frame(self.root,bg=BG,padx=34,pady=16)
        footer.pack(fill="x")
        tk.Label(footer,textvariable=self.status,bg=BG,fg=MUTED,
                 font=("Segoe UI",10),anchor="w").pack(side="left")
        self.label(footer,"v1.0.0",9,MUTED,bg=BG).pack(side="right")
        self.draw()

    def setstatus(self,text):
        self.status.set(text)

    def task(self,title,run,callback):
        if self.busy:
            self.setstatus("Please wait for the current operation")
            return
        self.busy=True
        self.setstatus(title)
        def worker():
            try:self.results.put((callback,run(),None))
            except Exception as err:self.results.put((callback,None,err))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        while True:
            try:fn,result,error=self.results.get_nowait()
            except queue.Empty:break
            self.busy=False
            if error:
                self.setstatus(str(error))
                self.message.showerror("Audio Cutter",str(error))
            else:fn(result)
        self.root.after(120,self.poll)

    def open(self):
        choice=self.ask.askopenfilename(title="Select audio file",filetypes=[
            ("Supported audio"," ".join("*"+x for x in INPUTS)),("All files","*.*")])
        if not choice:return
        path=Path(choice)
        def load():
            seconds=duration(path)
            return path,seconds,waveform(path,seconds)
        def ready(result):
            self.source,self.seconds,self.peaks=result
            self.file.set(self.source.name)
            self.info.set(f"{self.source.suffix[1:].upper()}   •   {stamp(self.seconds)}   •   {self.source.parent}")
            self.last_time.configure(text=stamp(self.seconds))
            self.full()
            self.setstatus("Audio loaded. Select your cut and export.")
        self.task("Decoding audio waveform…",load,ready)

    def selection_times(self):
        if not self.source:raise ValueError("Choose audio first")
        start,end=parse_time(self.start.get()),parse_time(self.end.get())
        range_length(start,end,self.seconds)
        return start,min(end,self.seconds)

    def changed(self,event=None):
        if not self.source:return
        try:
            start,end=self.selection_times()
            self.start.set(stamp(start))
            self.end.set(stamp(end))
            self.selection.set("SELECTION  "+stamp(end-start))
            self.draw()
        except ValueError as error:self.setstatus(str(error))

    def full(self):
        if not self.source:return
        self.start.set(stamp(0))
        self.end.set(stamp(self.seconds))
        self.changed()

    def preset(self,last):
        if not self.source:return
        lo=max(0,self.seconds-30) if last else 0
        hi=self.seconds if last else min(30,self.seconds)
        self.start.set(stamp(lo))
        self.end.set(stamp(hi))
        self.changed()

    def draw(self):
        if not hasattr(self,"canvas"):return
        c=self.canvas
        c.delete("all")
        w=max(280,c.winfo_width())
        h=max(80,c.winfo_height())
        mid=h/2
        c.create_line(0,mid,w,mid,fill="#41516a")
        if not self.peaks:
            c.create_text(w/2,mid,text="Waveform appears when audio is imported",fill=MUTED,
                          font=("Segoe UI",11))
            return
        try:start,end=self.selection_times()
        except ValueError:start,end=0,self.seconds
        left,right=w*start/self.seconds,w*end/self.seconds
        c.create_rectangle(left,0,right,h,fill="#214440",outline="")
        group=max(1,int(len(self.peaks)/(w/3)))
        for i in range(0,len(self.peaks),group):
            value=max(self.peaks[i:i+group])
            x=i*w/len(self.peaks)
            amp=max(2,value*h*.42)
            c.create_line(x,mid-amp,x,mid+amp,fill=ACCENT if left<=x<=right else "#60708a",width=2)
        for x in (left,right):
            c.create_line(x,0,x,h,fill=ACCENT,width=3)
            c.create_rectangle(x-5,0,x+5,16,fill=ACCENT,outline="")

    def down(self,event):
        if not self.source:return
        try:a,b=self.selection_times()
        except ValueError:return
        w=max(1,self.canvas.winfo_width())
        self.drag="start" if abs(event.x-w*a/self.seconds)<abs(event.x-w*b/self.seconds) else "end"
        self.move(event)

    def move(self,event):
        if not self.source or not self.drag:return
        try:start,end=self.selection_times()
        except ValueError:return
        t=max(0,min(self.seconds,event.x/max(1,self.canvas.winfo_width())*self.seconds))
        if self.drag=="start":self.start.set(stamp(min(t,end-.04)))
        else:self.end.set(stamp(max(t,start+.04)))
        self.changed()

    def stop(self):
        if sys.platform=="win32":
            import winsound
            winsound.PlaySound(None,0)
        self.setstatus("Preview stopped")

    def preview(self):
        try:start,end=self.selection_times()
        except ValueError as error:
            self.setstatus(str(error));return
        def run():
            import winsound
            target=Path(tempfile.gettempdir())/"haseeb-audio-cutter-preview.wav"
            args=[ffmpeg(),"-hide_banner","-loglevel","error","-nostdin","-y",
                  "-i",str(self.source),"-ss",f"{start:.3f}","-t",f"{min(30,end-start):.3f}",
                  "-vn","-ac","2","-ar","22050","-c:a","pcm_s16le",str(target)]
            p=subprocess.run(args,capture_output=True,timeout=90)
            if p.returncode:
                raise RuntimeError("Preview failed: "+p.stderr.decode(errors="replace")[-250:])
            winsound.PlaySound(str(target),winsound.SND_FILENAME|winsound.SND_ASYNC)
            return min(30,end-start)
        self.task("Preparing preview…",run,
                  lambda seconds:self.setstatus(f"Preview playing ({seconds:.1f} sec max)"))

    def save(self):
        try:start,end=self.selection_times()
        except ValueError as error:
            self.setstatus(str(error));return
        suffix="."+self.ext.get().lower()
        name=f"{self.source.stem}_cut_{round(start*1000)}-{round(end*1000)}{suffix}"
        path=self.ask.asksaveasfilename(title="Save trimmed audio",defaultextension=suffix,
                                        initialfile=name,filetypes=[(self.ext.get()+" audio","*"+suffix)])
        if not path:return
        if Path(path).exists():
            self.message.showerror("File exists","Choose a new filename; Audio Cutter never overwrites files.")
            return
        source=self.source
        fades=self.fade.get()
        self.task("Exporting audio…",lambda:export(source,Path(path),start,end,self.seconds,fades),
                  lambda saved:(self.setstatus("Exported: "+str(saved)),
                                self.message.showinfo("Export complete","Saved to:\n"+str(saved)+"\n\nOriginal file untouched.")))

    def close(self):
        try:self.stop()
        except Exception:pass
        self.root.destroy()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        self_test()
    else:
        import tkinter as tk
        root=tk.Tk()
        Window(root)
        root.mainloop()

if __name__=="__main__":
    main()
