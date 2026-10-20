"""usb2msxjoy / usb2mdjoy の KiCad 9 回路図を生成する。

    python3 gen_schematics.py <KiCad の symbols ディレクトリ> [出力先 (既定: ../../kicad)]

symbols ディレクトリの例:
    Linux   : /usr/share/kicad/symbols
    Windows : C:\\Program Files\\KiCad\\9.0\\share\\kicad\\symbols
    macOS   : /Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols

部品記号は KiCad 9 標準ライブラリから回路図の中にコピーする (lib_symbols)。
配線は「ピン → 短い配線 → ネットラベル / 電源シンボル」で表し、ネット名で接続する。
"""

import datetime
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sexpr as sx  # noqa: E402
from sexpr import Sym  # noqa: E402

GRID = 2.54
STUB = 2 * GRID  # ピンから引き出す配線の長さ

FP_PICO = "Module:RaspberryPi_Pico_Common_THT"
FP_DSUB = ("Connector_Dsub:DSUB-9_Socket_Horizontal_P2.77x2.84mm_EdgePinOffset7.70mm"
           "_Housed_MountingHolesOffset9.12mm")
FP_HDR3 = "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"
FP_C = "Capacitor_SMD:C_0805_2012Metric"
FP_R = "Resistor_SMD:R_0805_2012Metric"

LIB_SYMBOLS = [
    ("MCU_Module", "RaspberryPi_Pico"),
    ("Logic_LevelTranslator", "FXMA108"),
    ("Connector", "DE9_Socket_MountingHoles"),
    ("Connector_Generic", "Conn_01x03"),
    ("Device", "R"),
    ("Device", "C"),
    ("power", "+5V"),
    ("power", "+3V3"),
    ("power", "GND"),
]

# ネット割り当て: (Pico GPIO, FXMA A側, FXMA B側, D-sub ピン, Pico側ネット名)
DESIGNS = {
    "usb2msxjoy": {
        "title": "usb2msxjoy - USB joystick to MSX (FXMA108)",
        "firmware": "firmware/MSX/usb2msxjoy_pico_fxma108.uf2",
        "signals": [
            ("GPIO2", "A0", "B0", "1", "UP"),
            ("GPIO3", "A1", "B1", "2", "DOWN"),
            ("GPIO4", "A2", "B2", "3", "LEFT"),
            ("GPIO5", "A3", "B3", "4", "RIGHT"),
            ("GPIO6", "A4", "B4", "6", "TRG_A"),
            ("GPIO7", "A5", "B5", "7", "TRG_B"),
        ],
        "dsub_power": {"5": "+5V", "9": "GND"},
        "dsub_nc": ["8", "0"],
        "notes": [
            "MSX ジョイスティックポート用 (動作確認済み構成)",
            "J1: D-sub 9ピン メス (MSX 本体側はオス)。8番 (ストローブ) は未使用",
        ],
    },
    "usb2mdjoy": {
        "title": "usb2mdjoy - USB joystick to Mega Drive 3-button (FXMA108)",
        "firmware": "firmware/MD/usb2mdjoy_pico_fxma108.uf2",
        "signals": [
            ("GPIO2", "A0", "B0", "1", "UP"),
            ("GPIO3", "A1", "B1", "2", "DOWN"),
            ("GPIO4", "A2", "B2", "3", "LEFT"),
            ("GPIO5", "A3", "B3", "4", "RIGHT"),
            ("GPIO6", "A4", "B4", "6", "TL"),
            ("GPIO7", "A5", "B5", "9", "TR"),
            ("GPIO9", "A6", "B6", "7", "TH"),
        ],
        "dsub_power": {"5": "+5V", "8": "GND"},
        "dsub_nc": ["0"],
        "notes": [
            "メガドライブ 3ボタンパッド互換 (実機未確認)",
            "J1: D-sub 9ピン メス。7番 TH は本体からの入力 (FXMA108 が向きを自動判別)",
            "GND は 8番 (MSX 版とは配線が違う)",
        ],
    },
}

