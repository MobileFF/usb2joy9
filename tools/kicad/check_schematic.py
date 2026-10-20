"""生成した .kicad_sch を読み直して接続を検証し、ネットリストを表示する。

    python3 check_schematic.py <file.kicad_sch> [--png out.png]

KiCad がない環境で、座標の誤りによる「つながっていないピン」「余った配線」などを見つけるためのもの。
ERC の代わりではないので、最終確認は KiCad の ERC で行うこと。
"""

import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sexpr as sx  # noqa: E402


def key(x, y):
    return (round(float(x), 2), round(float(y), 2))


def rot_pt(px, py, rot):
    """ライブラリ座標 (Y 上向き) を回転して回路図座標の差分 (Y 下向き) に。"""
    a = math.radians(rot)
    rx = px * math.cos(a) - py * math.sin(a)
    ry = px * math.sin(a) + py * math.cos(a)
    return rx, -ry


class Schematic:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self.root = sx.parse(f.read())
        self.lib = {}
        for s in sx.find(sx.find1(self.root, "lib_symbols"), "symbol"):
            pins = {}
            graphics = []
            for sub in sx.find(s, "symbol"):
                for p in sx.find(sub, "pin"):
                    at = sx.find1(p, "at")
                    ln = sx.find1(p, "length")
                    pins[sx.find1(p, "number")[1]] = (sx.find1(p, "name")[1], p[1], float(at[1]),
                                                      float(at[2]), float(at[3]), float(ln[1]))
                for g in sub:
                    if isinstance(g, list) and g and g[0] in ("rectangle", "polyline", "circle", "arc"):
                        graphics.append(g)
            self.lib[s[1]] = {"pins": pins, "graphics": graphics, "power": sx.find1(s, "power") is not None}
        self.symbols = []
        for s in sx.find(self.root, "symbol"):
            at = sx.find1(s, "at")
            props = {p[1]: p for p in sx.find(s, "property")}
            self.symbols.append({"lib_id": sx.find1(s, "lib_id")[1], "x": float(at[1]), "y": float(at[2]),
                                 "rot": float(at[3]), "ref": props["Reference"][2],
                                 "value": props["Value"][2], "props": props,
                                 "footprint": props["Footprint"][2]})
        self.wires = [((float(w[1][1][1]), float(w[1][1][2])), (float(w[1][2][1]), float(w[1][2][2])))
                      for w in sx.find(self.root, "wire")]
        self.labels = [(l[1], float(sx.find1(l, "at")[1]), float(sx.find1(l, "at")[2]),
                        float(sx.find1(l, "at")[3])) for l in sx.find(self.root, "label")]
        self.ncs = [key(*sx.find1(n, "at")[1:3]) for n in sx.find(self.root, "no_connect")]
        self.texts = [(t[1], float(sx.find1(t, "at")[1]), float(sx.find1(t, "at")[2]))
                      for t in sx.find(self.root, "text")]

    def pins(self):
        """(ref, 番号, 名前, 種類, 接続点, 本体側の点, 電源ネット名)"""
        out = []
        for s in self.symbols:
            lib = self.lib[s["lib_id"]]
            for n, (name, typ, px, py, ang, ln) in lib["pins"].items():
                dx, dy = rot_pt(px, py, s["rot"])
                x, y = s["x"] + dx, s["y"] + dy
                bx, by = rot_pt(px + ln * math.cos(math.radians(ang)), py + ln * math.sin(math.radians(ang)),
                                s["rot"])
                net = s["value"] if lib["power"] else None
                out.append((s["ref"], n, name, typ, key(x, y), (s["x"] + bx, s["y"] + by), net))
        return out

    def check(self):
        errors = []
        parent = {}

        def find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            parent[find(a)] = find(b)

        pins = self.pins()
        at_point = defaultdict(list)
        for p in pins:
            at_point[p[4]].append(("pin", p))
        for w in self.wires:
            a, b = key(*w[0]), key(*w[1])
            union(("pt", a), ("pt", b))
            at_point[a].append(("wire", w))
            at_point[b].append(("wire", w))
        for name, x, y, _ in self.labels:
            at_point[key(x, y)].append(("label", name))
            union(("pt", key(x, y)), ("net", name))
        for p in pins:
            union(("pt", p[4]), ("pin", p[0], p[1]))
            if p[6]:
                union(("pt", p[4]), ("net", p[6]))
        # 同じ部品の同じ名前の電源ピン (Pico の GND など) は内部で接続
        groups = defaultdict(list)
        for p in pins:
            if p[2] == "GND":
                groups[p[0]].append(p)
        for g in groups.values():
            for p in g[1:]:
                union(("pin", g[0][0], g[0][1]), ("pin", p[0], p[1]))

        # 配線の端がどこにもつながっていない
        for pt, items in at_point.items():
            kinds = [k for k, _ in items]
            if "wire" in kinds and len(items) < 2:
                errors.append(f"配線の端が浮いている: {pt}")
        # 配線の途中に接している点 (KiCad ではつながらない) の検出
        for w in self.wires:
            (x1, y1), (x2, y2) = w
            for pt in at_point:
                if pt in (key(x1, y1), key(x2, y2)):
                    continue
                if min(x1, x2) - 1e-6 <= pt[0] <= max(x1, x2) + 1e-6 and \
                        min(y1, y2) - 1e-6 <= pt[1] <= max(y1, y2) + 1e-6:
                    errors.append(f"配線 {w} の途中に接続点 {pt} がある")
        nc = set(self.ncs)
        for pt in nc:
            kinds = [k for k, _ in at_point.get(pt, [])]
            if kinds.count("pin") != 1 or "wire" in kinds or "label" in kinds:
                errors.append(f"未接続マークの位置がおかしい: {pt} {kinds}")
        label_count = defaultdict(int)
        for name, *_ in self.labels:
            label_count[name] += 1
        for name, c in label_count.items():
            if c < 2:
                errors.append(f"ラベル {name} が 1 か所にしかない")

        nets = defaultdict(list)
        for p in pins:
            nets[find(("pin", p[0], p[1]))].append(p)
        names = {}
        for node in list(parent):
            if node[0] == "net":
                names.setdefault(find(node), set()).add(node[1])
        result = {}
        for rootk, ps in nets.items():
            real = [p for p in ps if not self.lib[self._lib_of(p[0])]["power"]]
            label = "/".join(sorted(names.get(rootk, []))) or "(無名)"
            if not real:
                continue
            if len(real) == 1:
                p = real[0]
                if p[4] not in nc and p[3] != "no_connect" and not names.get(rootk):
                    errors.append(f"未接続のピン: {p[0]}.{p[1]} ({p[2]})")
                elif names.get(rootk) and p[4] not in nc:
                    errors.append(f"ネット {label} に部品ピンが 1 つだけ: {p[0]}.{p[1]} ({p[2]})")
                continue
            result[label] = sorted(f"{p[0]}.{p[1]}({p[2]})" for p in real)
        return result, errors

    def _lib_of(self, ref):
        for s in self.symbols:
            if s["ref"] == ref:
                return s["lib_id"]
        raise KeyError(ref)

    def render(self, out, scale=8):
        from PIL import Image, ImageDraw, ImageFont
        W, H = int(297 * scale), int(210 * scale)
        img = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(img)
        font = None
        for fp in ("/usr/share/fonts/chromeos/notocjk/NotoSansCJK-Regular.ttc",
                   "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                   "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                   "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if os.path.exists(fp):
                font = ImageFont.truetype(fp, int(1.5 * scale))
                break
        font = font or ImageFont.load_default()

        def P(x, y):
            return (x * scale, y * scale)

        def tw(s):
            return d.textlength(s, font=font)

        for s in self.symbols:
            lib = self.lib[s["lib_id"]]
            for g in lib["graphics"]:
                if g[0] == "rectangle":
                    a = rot_pt(float(sx.find1(g, "start")[1]), float(sx.find1(g, "start")[2]), s["rot"])
                    b = rot_pt(float(sx.find1(g, "end")[1]), float(sx.find1(g, "end")[2]), s["rot"])
                    x0, x1 = sorted((s["x"] + a[0], s["x"] + b[0]))
                    y0, y1 = sorted((s["y"] + a[1], s["y"] + b[1]))
                    d.rectangle([P(x0, y0), P(x1, y1)], outline="darkred", width=2)
                elif g[0] == "polyline":
                    pts = [rot_pt(float(q[1]), float(q[2]), s["rot"]) for q in sx.find(sx.find1(g, "pts"), "xy")]
                    d.line([P(s["x"] + q[0], s["y"] + q[1]) for q in pts], fill="darkred", width=2)
                elif g[0] == "circle":
                    c = rot_pt(float(sx.find1(g, "center")[1]), float(sx.find1(g, "center")[2]), s["rot"])
                    r = float(sx.find1(g, "radius")[1])
                    cx, cy = s["x"] + c[0], s["y"] + c[1]
                    d.ellipse([P(cx - r, cy - r), P(cx + r, cy + r)], outline="darkred", width=1)
            # 表示されるプロパティ
            for pname in ("Reference", "Value"):
                pr = s["props"][pname]
                eff = sx.find1(pr, "effects")
                if eff and sx.find1(eff, "hide"):
                    continue
                at = sx.find1(pr, "at")
                txt = pr[2]
                x, y = float(at[1]), float(at[2])
                just = sx.find1(eff, "justify") if eff else None
                j = [str(v) for v in just[1:]] if just else []
                tx = x * scale - (0 if "left" in j else tw(txt) if "right" in j else tw(txt) / 2)
                d.text((tx, y * scale - 0.8 * scale), txt, fill="teal", font=font)
        for p in self.pins():
            d.line([P(*p[4]), P(*p[5])], fill="darkred", width=2)
            lib_power = self.lib[self._lib_of(p[0])]["power"]
            if not lib_power and p[2] not in ("~", "PAD") and not p[2].isdigit():
                pass
        for (a, b) in self.wires:
            d.line([P(*a), P(*b)], fill="green", width=2)
        for name, x, y, ang in self.labels:
            w = tw(name)
            if ang == 180:
                d.text((x * scale - w, y * scale - 1.9 * scale), name, fill="black", font=font)
            elif ang == 0:
                d.text((x * scale, y * scale - 1.9 * scale), name, fill="black", font=font)
            else:
                d.text((x * scale + 2, y * scale), name, fill="black", font=font)
        for (x, y) in self.ncs:
            r = 0.8
            d.line([P(x - r, y - r), P(x + r, y + r)], fill="blue", width=2)
            d.line([P(x - r, y + r), P(x + r, y - r)], fill="blue", width=2)
        for t, x, y in self.texts:
            d.text((x * scale, y * scale - 1.9 * scale), t, fill="black", font=font)
        d.rectangle([P(10, 10), P(287, 200)], outline="gray")
        img.save(out)


def main(argv):
    path = argv[0]
    sch = Schematic(path)
    nets, errors = sch.check()
    print(f"== {os.path.basename(path)}")
    for s in sorted(sch.symbols, key=lambda s: s["ref"]):
        if not s["ref"].startswith("#"):
            print(f"  {s['ref']:4} {s['value']:28} {s['footprint']}")
    print("-- nets")
    for name in sorted(nets):
        print(f"  {name:12} {' '.join(nets[name])}")
    print("-- errors" if errors else "-- no errors")
    for e in errors:
        print("  " + e)
    if "--png" in argv:
        sch.render(argv[argv.index("--png") + 1])
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
