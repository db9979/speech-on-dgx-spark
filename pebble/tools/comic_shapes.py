"""Writes src/c/comic_shapes.h: the fixed parts of the comic face as point lists.

The drawing is the same as COMIC in app/panel/static/js/face.js (200 x 200 box); curves are cut
into short lines here, so the watch only fills and outlines polygons. Run it again after the
comic face in the panel changes:  python3 tools/comic_shapes.py
"""
import math
import os
import re

S = dict(top=36, hw=47, cheekY=92, chinW=23, chinY=167, eyeX=21, eyeY=90, noseLen=29, noseW=10, stacheS=1.06)
HAIR = [[-6, 1], [-12.8, 1.31], [-19.7, 1], [-26.5, 1.19], [-33.3, 1], [-40.2, 1.33], [-47, 1], [-53.8, 1.22],
        [-60.7, 1], [-67.5, 1.3], [-74.3, 1], [-81.2, 1.2], [-88, 1], [-94.8, 1.34], [-101.7, 1], [-108.5, 1.21],
        [-115.3, 1], [-122.2, 1.3], [-129, 1], [-135.8, 1.18], [-142.7, 1], [-149.5, 1.32], [-156.3, 1],
        [-163.2, 1.24], [-170, 1]]
STEPS = 5      # line pieces per curve
R_CLIP = 95    # the face sits in a circle


def path(d):
    """Absolute M/L/C/Q/Z path to points (curves cut into STEPS lines)."""
    toks = re.findall(r"[MLCQZ]|-?\d+(?:\.\d+)?", d)
    pts, i, cmd, cur = [], 0, None, (0.0, 0.0)
    while i < len(toks):
        if toks[i] in "MLCQZ":
            cmd = toks[i]
            i += 1
            if cmd == "Z":
                continue
        n = {"M": 2, "L": 2, "C": 6, "Q": 4}[cmd]
        v = [float(x) for x in toks[i:i + n]]
        i += n
        if cmd in "ML":
            cur = (v[0], v[1])
            pts.append(cur)
        elif cmd == "Q":
            p0, p1, p2 = cur, (v[0], v[1]), (v[2], v[3])
            for k in range(1, STEPS + 1):
                t = k / STEPS
                pts.append(tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t * t * c for a, b, c in zip(p0, p1, p2)))
            cur = p2
        else:
            p0, p1, p2, p3 = cur, (v[0], v[1]), (v[2], v[3]), (v[4], v[5])
            for k in range(1, STEPS + 1):
                t = k / STEPS
                pts.append(tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * e
                                 for a, b, c, e in zip(p0, p1, p2, p3)))
            cur = p3
    out = []
    for p in pts:   # drop points that sit on the one before
        if not out or abs(out[-1][0] - p[0]) + abs(out[-1][1] - p[1]) > .8:
            out.append(p)
    return out


def ellipse(cx, cy, rx, ry, n=16):
    return [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]


