"""KiCad の S 式ファイル用の最小限のパーサ / 書き出し。"""

import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


class Sym(str):
    """クォートしない識別子 (キーワード・数値など)。"""


def parse(text):
    stack = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError(f"parse error at {pos}")
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            lst = stack.pop()
            stack[-1].append(lst)
        elif m.group(3) is not None:
            stack[-1].append(m.group(3).replace('\\"', '"').replace("\\\\", "\\"))
        elif m.group(4) is not None:
            stack[-1].append(Sym(m.group(4)))
    return stack[0][0]


def _atom(x):
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        s = f"{x:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return '"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"'


def dump(node, indent=0):
    if not isinstance(node, list):
        return _atom(node)
    # 子にリストを含まない短い式は 1 行で
    if all(not isinstance(c, list) for c in node):
        return "(" + " ".join(_atom(c) for c in node) + ")"
    pad = "\t" * (indent + 1)
    head = []
    rest = []
    for c in node:
        if not rest and not isinstance(c, list):
            head.append(_atom(c))
        else:
            rest.append(c)
    out = "(" + " ".join(head)
    for c in rest:
        out += "\n" + pad + dump(c, indent + 1)
    return out + "\n" + "\t" * indent + ")"


def find(node, key):
    """直下の子から先頭が key の式をすべて返す。"""
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def find1(node, key):
    r = find(node, key)
    return r[0] if r else None
