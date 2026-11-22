#!/usr/bin/env python3
"""Round 2 concept sketches: five cuter variations of concept 1 (sitting cat, stained glass),
250 mm high, with a lift-off head (seat at the neck). The ring stays 67 mm above the lower edge.

Run:  python3 tools/sketch_v2.py
Out:  sketches/round-2/concept-1<letter>-<key>.svg
Uses the drawing and checking code in tools/sketch.py.
"""
import math
import pathlib
import sys

from shapely.geometry import LineString, Polygon
from shapely import affinity, union_all

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sketch as sk  # noqa: E402

sk.H = 250.0
OUT = sk.OUT / "round-2"
NECK = 140.0  # seat of the lift-off head

catmull, mirror, lens, ellipse_pts = sk.catmull, sk.mirror, sk.lens, sk.ellipse_pts


# ---- Shape builders -------------------------------------------------------------------------
def body_half(chubby=0.0):
    c = chubby
    return [(70 + c, 0), (73 + c, 22), (73 + c, 48), (70 + c * 0.8, 72), (63 + c * 0.5, 96), (53, 116),
            (44, 133), (41, NECK + 6), (0, NECK + 6)]


def head_half(w=70.0, ear="pointy", ear_h=248.0, steep_chin=False):
    """Right half of the head from the neck up to the top centre. Chin flares out at 45 degrees max.
    steep_chin leaves room to tilt the head without breaking the 45-degree rule."""
    if steep_chin:
        base = [(41, NECK - 4), (48, 153), (w - 8, 172), (w, 188), (w - 2, 201), (w - 8, 213)]
    else:
        base = [(41, NECK - 4), (53, 149), (w - 4, 165), (w, 182), (w - 2, 199), (w - 8, 213)]
    if ear == "pointy":
        ear_pts = [(w - 12, 222), (w - 20, ear_h), (w - 34, 226)]
    else:  # rounded, smaller ear
        ear_pts = [(w - 13, 221), (w - 17, ear_h - 10), (w - 23, ear_h - 6), (w - 30, ear_h - 12), (w - 35, 225)]
    return base + ear_pts + [(0, 229)]


def smooth_half(half, corners):
    pts, start = [], 0
    for cidx in sorted(corners) + [len(half) - 1]:
        seg = catmull(half[start:cidx + 1], n=8)
        pts += seg if not pts else seg[1:]
        start = cidx
    return pts


def front_outline(chubby=0.0, w=70.0, ear="pointy", tilt=0.0):
    body = Polygon(mirror(smooth_half(body_half(chubby), [])))
    hh = head_half(w, ear, steep_chin=bool(tilt))
    corners = [7] if ear == "pointy" else []
    head = Polygon(mirror(smooth_half(hh, corners)))
    if tilt:
        head = affinity.rotate(head, tilt, origin=(0, NECK))
    shape = union_all([body, head]).buffer(0.01).buffer(-0.01)
    return [tuple(p) for p in shape.exterior.coords][:-1]


def side_outline(ear="pointy", tail_up=False):
    pts = [(54, 0), (57, 25), (56, 55), (50, 85), (42, 110), (36, 128), (37, NECK - 2), (47, 152), (55, 167),
           (57, 182), (53, 198), (44, 212), (33, 223)]
    if ear == "pointy":
        pts += [(18, 248), (8, 236), (-8, 235)]
    else:
        pts += [(22, 236), (15, 240), (8, 234), (-8, 233)]
    pts += [(-22, 226), (-35, 213), (-45, 198), (-49, 182), (-47, 165), (-42, 151), (-40, NECK), (-46, 124),
            (-58, 100), (-68, 70), (-74, 40), (-75, 15), (-72, 0)]
    corners = [0, len(pts) - 1]
    if ear == "pointy":
        corners += [13]
    return sk.poly_smooth(pts, corners=corners)


def tilt_pts(pts, tilt):
    if not tilt:
        return pts
    a = math.radians(tilt)
    return [(x * math.cos(a) - (z - NECK) * math.sin(a), NECK + x * math.sin(a) + (z - NECK) * math.cos(a))
            for x, z in pts]