COMMON_NOTES = [
    "電源: J1 5番 (+5V) を Pico の VBUS (40番) に入れる。VSYS (39番) に入れると USB 側に 5V が出ずパッドが動かない",
    "U2 FXMA108: /OE は L で有効 (GP8 が L を出力)。R1 は電源投入中に無効にしておくためのプルアップ",
    "秋月 AE-LLCNV8-DIP20 モジュールを使う場合、C1・C2・R1 はモジュールに載っているので不要",
    "FXMA108 はバスホールド付き。A/B 側の信号線にプルアップ/プルダウン抵抗を付けないこと",
    "J2: デバッグ用 UART (115200bps)。USB パッドは Pico の micro-USB に OTG アダプタで接続",
]


def uid():
    return str(uuid.uuid4())


def num(v):
    return float(v)


def effects(justify=None, hide=False, size=1.27):
    e = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    if hide:
        e.append([Sym("hide"), Sym("yes")])
    return e


def load_libs(symdir):
    out = {}
    cache = {}
    for lib, name in LIB_SYMBOLS:
        if lib not in cache:
            path = os.path.join(symdir, lib + ".kicad_sym")
            with open(path, encoding="utf-8") as f:
                cache[lib] = sx.parse(f.read())
        for s in sx.find(cache[lib], "symbol"):
            if s[1] == name:
                break
        else:
            raise SystemExit(f"{lib}:{name} が見つかりません")
        if sx.find1(s, "extends"):
            raise SystemExit(f"{lib}:{name} は extends を使っています (未対応)")
        out[f"{lib}:{name}"] = s
    return out


class LibSym:
    """ライブラリの記号定義 (ピン位置と既定プロパティ)。"""

    def __init__(self, lib_id, node):
        self.lib_id = lib_id
        self.node = node
        self.pins = {}  # number -> (name, x, y, angle)
        for sub in sx.find(node, "symbol"):
            for p in sx.find(sub, "pin"):
                at = sx.find1(p, "at")
                number = sx.find1(p, "number")[1]
                name = sx.find1(p, "name")[1]
                self.pins[number] = (name, num(at[1]), num(at[2]), int(num(at[3])))
        self.props = {p[1]: p[2] for p in sx.find(node, "property")}
        self.is_power = sx.find1(node, "power") is not None

    def pin_by_name(self, name):
        hits = [n for n, p in self.pins.items() if p[0] == name]
        if len(hits) != 1:
            raise KeyError(f"{self.lib_id}: ピン名 {name} が {len(hits)} 個")
        return hits[0]

    def cached(self):
        """回路図の lib_symbols に入れる形 (名前を Lib:Name に)。"""
        node = list(self.node)
        node[1] = self.lib_id
        return node


