"""usb2msxjoy / usb2mdjoy ボタン割り当て設定ツール (tkinter)

    python3 config_gui.py

設定は UF2 として書き出し、BOOTSEL モードの Pico (RPI-RP2 ドライブ) にコピーすると
フラッシュ末尾の設定領域だけが書き換わる (ファームウェアはそのまま)。
"""

import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import u2jconfig as u2j  # noqa: E402

TARGET_NAMES = {"MSX": "MSX", "MD": "メガドライブ (3ボタン)"}

# キーボードのキーが何番のボタンになるか (ファームウェアの gp_decode_keyboard と同じ)
KEY_HINTS = {0: "キーボード Space / Z", 1: "キーボード X / M", 2: "キーボード C", 9: "キーボード Enter"}


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=10)
        self.root = root
        root.title("USB → 9ピン ジョイスティック 設定")
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.target = tk.StringVar(value="MSX")
        self.turbo = tk.IntVar(value=15)
        self.cancel = tk.BooleanVar(value=True)
        self.actions = [tk.StringVar() for _ in range(u2j.NUM_BUTTONS)]
        self.status = tk.StringVar()

        self._build()
        self.set_config(u2j.Config.default("MSX"))
        self.status.set("既定値を表示しています")

    # --- 画面 ---
    def _build(self):
        top = ttk.LabelFrame(self, text="全般", padding=8)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="接続先:").grid(row=0, column=0, sticky="w")
        for i, (key, name) in enumerate(TARGET_NAMES.items()):
            ttk.Radiobutton(top, text=name, value=key, variable=self.target,
                            command=self.on_target_changed).grid(row=0, column=1 + i, sticky="w", padx=4)
        ttk.Label(top, text="連射速度 (Hz):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(top, from_=1, to=30, textvariable=self.turbo, width=5).grid(
            row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Checkbutton(top, text="スティック / 十字キーの上下・左右同時入力を打ち消す",
                        variable=self.cancel).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        grid = ttk.LabelFrame(self, text="ボタン割り当て", padding=8)
        grid.grid(row=1, column=0, sticky="nsew", pady=8)
        self.columnconfigure(0, weight=1)
        self.combos = []
        for i in range(u2j.NUM_BUTTONS):
            r, c = i % 8, (i // 8) * 3
            ttk.Label(grid, text=f"ボタン {i + 1}").grid(row=r, column=c, sticky="w", padx=(0, 4), pady=2)
            cb = ttk.Combobox(grid, textvariable=self.actions[i], state="readonly", width=14)
            cb.grid(row=r, column=c + 1, sticky="w", pady=2)
            self.combos.append(cb)
            ttk.Label(grid, text=KEY_HINTS.get(i, ""), foreground="gray").grid(
                row=r, column=c + 2, sticky="w", padx=(4, 16))
        ttk.Label(grid, foreground="gray",
                  text="ボタン番号はパッドによって違います。押したボタンの番号は UART ログ (GP0, 115200bps) に表示されます。"
                  ).grid(row=8, column=0, columnspan=6, sticky="w", pady=(6, 0))

        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew")
        ttk.Button(bar, text="既定値に戻す", command=self.on_default).pack(side="left")
        ttk.Button(bar, text="開く…", command=self.on_open).pack(side="left", padx=4)
        ttk.Button(bar, text="JSON 保存…", command=self.on_save_json).pack(side="left")
        ttk.Button(bar, text="UF2 書き出し…", command=self.on_save_uf2).pack(side="left", padx=4)
        b = ttk.Button(bar, text="Pico から読み込み", command=self.on_read_pico)
        b.pack(side="right")
        if not shutil.which("picotool"):
            b.state(["disabled"])
        ttk.Button(bar, text="Pico に書き込み", command=self.on_write_pico).pack(side="right", padx=4)

        ttk.Label(self, textvariable=self.status, foreground="gray").grid(row=3, column=0, sticky="w", pady=(8, 0))

    # --- 設定 <-> 画面 ---
    def labels(self):
        return u2j.ACTION_LABELS[self.target.get()]

    def refresh_choices(self):
        names = list(self.labels().values())
        for cb in self.combos:
            cb["values"] = names

    def set_config(self, cfg):
        self.target.set(cfg.target)
        self.turbo.set(cfg.turbo_hz)
        self.cancel.set(cfg.cancel_opposite)
        self.refresh_choices()
        labels = self.labels()
        for var, act in zip(self.actions, cfg.buttons):
            var.set(labels.get(act, labels["NONE"]))

    def get_config(self):
        rev = {v: k for k, v in self.labels().items()}
        try:
            hz = int(self.turbo.get())
        except (tk.TclError, ValueError):
            raise ValueError("連射速度は数値で入力してください")
        cfg = u2j.Config(target=self.target.get(), turbo_hz=hz, cancel_opposite=self.cancel.get(),
                         buttons=[rev.get(v.get(), "NONE") for v in self.actions])
        cfg.validate()
        return cfg

    # --- 操作 ---
    def on_target_changed(self):
        # 新しい機種で使えない動作は「なし」にする
        old = {}
        for labels in u2j.ACTION_LABELS.values():
            old.update({v: k for k, v in labels.items()})
        acts = [old.get(v.get(), "NONE") for v in self.actions]
        self.refresh_choices()
        labels = self.labels()
        for var, act in zip(self.actions, acts):
            var.set(labels.get(act, labels["NONE"]))
        self.status.set(f"接続先を {TARGET_NAMES[self.target.get()]} にしました (使えない割り当ては「なし」)")

    def on_default(self):
        self.set_config(u2j.Config.default(self.target.get()))
        self.status.set("既定値に戻しました")

    def on_open(self):
        path = filedialog.askopenfilename(filetypes=[("設定ファイル", "*.json *.uf2 *.bin"), ("すべて", "*")])
        if not path:
            return
        try:
            self.set_config(u2j.load_file(path))
            self.status.set(f"読み込みました: {path}")
        except (OSError, ValueError, KeyError) as e:
            messagebox.showerror("読み込みエラー", str(e))

    def _save(self, ext, data_fn, title):
        try:
            cfg = self.get_config()
        except ValueError as e:
            messagebox.showerror("設定エラー", str(e))
            return
        name = "usb2mdjoy_config" if cfg.target == "MD" else "usb2msxjoy_config"
        path = filedialog.asksaveasfilename(defaultextension=ext, initialfile=name + ext,
                                            filetypes=[(title, "*" + ext)])
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(data_fn(cfg))
            self.status.set(f"保存しました: {path}")
        except OSError as e:
            messagebox.showerror("保存エラー", str(e))

    def on_save_json(self):
        self._save(".json", lambda c: c.to_json().encode("utf-8"), "JSON")

    def on_save_uf2(self):
        self._save(".uf2", lambda c: c.to_uf2(), "UF2")

    def on_write_pico(self):
        try:
            cfg = self.get_config()
        except ValueError as e:
            messagebox.showerror("設定エラー", str(e))
            return
        drive = u2j.find_rpi_rp2_drive()
        if not drive:
            messagebox.showwarning(
                "Pico が見つかりません",
                "BOOTSEL ボタンを押しながら Pico を PC につなぎ、RPI-RP2 ドライブが現れてから\n"
                "もう一度押してください。\n\n見つからない場合は「UF2 書き出し」で保存したファイルを\n"
                "RPI-RP2 ドライブに手動でコピーしてください。")
            return
        try:
            with open(os.path.join(drive, "config.uf2"), "wb") as f:
                f.write(cfg.to_uf2())
            self.status.set(f"{drive} に書き込みました。Pico は自動で再起動します")
        except OSError as e:
            messagebox.showerror("書き込みエラー", str(e))

    def on_read_pico(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "cfg.bin")
            start = u2j.CFG_ADDR
            cmd = ["picotool", "save", "-r", hex(start), hex(start + u2j.CFG_BLOCK_SIZE), out]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if r.returncode != 0:
                    raise RuntimeError(r.stderr.strip() or r.stdout.strip())
                self.set_config(u2j.load_file(out))
                self.status.set("Pico から読み込みました")
            except ValueError as e:
                messagebox.showinfo("Pico から読み込み", f"Pico に有効な設定がありません (既定値で動作中)。\n\n{e}")
            except (OSError, RuntimeError, subprocess.SubprocessError) as e:
                messagebox.showerror("Pico から読み込み",
                                     f"読み込めませんでした。Pico を BOOTSEL モードでつないでください。\n\n{e}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
