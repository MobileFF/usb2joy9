"""usb2msxjoy / usb2mdjoy の設定ブロックと UF2 の読み書き。

形式はファームウェアの src/config.h と同じ (変えるときは両方直すこと)。
コマンドラインからも使える:
    python3 u2jconfig.py settings.json -o config.uf2
"""

import json
import os
import struct
import sys
import zlib
from dataclasses import dataclass, field

CFG_MAGIC = 0x434A3255  # 'U2JC'
CFG_VERSION = 1
CFG_BLOCK_SIZE = 256
NUM_BUTTONS = 16

FLASH_BASE = 0x10000000
FLASH_SIZE = 2 * 1024 * 1024  # Pico / RP2040-Zero
CFG_ADDR = FLASH_BASE + FLASH_SIZE - 4096

FLAG_CANCEL_OPPOSITE = 0x01

TARGETS = {"MSX": 0, "MD": 1}

# 動作コード (src/config.h の cfg_action_t と同じ順)
ACTIONS = ["NONE", "A", "B", "TURBO_A", "TURBO_B", "UP_DOWN", "LEFT_RIGHT",
           "C", "START", "TURBO_C", "UP", "DOWN", "LEFT", "RIGHT"]

# 機種ごとに選べる動作と表示名
ACTION_LABELS = {
    "MSX": {
        "NONE": "なし", "A": "トリガA", "B": "トリガB",
        "TURBO_A": "連射A", "TURBO_B": "連射B",
        "UP_DOWN": "上下同時押し", "LEFT_RIGHT": "左右同時押し",
        "UP": "上", "DOWN": "下", "LEFT": "左", "RIGHT": "右",
    },
    "MD": {
        "NONE": "なし", "A": "A", "B": "B", "C": "C", "START": "スタート",
        "TURBO_A": "連射A", "TURBO_B": "連射B", "TURBO_C": "連射C",
        "UP_DOWN": "上下同時押し", "LEFT_RIGHT": "左右同時押し",
        "UP": "上", "DOWN": "下", "LEFT": "左", "RIGHT": "右",
    },
}

UF2_MAGIC0 = 0x0A324655
UF2_MAGIC1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
UF2_FLAG_FAMILY = 0x00002000
RP2040_FAMILY = 0xE48BFF56