class Sheet:
    def __init__(self, project, libs):
        self.project = project
        self.libs = {k: LibSym(k, v) for k, v in libs.items()}
        self.root_uuid = uid()
        self.items = []
        self.pwr_count = 0
        self.points = []  # 検証用: (x, y, 種類, 内容)

    # --- 部品 ---
    def symbol(self, lib_id, ref, x, y, value=None, footprint=None, rot=0, props_at=None):
        ls = self.libs[lib_id]
        node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), x, y, rot], [Sym("unit"), 1],
                [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("no" if ls.is_power else "yes")],
                [Sym("on_board"), Sym("no" if ls.is_power else "yes")], [Sym("dnp"), Sym("no")],
                [Sym("uuid"), uid()]]
        val = value if value is not None else ls.props.get("Value", "")
        fp = footprint if footprint is not None else ls.props.get("Footprint", "")
        pa = props_at or {}
        ref_at = pa.get("Reference", (x, y - 3.81, 0))
        val_at = pa.get("Value", (x, y + 3.81, 0))
        fields = [
            ("Reference", ref, ref_at, ls.is_power, pa.get("ref_justify")),
            ("Value", val, val_at, False, pa.get("val_justify")),
            ("Footprint", fp, (x, y, 0), True, None),
            ("Datasheet", ls.props.get("Datasheet", ""), (x, y, 0), True, None),
            ("Description", ls.props.get("Description", ""), (x, y, 0), True, None),
        ]
        for name, text, at, hide, just in fields:
            node.append([Sym("property"), name, text, [Sym("at"), at[0], at[1], at[2]],
                         effects(justify=just, hide=hide)])
        for n in sorted(ls.pins, key=lambda s: (len(s), s)):
            node.append([Sym("pin"), n, [Sym("uuid"), uid()]])
        node.append([Sym("instances"), [Sym("project"), self.project,
                                        [Sym("path"), "/" + self.root_uuid,
                                         [Sym("reference"), ref], [Sym("unit"), 1]]]])
        self.items.append(node)
        return Placed(self, ls, ref, x, y, rot)

    def power(self, net, x, y, rot=0):
        """電源シンボル。rot: 0=上向き(+5V等)/下向き(GND), 90/270 で横向き。"""
        self.pwr_count += 1
        ref = f"#PWR{self.pwr_count:02d}"
        lib_id = "power:" + net
        # 値の文字はシンボルの向いた側に置く
        d = {0: (0, -1), 90: (-1, 0), 180: (0, 1), 270: (1, 0)}[rot]
        if net == "GND":
            d = (-d[0], -d[1])
        dist = 3.81 if net == "GND" else 3.556
        vx, vy = x + d[0] * dist, y + d[1] * dist
        just = None
        if d[0] < 0:
            just = "right"
        elif d[0] > 0:
            just = "left"
        if d[0] != 0:
            vx = x + d[0] * 3.2
        self.symbol(lib_id, ref, x, y, rot=rot,
                    props_at={"Value": (vx, vy, 0), "Reference": (x, y, 0), "val_justify": just})
        self.points.append((x, y, "power", net))

    def wire(self, x1, y1, x2, y2):
        self.items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), x1, y1], [Sym("xy"), x2, y2]],
                           [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                           [Sym("uuid"), uid()]])
        self.points.append(((x1, y1), (x2, y2), "wire", None))

    def label(self, name, x, y, side):
        """side: ラベルの文字が伸びる向き (left / right / up / down)。"""
        angle, just = {"right": (0, "left bottom"), "left": (180, "right bottom"),
                       "up": (90, "left bottom"), "down": (270, "right bottom")}[side]
        self.items.append([Sym("label"), name, [Sym("at"), x, y, angle],
                           effects(justify=just), [Sym("uuid"), uid()]])
        self.points.append((x, y, "label", name))

    def no_connect(self, x, y):
        self.items.append([Sym("no_connect"), [Sym("at"), x, y], [Sym("uuid"), uid()]])
        self.points.append((x, y, "nc", None))

    def text(self, s, x, y, size=1.27):
        self.items.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")],
                           [Sym("at"), x, y, 0], effects(justify="left bottom", size=size),
                           [Sym("uuid"), uid()]])

    # --- 出力 ---
    def dump(self, title, comments):
        today = datetime.date.today().isoformat()
        tb = [Sym("title_block"), [Sym("title"), title], [Sym("date"), today], [Sym("rev"), "1"]]
        for i, c in enumerate(comments, 1):
            tb.append([Sym("comment"), i, c])
        used = sorted({it[1][1] for it in self.items if it[0] == "symbol"})
        root = [Sym("kicad_sch"), [Sym("version"), Sym("20250114")], [Sym("generator"), "eeschema"],
                [Sym("generator_version"), "9.0"], [Sym("uuid"), self.root_uuid], [Sym("paper"), "A4"],
                tb, [Sym("lib_symbols")] + [self.libs[u].cached() for u in used]]
        root += self.items
        root.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
        root.append([Sym("embedded_fonts"), Sym("no")])
        return sx.dump(root) + "\n"