def clip_circle(poly, n=48):
    """Sutherland-Hodgman against the round frame (a convex polygon)."""
    circ = ellipse(100, 100, R_CLIP, R_CLIP, n)
    out = poly
    for a, b in zip(circ, circ[1:] + circ[:1]):
        inside = lambda p: (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0
        src, out = out, []
        for p, q in zip(src, src[1:] + src[:1]):
            def cut():
                dx, dy, ex, ey = q[0] - p[0], q[1] - p[1], b[0] - a[0], b[1] - a[1]
                t = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / (dx * ey - dy * ex)
                return (p[0] + t * dx, p[1] + t * dy)
            if inside(q):
                if not inside(p):
                    out.append(cut())
                out.append(q)
            elif inside(p):
                out.append(cut())
    return out


def shapes():
    s, r = S, round
    m = s["eyeY"] + s["noseLen"] + 6
    hw, top, cy0, chW, chY = s["hw"], s["top"], s["cheekY"], s["chinW"], s["chinY"]
    face = (f"M100 {top} C{100 + hw * .72} {top} {100 + hw} {top + 22} {100 + hw} {cy0} "
            f"C{100 + hw} {cy0 + 36} {100 + chW + 13} {chY - 15} {100 + chW} {chY - 5} Q100 {chY + 6} {100 - chW} {chY - 5} "
            f"C{100 - chW - 13} {chY - 15} {100 - hw} {cy0 + 36} {100 - hw} {cy0} C{100 - hw} {top + 22} {100 - hw * .72} {top} 100 {top}Z")
    cy, rx = top + 44, hw + 4
    hair = f"M{100 + hw + 2} {cy}"
    for a, k in HAIR:
        hair += f" L{100 + math.cos(math.radians(a)) * rx * k:.2f} {cy + math.sin(math.radians(a)) * 50 * k:.2f}"
    hair += (f" L{100 - hw - 2} {cy} L{100 - hw + 3} {top + 38} Q{100 - hw * .45} {top + 13} 100 {top + 18} "
             f"Q{100 + hw * .45} {top + 13} {100 + hw - 3} {top + 38}Z")
    st = (f"M100 {m} C106.33 {m - 2} 115.2 {m + 2} 119 {m + 4.5} C120.9 {m + 6.7} 120.33 {m + 9} 118.43 {m + 10} "
          f"C116.53 {m + 7.8} 111.4 {m + 11} 105.13 {m + 10} Q100 {m + 8} 94.87 {m + 10} C88.6 {m + 11} 83.47 {m + 7.8} "
          f"81.57 {m + 10} C79.67 {m + 9} 79.1 {m + 6.7} 81 {m + 4.5} C84.8 {m + 2} 93.67 {m - 2} 100 {m}Z")
    stache = [(100 + (x - 100) * s["stacheS"], m + (y - m) * s["stacheS"]) for x, y in path(st)]
    c, ny, nl, nw = chY, s["eyeY"], s["noseLen"], s["noseW"]
    nose = (f"M97 {ny + 4} C97 {ny + nl * .5} {100 - nw * .5} {ny + nl * .75} {100 - nw * .6} {ny + nl - 4} "
            f"C{100 - nw - 1} {ny + nl} {100 - nw + 1} {ny + nl + 5} 96 {ny + nl + 4} Q100 {ny + nl + 6} 104 {ny + nl + 4} "
            f"C{100 + nw - 1} {ny + nl + 5} {100 + nw + 1} {ny + nl} {100 + nw * .6} {ny + nl - 4}")
    return {
        "neck": clip_circle(path(f"M80 {c - 26} L78 200 L122 200 L120 {c - 26}Z")),
        "shirt": clip_circle(path(f"M0 200 L0 {c + 30} Q30 {c + 14} 78 {c + 11} Q100 {c + 27} 122 {c + 11} "
                                  f"Q170 {c + 14} 200 {c + 30} L200 200Z")),
        "ear_l": ellipse(100 - hw - 1, s["eyeY"] + 8, 7, 13, 12),
        "ear_r": ellipse(100 + hw + 1, s["eyeY"] + 8, 7, 13, 12),
        "face": path(face),
        "nose": path(nose),
        "stache": stache,
        "hair": path(hair),
    }


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = ["// Made by tools/comic_shapes.py from the comic face in app/panel/static/js/face.js; do not edit.",
           "// Points in the face's 200 x 200 box, times 4 (quarter units).", "#pragma once", "#include <pebble.h>", ""]
    for name, pts in shapes().items():
        flat = ", ".join(f"{{{r(x * 4)}, {r(y * 4)}}}" for x, y in pts for r in [round])
        out.append(f"static const GPoint COMIC_{name.upper()}[] = {{{flat}}};")
    out.append("")
    with open(os.path.join(here, "..", "src", "c", "comic_shapes.h"), "w") as f:
        f.write("\n".join(out))


if __name__ == "__main__":
    main()