def face(style="big", tilt=0.0, w=70.0):
    """Cute face features. style: big (round eyes), happy (closed ^ ^ eyes), sleepy."""
    f = []
    ex, ez, er = 26, 180, 12.5
    for s in (1, -1):
        if style == "happy":
            f.append({"kind": "line", "pts": catmull([(s * ex - 10, ez - 3), (s * ex, ez + 6), (s * ex + 10, ez - 3)], n=6), "sw": 2.2})
        elif style == "sleepy":
            f.append({"kind": "line", "pts": catmull([(s * ex - 10, ez + 2), (s * ex, ez - 5), (s * ex + 10, ez + 2)], n=6), "sw": 2.2})
            f.append({"kind": "line", "pts": [(s * ex + s * 8, ez - 2), (s * ex + s * 12, ez - 6)], "sw": 1.0})
        else:
            f.append({"kind": "thin", "pts": ellipse_pts(s * ex, ez, er, er * 1.08, 40), "sw": 2.0, "name": "eye"})
            f.append({"kind": "open", "pts": lens(s * ex, ez - 1, 7.5, 19), "sw": 1.2, "name": "pupil"})
            f.append({"kind": "solid", "pts": ellipse_pts(s * ex + 6.5, ez + 6, 2.4, 2.4, 16), "sw": 0.6, "cut": False})
        f.append({"kind": "blush", "pts": ellipse_pts(s * 47, 162, 8, 5, 28), "sw": 0.8, "cut": False})
        for k in range(3):
            f.append({"kind": "line", "pts": [(s * 14, 160 + k * 3.5), (s * (w - 12), 156 + k * 8 - 4)], "sw": 0.5})
        # inner ear panel
    f.append({"kind": "dark", "pts": catmull([(-4.5, 168), (4.5, 168), (0, 163.5)], n=4) + [(0, 163.5)], "sw": 1.0, "name": "nose"})
    f.append({"kind": "line", "pts": [(0, 163.5), (0, 160)], "sw": 1.1})
    f.append({"kind": "line", "pts": catmull([(0, 160), (-4, 156.5), (-8.5, 159)], n=5), "sw": 1.1})
    f.append({"kind": "line", "pts": catmull([(0, 160), (4, 156.5), (8.5, 159)], n=5), "sw": 1.1})
    # forehead tabby marks
    for x0 in (-7, 0, 7):
        f.append({"kind": "line", "pts": [(x0, 220), (x0 * 0.8, 211)], "sw": 1.4})
    # stained-glass leads on the head: brow arc and muzzle frame
    f.append({"kind": "line", "pts": catmull([(-w + 3, 196), (-34, 203), (0, 206), (34, 203), (w - 3, 196)], n=8), "sw": 2.2})
    for s in (1, -1):
        f.append({"kind": "line", "pts": catmull([(s * (w - 9), 171), (s * 30, 165), (s * 16, 150), (0, 145)], n=8), "sw": 2.2})
    return [dict(ft, pts=tilt_pts(ft["pts"], tilt)) for ft in f]


def ear_panels(w=70.0, ear="pointy", tilt=0.0):
    out = []
    for s in (1, -1):
        if ear == "pointy":
            p = [(s * (w - 15), 222), (s * (w - 20), 240), (s * (w - 29), 225)]
        else:
            p = catmull([(s * (w - 16), 223), (s * (w - 19), 234), (s * (w - 24), 236), (s * (w - 29), 225)], n=5)
        out.append({"kind": "thin", "pts": tilt_pts(p, tilt), "sw": 1.2, "cut": False})
    return out


def paws():
    out = []
    for s in (1, -1):
        p = [(s * 4, 0)] + catmull([(s * 4, 12), (s * 9, 21), (s * 17, 23), (s * 25, 20), (s * 29, 11)], n=6) + [(s * 29, 0)]
        out.append({"kind": "thin", "pts": p, "sw": 2.2, "name": "paw"})
        for xt in (12, 21):
            out.append({"kind": "line", "pts": [(s * xt, 15), (s * xt, 21)], "sw": 1.0})
    return out


def heart(cx, cz, s):
    pts = []
    for i in range(60):
        t = 2 * math.pi * i / 60
        x = 16 * math.sin(t) ** 3
        z = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s, cz + z * s))
    return pts


def band_lines(outline, z0, z1):
    reg = Polygon(outline)
    out = []
    for z in (z0, z1):
        sec = reg.intersection(LineString([(-200, z), (200, z)]))
        xs = [c[0] for g in getattr(sec, "geoms", [sec]) for c in g.coords]
        out.append([(min(xs), z), (max(xs), z)])
    return out


def side_feats(style="big", ear="pointy"):
    f = []
    if style == "big":
        f.append({"kind": "thin", "pts": lens(48, 180, 7, 16), "sw": 1.6})
    else:
        f.append({"kind": "line", "pts": catmull([(43, 178), (48, 182), (53, 178)], n=4), "sw": 1.8})
    f.append({"kind": "blush", "pts": ellipse_pts(42, 162, 6, 4, 24), "sw": 0.6, "cut": False})
    if ear == "pointy":
        f.append({"kind": "thin", "pts": [(14, 230), (17, 242), (10, 234)], "sw": 1.0, "cut": False})
    f.append({"kind": "line", "pts": catmull([(-48, 190), (-20, 205), (10, 207), (36, 201), (54, 192)], n=8), "sw": 2.2})
    f.append({"kind": "line", "pts": catmull([(56, 170), (40, 158), (40, 146)], n=6), "sw": 2.2})
    return f


def tail_front():
    return catmull([(70, 5), (62, 13), (50, 18), (39, 17), (33, 11)], n=10)


def tail_side(up=False):
    if up:
        return catmull([(-62, 6), (-66, 40), (-58, 80), (-48, 108), (-42, 124)], n=10)
    return catmull([(-72, 3), (-50, 4), (-20, 6), (12, 8), (40, 7), (52, 4)], n=10)