class Placed:
    def __init__(self, sheet, ls, ref, x, y, rot):
        self.sheet, self.ls, self.ref, self.x, self.y, self.rot = sheet, ls, ref, x, y, rot

    def pin_end(self, pin):
        """ピン番号またはピン名 → (回路図上の接続点, 外向きの向き)。"""
        if self.rot != 0:
            raise ValueError("ピンを使う部品は回転なしで置く")
        n = pin if pin in self.ls.pins else self.ls.pin_by_name(pin)
        _name, px, py, ang = self.ls.pins[n]
        out = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[ang]
        x, y = round(self.x + px, 4), round(self.y - py, 4)
        self.sheet.points.append((x, y, "pin", f"{self.ref}.{n}"))
        return x, y, out

    def stub(self, pin, length=STUB):
        x, y, (dx, dy) = self.pin_end(pin)
        ex, ey = round(x + dx * length, 4), round(y + dy * length, 4)
        self.sheet.wire(x, y, ex, ey)
        return ex, ey, (dx, dy)

    def to_label(self, pin, net, length=STUB, side=None):
        ex, ey, (dx, dy) = self.stub(pin, length)
        side = side or {(-1, 0): "left", (1, 0): "right", (0, -1): "up", (0, 1): "down"}[(dx, dy)]
        self.sheet.label(net, ex, ey, side)

    def to_power(self, pin, net, length=STUB):
        ex, ey, (dx, dy) = self.stub(pin, length)
        # 電源記号を配線の延長方向に向ける
        if net == "GND":
            rot = {(0, 1): 0, (-1, 0): 270, (1, 0): 90, (0, -1): 180}[(dx, dy)]
        else:
            rot = {(0, -1): 0, (-1, 0): 90, (1, 0): 270, (0, 1): 180}[(dx, dy)]
        self.sheet.power(net, ex, ey, rot)

    def nc(self, pin):
        x, y, _ = self.pin_end(pin)
        self.sheet.no_connect(x, y)