@dataclass
class Config:
    target: str = "MSX"
    turbo_hz: int = 15
    cancel_opposite: bool = True
    buttons: list = field(default_factory=lambda: ["NONE"] * NUM_BUTTONS)

    @classmethod
    def default(cls, target):
        """ファームウェアの config_default() と同じ既定値。"""
        c = cls(target=target)
        c.buttons[0] = "A"
        c.buttons[1] = "B"
        if target == "MD":
            c.buttons[2] = "C"
            c.buttons[9] = "START"
        else:
            c.buttons[2] = "TURBO_A"
            c.buttons[3] = "TURBO_B"
        return c

    def validate(self):
        if self.target not in TARGETS:
            raise ValueError(f"target は MSX か MD: {self.target}")
        if not 1 <= self.turbo_hz <= 30:
            raise ValueError("連射速度は 1〜30 Hz")
        if len(self.buttons) != NUM_BUTTONS:
            raise ValueError(f"ボタンは {NUM_BUTTONS} 個")
        for b in self.buttons:
            if b not in ACTION_LABELS[self.target]:
                raise ValueError(f"{self.target} では使えない動作: {b}")

    # --- バイナリ ---
    def to_block(self):
        self.validate()
        flags = FLAG_CANCEL_OPPOSITE if self.cancel_opposite else 0
        body = struct.pack("<IBBBB", CFG_MAGIC, CFG_VERSION, TARGETS[self.target],
                           self.turbo_hz, flags)
        body += bytes(ACTIONS.index(b) for b in self.buttons)
        body += bytes(CFG_BLOCK_SIZE - 4 - len(body))
        return body + struct.pack("<I", zlib.crc32(body))

    @classmethod
    def from_block(cls, block):
        if len(block) < CFG_BLOCK_SIZE:
            raise ValueError("設定ブロックが短すぎます")
        block = block[:CFG_BLOCK_SIZE]
        magic, ver, target, hz, flags = struct.unpack_from("<IBBBB", block)
        if magic != CFG_MAGIC:
            raise ValueError("設定ブロックではありません (magic 不一致)")
        if ver != CFG_VERSION:
            raise ValueError(f"未対応のバージョン: {ver}")
        if struct.unpack_from("<I", block, CFG_BLOCK_SIZE - 4)[0] != zlib.crc32(block[:-4]):
            raise ValueError("CRC が一致しません")
        names = {v: k for k, v in TARGETS.items()}
        if target not in names:
            raise ValueError(f"不明な機種: {target}")
        c = cls(target=names[target], turbo_hz=hz,
                cancel_opposite=bool(flags & FLAG_CANCEL_OPPOSITE))
        c.buttons = [ACTIONS[a] if a < len(ACTIONS) else "NONE" for a in block[8:8 + NUM_BUTTONS]]
        c.buttons = [b if b in ACTION_LABELS[c.target] else "NONE" for b in c.buttons]
        return c

    # --- UF2 ---
    def to_uf2(self):
        data = self.to_block().ljust(476, b"\0")
        return (struct.pack("<8I", UF2_MAGIC0, UF2_MAGIC1, UF2_FLAG_FAMILY, CFG_ADDR,
                            CFG_BLOCK_SIZE, 0, 1, RP2040_FAMILY)
                + data + struct.pack("<I", UF2_MAGIC_END))

    @classmethod
    def from_uf2(cls, raw):
        for off in range(0, len(raw) - 511, 512):
            m0, m1, _flags, addr, size = struct.unpack_from("<5I", raw, off)
            if m0 == UF2_MAGIC0 and m1 == UF2_MAGIC1 and addr == CFG_ADDR:
                return cls.from_block(raw[off + 32:off + 32 + size])
        raise ValueError("この UF2 には設定ブロックが含まれていません")

    # --- JSON ---
    def to_json(self):
        self.validate()
        return json.dumps({"target": self.target, "turbo_hz": self.turbo_hz,
                           "cancel_opposite": self.cancel_opposite,
                           "buttons": self.buttons}, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        c = cls(target=d["target"], turbo_hz=int(d.get("turbo_hz", 15)),
                cancel_opposite=bool(d.get("cancel_opposite", True)),
                buttons=list(d["buttons"]))
        c.validate()
        return c


def load_file(path):
    """.json / .uf2 / .bin (256バイトのブロック) を読み込む。"""
    with open(path, "rb") as f:
        raw = f.read()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return Config.from_json(raw.decode("utf-8"))
    if ext == ".uf2":
        return Config.from_uf2(raw)
    return Config.from_block(raw)


def find_rpi_rp2_drive():
    """BOOTSEL モードの Pico のドライブ (RPI-RP2) を探す。なければ None。"""
    candidates = []
    if sys.platform.startswith("win"):
        candidates = [f"{d}:\\" for d in "DEFGHIJKLMNOPQRSTUVWXYZ"]
    elif sys.platform == "darwin":
        candidates = ["/Volumes/RPI-RP2"]
    else:
        user = os.environ.get("USER", "")
        candidates = [f"/media/{user}/RPI-RP2", f"/run/media/{user}/RPI-RP2", "/media/RPI-RP2"]
    for d in candidates:
        info = os.path.join(d, "INFO_UF2.TXT")
        try:
            with open(info, encoding="ascii", errors="ignore") as f:
                if "RPI-RP2" in f.read():
                    return d
        except OSError:
            pass
    return None


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="設定ファイル (.json/.uf2/.bin) を UF2 または JSON に変換")
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True, help=".uf2 / .json / .bin")
    a = ap.parse_args(argv)
    cfg = load_file(a.input)
    ext = os.path.splitext(a.output)[1].lower()
    if ext == ".json":
        out = cfg.to_json().encode("utf-8")
    elif ext == ".uf2":
        out = cfg.to_uf2()
    else:
        out = cfg.to_block()
    with open(a.output, "wb") as f:
        f.write(out)


if __name__ == "__main__":
    main(sys.argv[1:])