def top_view(w=73, ear_x=52, ear="pointy", extra=()):
    feats = [{"kind": "line", "pts": [(-48, 0), (48, 0)], "sw": 1.2}]
    for s in (1, -1):
        feats.append({"kind": "thin", "pts": [(s * (ear_x - 10), -6), (s * (ear_x + 4), 1), (s * (ear_x - 10), 8)]})
    feats.append({"kind": "open", "pts": [(-12, -2.5), (12, -2.5), (12, 2.5), (-12, 2.5)], "name": "ridge vent"})
    return dict(outline=sk.ellipse_quarters(w, 58, 75), features=feats + list(extra), rib_r=60)


BODY_CLIP = [(-95, 0), (95, 0), (95, NECK - 1), (-95, NECK - 1)]
ACCESS = "lift the head off (seat at z 140, opening ~Ø80), or fingers from below"


def common(front_outline_pts, feats, leads, seeds, seed, share=0.5, side_style="big", ear="pointy",
           side_tail_up=False, top=None, extra_side_leads=()):
    return dict(
        front=dict(outline=front_outline_pts, features=feats, leads=leads, mosaic=("voronoi", seeds, seed),
                   open_share=share, mosaic_clip=BODY_CLIP, split_z=NECK, split_label="lift-off head"),
        side=dict(outline=side_outline(ear), features=side_feats(side_style, ear),
                  leads=[tail_side(side_tail_up), *extra_side_leads], mosaic=("voronoi", int(seeds * 0.8), seed + 3),
                  open_share=share, mosaic_clip=BODY_CLIP, split_z=NECK, split_label="lift-off head"),
        top=top or top_view(ear=ear),
        access=ACCESS,
    )


# ---- The five variations ---------------------------------------------------------------------
def v_kitten():
    out = front_outline()
    feats = face("big") + ear_panels() + paws()
    return dict(key="big-eyed-kitten", label="1A", name="Big-eyed kitten",
                tagline="Kitten proportions: big head, big glowing eyes with open slit pupils, pink cheeks, paws in front, tail curled round.",
                **common(out, feats, [tail_front()], 22, 31))


def v_tilt():
    t = 6.0
    out = front_outline(tilt=t)
    feats = face("big", tilt=t) + ear_panels(tilt=t) + paws()
    return dict(key="head-tilt", label="1B", name="Curious head tilt",
                tagline="Same kitten, head tilted 6° as if it hears something. Rounder body panels, tail curled round the paws.",
                **common(out, feats, [tail_front()], 18, 44))


def v_heart():
    out = front_outline()
    feats = face("happy") + ear_panels() + paws() + [
        {"kind": "thin", "pts": heart(0, 84, 1.35), "sw": 2.6, "name": "heart"},
        {"kind": "open", "pts": heart(0, 84, 0.55)[0:1] and sk.teardrop(0, 82, 5), "sw": 1, "name": "heart window"}]
    return dict(key="happy-heart", label="1C", name="Happy cat with heart",
                tagline="Closed, smiling eyes (^ ^) and a big glowing heart on the chest with a small window in it. Warm and calm.",
                **common(out, feats, [tail_front()], 22, 57, share=0.45, side_style="happy"))


def v_chubby():
    out = front_outline(chubby=4, w=70, ear="round")
    feats = face("big") + ear_panels(ear="round") + paws()
    return dict(key="chubby-round-ears", label="1D", name="Chubby, round ears",
                tagline="Rounder, softer cat: small rounded ears, wider belly, few big panels and more open area, so more light on the wall.",
                **common(out, feats, [tail_front()], 12, 72, share=0.75, ear="round",
                         top=dict(top_view(ear="round", w=76), outline=sk.ellipse_quarters(76, 58, 75))))


def v_collar():
    out = front_outline()
    feats = face("big") + ear_panels() + paws()
    bands = band_lines(out, NECK - 5, NECK + 5)
    tag = sk.ellipse_pts(0, NECK - 14, 6.5, 6.5, 28)
    feats += [{"kind": "solid", "pts": tag, "sw": 1.6, "name": "bell"},
              {"kind": "line", "pts": [(0, NECK - 15), (0, NECK - 20)], "sw": 1.0}]
    sbands = band_lines(side_outline(), NECK - 5, NECK + 5)
    return dict(key="collar-bell", label="1E", name="Collar and bell",
                tagline="A collar hides the joint between head and body; a flat bell hangs on the chest. Tail goes up the back.",
                **common(out, feats, [tail_front(), *bands], 22, 88, side_tail_up=True, extra_side_leads=sbands))


VARIANTS = [v_kitten, v_tilt, v_heart, v_chubby, v_collar]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in VARIANTS:
        c = fn()
        svg, checks, rmax = sk.render(c, c["label"])
        p = OUT / f"concept-{c['label'].lower()}-{c['key']}.svg"
        p.write_text(svg, encoding="utf-8")
        print(f"{p.name}: " + ", ".join(f"{n} overhang {w:.0f}°" for n, w in checks) + f", top Ø{2 * rmax:.0f}")


if __name__ == "__main__":
    main()