def build(project, design, libs):
    sh = Sheet(project, libs)

    # U1: Raspberry Pi Pico
    u1 = sh.symbol("MCU_Module:RaspberryPi_Pico", "U1", 63.5, 88.9, footprint=FP_PICO,
                   props_at={"Reference": (76.2, 46.99, 0), "Value": (76.2, 49.53, 0),
                             "ref_justify": "left", "val_justify": "left"})
    # U2: FXMA108
    u2 = sh.symbol("Logic_LevelTranslator:FXMA108", "U2", 139.7, 86.36,
                   props_at={"Reference": (148.59, 64.77, 0), "Value": (148.59, 109.22, 0),
                             "ref_justify": "left", "val_justify": "left"})
    # J1: D-sub 9 メス
    j1 = sh.symbol("Connector:DE9_Socket_MountingHoles", "J1", 205.74, 86.36, value="DE9_Socket",
                   footprint=FP_DSUB,
                   props_at={"Reference": (205.74, 71.12, 0), "Value": (213.36, 86.36, 90)})

    used_gpio = {"GPIO0", "GPIO1", "GPIO8"}
    used_a = {"~{OE}"}
    used_b = set()
    used_j = set()
    for gpio, a, b, jp, net in design["signals"]:
        u1.to_label(gpio, net)
        u2.to_label(a, net)
        u2.to_label(b, net + "_5V")
        j1.to_label(jp, net + "_5V")
        used_gpio.add(gpio)
        used_a.add(a)
        used_b.add(b)
        used_j.add(jp)

    # Pico の電源とその他
    u1.to_power("VBUS", "+5V")
    u1.to_power("3V3", "+3V3")
    u1.nc("VSYS")
    u1.to_power("3", "GND")  # GND ピンは記号上で重なっている
    u1.to_label("GPIO8", "OE_N")
    u1.to_label("GPIO0", "UART_TX")
    u1.to_label("GPIO1", "UART_RX")
    for n, (name, *_r) in u1.ls.pins.items():
        if name.startswith("GPIO") and name.split("_")[0] not in used_gpio and name not in used_gpio:
            u1.nc(n)
    for name in ("RUN", "3V3_EN", "ADC_VREF", "AGND"):
        u1.nc(name)

    # FXMA108
    u2.to_label("~{OE}", "OE_N")
    u2.to_power("VCCA", "+3V3", length=2 * STUB)
    u2.to_power("VCCB", "+5V", length=STUB)
    u2.to_power("GND", "GND")
    for i in range(8):
        if f"A{i}" not in used_a:
            u2.nc(f"A{i}")
        if f"B{i}" not in used_b:
            u2.nc(f"B{i}")

    # D-sub
    for jp, net in design["dsub_power"].items():
        j1.to_power(jp, net)
    for jp in design["dsub_nc"]:
        j1.nc(jp)

    # 周辺部品 (U2 の下)
    c1 = sh.symbol("Device:C", "C1", 114.3, 137.16, value="0.1u", footprint=FP_C,
                   props_at={"Reference": (116.84, 135.89, 0), "Value": (116.84, 139.7, 0),
                             "ref_justify": "left", "val_justify": "left"})
    c1.to_power("1", "+3V3")
    c1.to_power("2", "GND")
    c2 = sh.symbol("Device:C", "C2", 132.08, 137.16, value="0.1u", footprint=FP_C,
                   props_at={"Reference": (134.62, 135.89, 0), "Value": (134.62, 139.7, 0),
                             "ref_justify": "left", "val_justify": "left"})
    c2.to_power("1", "+5V")
    c2.to_power("2", "GND")
    r1 = sh.symbol("Device:R", "R1", 152.4, 137.16, value="10k", footprint=FP_R,
                   props_at={"Reference": (154.94, 135.89, 0), "Value": (154.94, 138.43, 0),
                             "ref_justify": "left", "val_justify": "left"})
    r1.to_power("1", "+3V3")
    r1.to_label("2", "OE_N", side="right")
    sh.text("C1: U2 VCCA (1番) の近く / C2: U2 VCCB (20番) の近く", 109.22, 154.94)

    # J2: UART
    j2 = sh.symbol("Connector_Generic:Conn_01x03", "J2", 213.36, 134.62, value="UART", footprint=FP_HDR3,
                   props_at={"Reference": (215.9, 132.08, 0), "Value": (215.9, 137.16, 0),
                             "ref_justify": "left", "val_justify": "left"})
    j2.to_power("1", "GND")
    j2.to_label("2", "UART_TX")
    j2.to_label("3", "UART_RX")
    sh.text("J2: 1=GND 2=TX (GP0) 3=RX (GP1)", 200.66, 144.78)

    # 注記
    y = 160.02
    for line in design["notes"] + COMMON_NOTES:
        sh.text(line, 20.32, y)
        y += 3.81
    sh.text("ファームウェア: " + design["firmware"], 20.32, y)

    comments = ["Raspberry Pi Pico + FXMA108 level translator", "firmware: " + design["firmware"]]
    return sh, sh.dump(design["title"], comments)


def project_file(name):
    return json.dumps({"meta": {"filename": name + ".kicad_pro", "version": 3},
                       "sheets": [], "boards": [], "libraries": {"pinned_symbol_libs": [],
                                                                  "pinned_footprint_libs": []}},
                      indent=2) + "\n"


def main(argv):
    if len(argv) < 1:
        print(__doc__)
        return 1
    symdir = argv[0]
    outdir = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       "..", "..", "kicad")
    libs = load_libs(symdir)
    for name, design in DESIGNS.items():
        d = os.path.join(outdir, name)
        os.makedirs(d, exist_ok=True)
        _sheet, text = build(name, design, libs)
        with open(os.path.join(d, name + ".kicad_sch"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        pro = os.path.join(d, name + ".kicad_pro")
        if not os.path.exists(pro):  # KiCad が書き足した設定を消さない
            with open(pro, "w", encoding="utf-8", newline="\n") as f:
                f.write(project_file(name))
        print("wrote", os.path.join(d, name + ".kicad_sch"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
