#!/usr/bin/env python3
"""FrankieXGM 1.0.0 - graphical front end."""

import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import FrankieXGM as engine

APP_VERSION = "1.0.0"
AUTHOR_URL = "https://linktr.ee/lukemcqueen_"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FrankieXGM")
        self.geometry("720x560")
        self.minsize(650, 500)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.video_var = tk.StringVar(value="NTSC")
        self.pcm_mode = tk.StringVar(value="unchanged")
        self.gain_var = tk.StringVar(value="0")
        self.delay_keyoff_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready.")

        self._build()

    def _build(self):
        pad = {"padx": 10, "pady": 6}
        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="FrankieXGM", font=("TkDefaultFont", 20, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(main, text="Mega Drive VGM/VGZ → XGM 1.01").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

        ttk.Label(main, text="Input VGM/VGZ:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(main, textvariable=self.input_var).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(main, text="Browse…", command=self.pick_input).grid(row=2, column=2, **pad)

        ttk.Label(main, text="Output XGM:").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(main, textvariable=self.output_var).grid(row=3, column=1, sticky="ew", **pad)
        ttk.Button(main, text="Browse…", command=self.pick_output).grid(row=3, column=2, **pad)

        video = ttk.LabelFrame(main, text="Video standard", padding=8)
        video.grid(row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=8)
        ttk.Radiobutton(video, text="NTSC (60 Hz)", value="NTSC", variable=self.video_var).pack(side="left", padx=8)
        ttk.Radiobutton(video, text="PAL (50 Hz)", value="PAL", variable=self.video_var).pack(side="left", padx=8)

        pcm = ttk.LabelFrame(main, text="PCM volume", padding=8)
        pcm.grid(row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=8)
        ttk.Radiobutton(pcm, text="Unchanged", value="unchanged", variable=self.pcm_mode,
                        command=self.update_gain_state).grid(row=0, column=0, sticky="w", padx=8)
        ttk.Radiobutton(pcm, text="Automatic normalization", value="normalize", variable=self.pcm_mode,
                        command=self.update_gain_state).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Radiobutton(pcm, text="Manual gain:", value="gain", variable=self.pcm_mode,
                        command=self.update_gain_state).grid(row=0, column=2, sticky="w", padx=8)
        self.gain_entry = ttk.Entry(pcm, textvariable=self.gain_var, width=8)
        self.gain_entry.grid(row=0, column=3, padx=(2, 4))
        ttk.Label(pcm, text="dB").grid(row=0, column=4, sticky="w")
        ttk.Label(pcm, text="Automatic mode targets RMS ≈ −14.9 dBFS with a −3 dBFS peak ceiling.").grid(
            row=1, column=0, columnspan=5, sticky="w", padx=8, pady=(6, 0))

        opts = ttk.LabelFrame(main, text="Timing", padding=8)
        opts.grid(row=6, column=0, columnspan=3, sticky="ew", padx=10, pady=8)
        ttk.Checkbutton(opts, text="Delayed YM key-off (XGMTool-compatible behavior)",
                        variable=self.delay_keyoff_var).pack(anchor="w", padx=8)

        buttons = ttk.Frame(main)
        buttons.grid(row=7, column=0, columnspan=3, pady=10)
        self.convert_btn = ttk.Button(buttons, text="Convert", command=self.start_conversion)
        self.convert_btn.pack(side="left", padx=6)
        ttk.Button(buttons, text="About", command=self.show_info).pack(side="left", padx=6)

        ttk.Label(main, text="Status / conversion log:").grid(row=8, column=0, columnspan=3, sticky="w", padx=10)
        self.log = tk.Text(main, height=12, wrap="word", state="disabled")
        self.log.grid(row=9, column=0, columnspan=3, sticky="nsew", padx=10, pady=(4, 10))
        scroll = ttk.Scrollbar(main, orient="vertical", command=self.log.yview)
        scroll.grid(row=9, column=3, sticky="ns", pady=(4, 10))
        self.log.configure(yscrollcommand=scroll.set)

        ttk.Label(main, textvariable=self.status_var).grid(row=10, column=0, columnspan=3, sticky="w", padx=10)

        main.columnconfigure(1, weight=1)
        main.rowconfigure(9, weight=1)
        self.update_gain_state()

    def update_gain_state(self):
        state = "normal" if self.pcm_mode.get() == "gain" else "disabled"
        self.gain_entry.configure(state=state)

    def pick_input(self):
        p = filedialog.askopenfilename(
            title="Select VGM/VGZ input",
            filetypes=[("VGM files", "*.vgm"), ("VGZ files", "*.vgz"), ("VGM/VGZ", "*.vgm *.vgz"), ("All files", "*.*")]
        )
        if p:
            self.input_var.set(p)
            if not self.output_var.get():
                self.output_var.set(str(Path(p).with_suffix(".xgm")))

    def pick_output(self):
        p = filedialog.asksaveasfilename(
            title="Select XGM output",
            defaultextension=".xgm",
            filetypes=[("XGM files", "*.xgm"), ("All files", "*.*")]
        )
        if p:
            self.output_var.set(p)

    def append_log(self, text):
        self.after(0, self._append_log, text)

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def show_info(self):
        win = tk.Toplevel(self)
        win.title("About FrankieXGM")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=22)
        frame.pack()
        ttk.Label(frame, text="FrankieXGM v1.0.0", font=("TkDefaultFont", 15, "bold")).pack(pady=(0, 8))
        row = ttk.Frame(frame)
        row.pack()
        ttk.Label(row, text="by ").pack(side="left")
        link = tk.Label(row, text="Luke McQueen", fg="blue", cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: webbrowser.open(AUTHOR_URL))
        ttk.Label(frame, text="Based on XGMTool by Stephane Dallongeville").pack(pady=(6, 12))
        ttk.Button(frame, text="Close", command=win.destroy).pack()

    def start_conversion(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        if not inp:
            messagebox.showerror("FrankieXGM", "Please select a VGM/VGZ input file.")
            return
        if not out:
            messagebox.showerror("FrankieXGM", "Please select an XGM output file.")
            return
        if Path(out).suffix.lower() != ".xgm":
            out += ".xgm"
            self.output_var.set(out)

        try:
            gain = float(self.gain_var.get()) if self.pcm_mode.get() == "gain" else None
        except ValueError:
            messagebox.showerror("FrankieXGM", "Manual PCM gain must be a number in dB.")
            return

        self.convert_btn.configure(state="disabled")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.status_var.set("Converting…")

        t = threading.Thread(target=self._convert_worker,
                             args=(inp, out, gain), daemon=True)
        t.start()

    def _convert_worker(self, inp, out, gain):
        import contextlib
        import io

        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                data = engine.load_vgm(Path(inp))
                result, info = engine.convert(
                    data,
                    True if self.video_var.get() == "NTSC" else False,
                    self.pcm_mode.get() == "normalize",
                    gain,
                    self.delay_keyoff_var.get()
                )
                Path(out).write_bytes(result)
                print(f"Converted: {inp} -> {out}")
                print(f"XGM: {info['frames']} frames ({info['seconds']:.2f}s), "
                      f"{info['samples']} PCM samples, {info['sample_bytes']} bytes PCM")
                print(f"YM2612/PSG events: {info['fm_psg_events']}; "
                      f"SegaPCM starts: {info['pcm_starts']}; "
                      f"GD3: {'yes' if info['gd3'] else 'no'}")
            self.append_log(buf.getvalue().rstrip())
            self.after(0, self._success, out)
        except Exception as exc:
            self.append_log(traceback.format_exc().rstrip())
            self.after(0, self._failure, str(exc))

    def _success(self, out):
        self.convert_btn.configure(state="normal")
        self.status_var.set("Conversion complete.")
        messagebox.showinfo("FrankieXGM", f"Conversion complete.\n\nOutput:\n{out}")

    def _failure(self, msg):
        self.convert_btn.configure(state="normal")
        self.status_var.set("Conversion failed.")
        messagebox.showerror("FrankieXGM", msg)

if __name__ == "__main__":
    App().mainloop()
