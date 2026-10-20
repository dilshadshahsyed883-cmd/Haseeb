"""Read-only local PC readiness dashboard; never displays secrets."""
import argparse
import shutil
import sys


def tools():
    return {
        "Python": sys.executable,
        "Git": shutil.which("git"),
        "GitHub CLI": shutil.which("gh"),
        "Tailscale": shutil.which("tailscale"),
        "rclone": shutil.which("rclone"),
    }


def ui():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("Haseeb | PC Control Center")
    root.geometry("690x450")
    root.minsize(540, 350)
    panel = ttk.Frame(root, padding=26)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="HASEEB  /  PC CONTROL CENTER",
              font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(panel, text="Installed tools and local deployment readiness").pack(anchor="w", pady=(8, 24))
    rows = {}
    for name, detected in tools().items():
        row = ttk.Frame(panel)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text=name, width=20).pack(side="left")
        label = ttk.Label(row, text="Available" if detected else "Not detected")
        label.pack(side="left")
        rows[name] = label
    def refresh():
        for key, value in tools().items():
            rows[key].configure(text="Available" if value else "Not detected")
    ttk.Button(panel, text="Refresh", command=refresh).pack(anchor="w", pady=(18, 0))
    ttk.Label(panel, text="Local status only. Login tokens are never read by this app.").pack(
        anchor="w", pady=(18, 0))
    root.mainloop()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    arg = p.parse_args()
    if arg.self_test:
        assert tools()["Python"]
        print("Haseeb Control Center PASS")
    else:
        ui()
