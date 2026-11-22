#!/usr/bin/env python3
"""Make dimensioned concept sketches (front, side, top) for the cat lamp shade.

Run:  python3 tools/sketch.py
Out:  sketches/concept-<n>-<key>.svg

Each view is checked for the print rules (no overhang steeper than 45 degrees from vertical,
fits in a 160 mm cylinder). The script stops with an error when a concept breaks a rule.
Needs: numpy, shapely, scipy.
"""
import math
import pathlib
import random

import numpy as np
import shapely
from shapely.geometry import MultiPoint, Point, Polygon, LineString
from shapely.geometry.polygon import orient

OUT = pathlib.Path(__file__).resolve().parent.parent / "sketches"

# ---- Fixed requirements (mm) -------------------------------------------------------------
H = 200.0            # total height
ENV_D = 160.0        # max diameter of the wrapping cylinder
RING_Z = 67.0        # mounting ring height (top face), 1/3 of H from the lower edge
RING_OD, RING_ID, RING_T = 47.0, 28.0, 5.0
BULB_D, BULB_L = 45.0, 70.0   # E14 bulb, worst case (glass, without the screw base)
BULB_Z0 = RING_Z + 8.0        # glass starts just above the ring nut
OVERHANG_MAX = 45.0           # degrees from vertical
BRIDGE_OK = 6.0               # mm: a flat hole top up to this length prints without supports
LEAD = 2.5                    # mm: width of a "lead" rib between panels

# ---- Drawing scale and colours --------------------------------------------------------------
S = 1.75  # px per mm
INK, DIM, HID = "#23201c", "#3a6ea5", "#8b8378"
GLOW, GLOW2, OPEN_BG, SOLID = "#f7c46c", "#fbe3b0", "#ffffff", "#b9b2a6"
FONT = "Inter, 'DejaVu Sans', Arial, sans-serif"


# ---- Geometry helpers ---------------------------------------------------------------------
def catmull(pts, n=10, closed=False):
    """Smooth curve through pts (Catmull-Rom). Keeps the end points."""
    p = [np.array(q, float) for q in pts]
    if closed:
        p = [p[-1]] + p + [p[0], p[1]]
    else:
        p = [p[0]] + p + [p[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(p[-2])
    return [tuple(q) for q in out]


def mirror(half):
    """half: right half profile from (x>0, 0) up to (0, ztop). Returns the full closed outline."""
    left = [(-x, z) for x, z in reversed(half[:-1]) if x > 1e-6] if half[-1][0] == 0 else []
    if half[-1][0] != 0:
        left = [(-x, z) for x, z in reversed(half)]
    return half + left


def profile(half, smooth=True, corners=()):
    """Smooth a half profile, but keep sharp points (ear tips) listed by index in corners."""
    if not smooth:
        return mirror(half)
    pieces, start = [], 0
    for c in sorted(corners) + [len(half) - 1]:
        seg = catmull(half[start:c + 1], n=8)
        pieces += seg if not pieces else seg[1:]
        start = c
    return mirror(pieces)


def poly_smooth(pts, corners=()):
    """Smooth a full closed outline; indices in corners stay sharp."""
    if not corners:
        return catmull(pts, n=8, closed=True)
    n = len(pts)
    cs = sorted(corners)
    out = []
    for a, b in zip(cs, cs[1:] + [cs[0] + n]):
        seg = [pts[i % n] for i in range(a, b + 1)]
        out += catmull(seg, n=8)[:-1]
    return out


def overhang_report(outline, bed_z=0.5):
    """Steepest downward-facing edge of a closed outline, in degrees from vertical."""
    poly = orient(Polygon(outline), 1.0)  # CCW
    xy = list(poly.exterior.coords)
    worst, where = 0.0, None
    for (x1, z1), (x2, z2) in zip(xy, xy[1:]):
        dx, dz = x2 - x1, z2 - z1
        L = math.hypot(dx, dz)
        if L < 1e-9 or (z1 < bed_z and z2 < bed_z):
            continue
        nz = -dx / L  # outward normal z for a CCW outline
        if nz < 0:  # faces down
            ang = math.degrees(math.acos(min(1.0, -nz)))  # 0 = flat ceiling
            from_vertical = 90.0 - ang
            if from_vertical > worst:
                worst, where = from_vertical, ((x1 + x2) / 2, (z1 + z2) / 2)
    return worst, where


def hole_ok(hole):
    """True when an opening prints without supports: its top edges are >= 45 degrees,
    or a flat run is at most BRIDGE_OK long."""
    hole = orient(hole, 1.0)
    xy = list(hole.exterior.coords)
    run, worst = 0.0, 0.0
    for (x1, z1), (x2, z2) in zip(xy, xy[1:]):
        dx, dz = x2 - x1, z2 - z1
        L = math.hypot(dx, dz)
        if L < 1e-9:
            continue
        # material is outside the hole; at the top edge (CCW goes right->left) it faces down
        if dx / L < -math.cos(math.radians(OVERHANG_MAX)) - 1e-9:
            run += abs(dx)
            worst = max(worst, run)
        else:
            run = 0.0
    return worst <= BRIDGE_OK


def ellipse_pts(cx, cz, rx, rz, n=48, a0=0.0):
    return [(cx + rx * math.cos(a0 + 2 * math.pi * i / n), cz + rz * math.sin(a0 + 2 * math.pi * i / n))
            for i in range(n)]


def lens(cx, cz, w, h, n=16):
    """Pointed oval (vertical slit), points at top and bottom."""
    r = (w * w / 4 + h * h / 4) / w
    pts = []
    for s in (1, -1):
        c = cx - s * (r - w / 2)
        a = math.asin((h / 2) / r)
        for t in np.linspace(-a, a, n):
            pts.append((c + s * r * math.cos(t), cz + s * r * math.sin(t)))
    return pts


def teardrop(cx, cz, r, n=14):
    """Round hole with a 45-degree pointed top: prints without supports."""
    pts = [(cx + r * math.cos(a), cz + r * math.sin(a))
           for a in np.linspace(math.radians(-225), math.radians(45), n)]
    pts.append((cx, cz + r * math.sqrt(2)))
    return pts


def gothic_arch(cx, z0, w, h):
    """Pointed (equilateral) arch window."""
    r = w
    zc = z0 + h - math.sqrt(r * r - (w / 2) ** 2)
    right = [(cx - w / 2 + r * math.cos(a), zc + r * math.sin(a))
             for a in np.linspace(0, math.acos(0.5), 10)]
    left = [(cx + w / 2 - r * math.cos(a), zc + r * math.sin(a))
            for a in np.linspace(math.acos(0.5), 0, 10)]
    return [(cx - w / 2, z0), (cx + w / 2, z0)] + right[0:1] + right + left[1:] + [(cx - w / 2, zc)]


def cat_cutout(cx, z0, s):
    """Small sitting-cat silhouette (front view) as a hole, height ~ 34*s mm.
    Steep shoulders and pointed ears so it prints without supports."""
    pts = [(-9, 0), (9, 0), (10, 6), (9, 13), (6, 18), (4.5, 21), (7, 25), (7.5, 29), (5, 34.5),
           (2, 30.5), (-2, 30.5), (-5, 34.5), (-7.5, 29), (-7, 25), (-4.5, 21),
           (-6, 18), (-9, 13), (-10, 6)]
    return [(cx + x * s, z0 + z * s) for x, z in pts]


# ---- Panels (stained-glass mosaic) ----------------------------------------------------------
def voronoi_panels(region, n, seed, keep_out=None):
    rng = random.Random(seed)
    minx, minz, maxx, maxz = region.bounds
    pts = []
    while len(pts) < n:
        p = Point(rng.uniform(minx, maxx), rng.uniform(minz, maxz))
        if region.contains(p):
            pts.append(p)
    cells = shapely.voronoi_polygons(MultiPoint(pts), extend_to=region.envelope.buffer(20))
    out = []
    for c in cells.geoms:
        c = c.intersection(region)
        if keep_out is not None:
            c = c.difference(keep_out)
        for g in getattr(c, "geoms", [c]):
            if g.geom_type == "Polygon" and g.area > 4:
                out.append(g)
    return out


def tri_panels(region, extra, n, seed, keep_out=None):
    rng = random.Random(seed)
    minx, minz, maxx, maxz = region.bounds
    pts = list(region.exterior.coords)[:-1] + list(extra)
    inner = region.buffer(-8)
    while len(pts) < len(region.exterior.coords) + len(extra) + n:
        p = (rng.uniform(minx, maxx), rng.uniform(minz, maxz))
        if inner.contains(Point(p)):
            pts.append(p)
    tris = shapely.delaunay_triangles(MultiPoint(pts))
    out = []
    for t in tris.geoms:
        if region.buffer(0.5).contains(t.centroid):
            g = t.intersection(region)
            if keep_out is not None:
                g = g.difference(keep_out)
            for h in getattr(g, "geoms", [g]):
                if h.geom_type == "Polygon" and h.area > 4:
                    out.append(h)
    return out


def pointed(hole):
    """Cut a 45-degree tent over an opening, with its peak at the highest point.
    Every top edge is then 45 degrees or steeper, so it prints without supports."""
    top = max(hole.exterior.coords, key=lambda q: q[1])
    tent = Polygon([(top[0] - 400, top[1] - 400), (top[0], top[1]), (top[0] + 400, top[1] - 400)])
    g = hole.intersection(tent)
    if g.geom_type != "Polygon":
        g = max(getattr(g, "geoms", []), key=lambda h: h.area, default=Polygon())
    return g


def pick_open(cells, region, share, seed, zmin=6.0, zmax=None):
    """Choose which panels get an opening. Each opening sits inside its panel with a
    pointed (45-degree) top, and keeps a solid border to the outline. Returns {index: hole}."""
    rng = random.Random(seed + 99)
    inner = region.buffer(-LEAD * 1.6)
    cand = {}
    for i, c in enumerate(cells):
        hole = c.buffer(-LEAD * 0.9, join_style=2)
        if hole.is_empty or hole.geom_type != "Polygon":
            continue
        hole = pointed(hole)
        if hole.is_empty or hole.area < 40 or hole.area > 1400:
            continue
        if not inner.contains(hole) or hole.bounds[1] < zmin:
            continue
        if zmax is not None and hole.bounds[3] > zmax:
            continue
        if hole_ok(hole):
            cand[i] = hole
    keys = list(cand)
    rng.shuffle(keys)
    return {k: cand[k] for k in keys[: int(round(share * len(keys)))]}


# ---- SVG writer ---------------------------------------------------------------------------
class Sheet:
    def __init__(self, w, h):
        self.w, self.h, self.items = w, h, []

    def add(self, s):
        self.items.append(s)

    def svg(self):
        defs = f"""<defs>
<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0,1 L10,5 L0,9 z" fill="{DIM}"/></marker>
<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
<path d="M0,1 L10,5 L0,9 z" fill="#c0392b"/></marker>
<pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
<rect width="6" height="6" fill="{OPEN_BG}"/><line x1="0" y1="0" x2="0" y2="6" stroke="#9cc3e6" stroke-width="1.4"/></pattern>
<radialGradient id="glow" cx="50%" cy="45%" r="70%"><stop offset="0" stop-color="{GLOW2}"/><stop offset="1" stop-color="{GLOW}"/></radialGradient>
</defs>"""
        body = "\n".join(self.items)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
                f'width="{self.w}" height="{self.h}" font-family="{FONT}">\n'
                f'<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->\n{defs}\n'
                f'<rect width="{self.w}" height="{self.h}" fill="#fbfaf7"/>\n{body}\n</svg>\n')


class View:
    """Maps model mm (x right, z up) to sheet px."""

    def __init__(self, sheet, ox, oy):
        self.sh, self.ox, self.oy = sheet, ox, oy

    def p(self, x, z):
        return self.ox + x * S, self.oy - z * S

    def path(self, pts, closed=True):
        d = " ".join(("M" if i == 0 else "L") + f"{a:.1f},{b:.1f}"
                     for i, (a, b) in enumerate(self.p(x, z) for x, z in pts))
        return d + (" Z" if closed else "")

    def poly(self, pts, fill="none", stroke=INK, sw=1.0, extra=""):
        self.sh.add(f'<path d="{self.path(pts)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
                    f'stroke-linejoin="round" {extra}/>')

    def line(self, pts, stroke=INK, sw=1.0, extra=""):
        self.sh.add(f'<path d="{self.path(pts, False)}" fill="none" stroke="{stroke}" stroke-width="{sw}" '
                    f'stroke-linecap="round" stroke-linejoin="round" {extra}/>')

    def text(self, x, z, s, size=12, anchor="middle", color=INK, weight=400, dx=0, dy=0, rotate=None):
        X, Y = self.p(x, z)
        X, Y = X + dx, Y + dy
        rot = f' transform="rotate({rotate} {X:.1f} {Y:.1f})"' if rotate else ""
        self.sh.add(f'<text x="{X:.1f}" y="{Y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" '
                    f'font-weight="{weight}"{rot}>{s}</text>')

    def hdim(self, x1, x2, z, label, ext_from=None):
        """Horizontal dimension at height z (mm), with extension lines from ext_from z values."""
        if ext_from:
            for x, ze in zip((x1, x2), ext_from):
                self.line([(x, ze), (x, z + (2 if z > ze else -2))], stroke=DIM, sw=0.6)
        self.line([(x1, z), (x2, z)], stroke=DIM, sw=1.0, extra='marker-start="url(#ar)" marker-end="url(#ar)"')
        self.text((x1 + x2) / 2, z, label, size=12, color=DIM, weight=600, dy=-5)

    def vdim(self, x, z1, z2, label, ext_from=None, side=1):
        if ext_from:
            for z, xe in zip((z1, z2), ext_from):
                self.line([(xe, z), (x + 2 * side, z)], stroke=DIM, sw=0.6)
        self.line([(x, z1), (x, z2)], stroke=DIM, sw=1.0, extra='marker-start="url(#ar)" marker-end="url(#ar)"')
        X, Y = self.p(x, (z1 + z2) / 2)
        self.sh.add(f'<text x="{X - 6 * side:.1f}" y="{Y:.1f}" font-size="12" fill="{DIM}" font-weight="600" '
                    f'text-anchor="middle" transform="rotate(-90 {X - 6 * side:.1f} {Y:.1f})">{label}</text>')


# ---- Common parts drawn in every elevation ----------------------------------------------------
def draw_internals(v, wall_r_at):
    """Mounting ring (cone washer), support ribs, E14 socket and bulb as hidden lines."""
    BULB_Z0 = RING_Z + 8.0
    dash = 'stroke-dasharray="5 3"'
    # socket and lamp stem below
    v.poly([(-15, -22), (15, -22), (15, RING_Z + 6), (-15, RING_Z + 6)], fill="#00000008", stroke=HID, sw=0.9,
           extra=dash)
    v.text(0, -22, "E14 socket", size=10, color=HID, dy=13)
    # bulb (worst case)
    bulb = catmull([(-8, BULB_Z0), (-BULB_D / 2, BULB_Z0 + BULB_L * 0.45), (-BULB_D / 2 + 3, BULB_Z0 + BULB_L * 0.8),
                    (0, BULB_Z0 + BULB_L), (BULB_D / 2 - 3, BULB_Z0 + BULB_L * 0.8),
                    (BULB_D / 2, BULB_Z0 + BULB_L * 0.45), (8, BULB_Z0)], n=8)
    v.poly(bulb, fill="#fff6c855", stroke="#c9a227", sw=0.9, extra=dash)
    v.text(0, BULB_Z0 + BULB_L * 0.45, "bulb", size=10, color="#a8861c")
    # ring: flat top face at RING_Z, 45-degree cone underneath (prints without supports)
    ro, ri = RING_OD / 2, RING_ID / 2
    cone = ro - ri - 1.5
    for s in (1, -1):
        v.poly([(s * ri, RING_Z), (s * ro, RING_Z), (s * ro, RING_Z - RING_T), (s * (ri + 1.5), RING_Z - RING_T - cone + 3),
                (s * ri, RING_Z - RING_T - cone + 3)], fill="#d9d2c3", stroke=INK, sw=0.9)
    # three ribs at 45 degrees from the ring down to the wall
    z_top = RING_Z - RING_T
    for s in (1, -1):
        wr = wall_r_at(s)
        z_wall = z_top - (wr - ro)
        v.line([(s * ro, z_top), (s * wr, z_wall)], stroke=HID, sw=1.4, extra=dash)
        v.line([(s * ro, RING_Z), (s * wr, RING_Z - (wr - ro) + 0)], stroke=HID, sw=0.8, extra=dash)


def legend(sh, x, y):
    items = [("url(#glow)", "thin wall, glows (0.8-1.2 mm)"), ("url(#hatch)", "open"),
             (SOLID, "thick / solid"), (None, "lead rib 2.5 mm")]
    for i, (fill, label) in enumerate(items):
        X = x + i * 205
        if fill:
            sh.add(f'<rect x="{X}" y="{y - 11}" width="22" height="14" fill="{fill}" stroke="{INK}" stroke-width="1"/>')
        else:
            sh.add(f'<line x1="{X}" y1="{y - 4}" x2="{X + 22}" y2="{y - 4}" stroke="{INK}" stroke-width="{LEAD * S}"/>')
        sh.add(f'<text x="{X + 30}" y="{y}" font-size="12" fill="{INK}">{label}</text>')
    X = x + 4 * 205 - 40
    sh.add(f'<line x1="{X}" y1="{y - 4}" x2="{X + 26}" y2="{y - 4}" stroke="{HID}" stroke-width="1.2" stroke-dasharray="5 3"/>')
    sh.add(f'<text x="{X + 32}" y="{y}" font-size="12" fill="{INK}">hidden (ring, ribs, bulb)</text>')


# ---- Rendering of one elevation -------------------------------------------------------------
def render_elevation(sh, ox, oy, title, el, check):
    v = View(sh, ox, oy)
    outline = el["outline"]
    region = Polygon(outline).buffer(0)
    worst, where = overhang_report(outline)
    check.append((title, worst))

    keep_out = None
    feats = el.get("features", [])
    solid_feats = [Polygon(f["pts"]) for f in feats if f["kind"] != "line" and f.get("cut", True)]
    if solid_feats:
        keep_out = shapely.union_all([g.buffer(LEAD * 0.4) for g in solid_feats])

    mosaic = el.get("mosaic", ("voronoi", 24, 1))
    mregion = region
    if el.get("mosaic_clip") is not None:
        mregion = region.intersection(Polygon(el["mosaic_clip"]))
    if mosaic[0] == "voronoi":
        cells = voronoi_panels(mregion, mosaic[1], mosaic[2], keep_out)
    elif mosaic[0] == "tri":
        cells = tri_panels(mregion, el.get("tri_extra", []), mosaic[1], mosaic[2], keep_out)
    elif mosaic[0] == "bands":
        cells = []
        for z0, z1 in mosaic[1]:
            band = mregion.intersection(Polygon([(-200, z0), (200, z0), (200, z1), (-200, z1)]))
            if keep_out is not None:
                band = band.difference(keep_out)
            cells += [g for g in getattr(band, "geoms", [band]) if g.geom_type == "Polygon" and g.area > 4]
    else:
        cells = []
    opened = pick_open(cells, region, el.get("open_share", 0.35), mosaic[2] if len(mosaic) > 2 else 0,
                       zmax=el.get("open_zmax"))
    if mosaic[0] != "voronoi" and mosaic[0] != "tri":
        opened = {}

    # base fill = glowing wall
    v.poly(outline, fill="url(#glow)", stroke="none")
    for i, c in enumerate(cells):
        pts = list(c.exterior.coords)
        v.poly(pts, fill="none", stroke=INK, sw=LEAD * S * 0.9)
        if i in opened:
            v.poly(list(opened[i].exterior.coords), fill="url(#hatch)", stroke=INK, sw=1.2)
    for f in feats:
        fill = {"open": "url(#hatch)", "thin": "url(#glow)", "solid": SOLID, "dark": "#5a5248", "blush": "#f4a7a0", "line": "none"}[f["kind"]]
        if f["kind"] == "line":
            v.line(f["pts"], stroke=INK, sw=f.get("sw", LEAD) * S)
        else:
            if f["kind"] == "open" and not hole_ok(Polygon(f["pts"])):
                raise SystemExit(f"{title}: opening '{f.get('name')}' needs supports")
            v.poly(f["pts"], fill=fill, stroke=INK, sw=f.get("sw", LEAD) * S * 0.8)
    for ln in el.get("leads", []):
        v.line(ln, stroke=INK, sw=LEAD * S)
    v.poly(outline, fill="none", stroke=INK, sw=4.2)
    if el.get("split_z") is not None:
        zc = el["split_z"]
        sl = region.intersection(LineString([(-200, zc), (200, zc)]))
        if not sl.is_empty:
            (a, _), (b, _) = sl.coords[0], sl.coords[-1]
            v.line([(a - 6, zc), (b + 6, zc)], stroke="#c0392b", sw=1.6, extra='stroke-dasharray="9 4"')
            v.text(b + 8, zc, el.get("split_label", "lift-off cap"), size=11, anchor="start", color="#c0392b", dy=4)

    # internals
    def wall_r_at(sgn):
        z = RING_Z - RING_T - 25
        sec = region.intersection(LineString([(-200, z), (200, z)]))
        xs = [c[0] for g in getattr(sec, "geoms", [sec]) for c in g.coords]
        return (max(xs) if sgn > 0 else -min(xs)) - LEAD
    draw_internals(v, wall_r_at)

    # envelope + bed
    for s in (1, -1):
        v.line([(s * ENV_D / 2, -4), (s * ENV_D / 2, H + 4)], stroke="#9aa5b1", sw=0.8, extra='stroke-dasharray="2 4"')
    v.line([(-95, 0), (95, 0)], stroke=INK, sw=0.8)

    # dimensions
    minx, minz, maxx, maxz = region.bounds
    v.hdim(minx, maxx, H + 16, f"{maxx - minx:.0f}", ext_from=(region.bounds[3] - 5, region.bounds[3] - 5))
    v.vdim(94, 0, H, f"{H:.0f}", side=-1)
    v.vdim(-94, 0, RING_Z, f"ring {RING_Z:.0f}", side=1)
    v.line([(-94, RING_Z), (-RING_OD / 2, RING_Z)], stroke=DIM, sw=0.6)
    bot = region.intersection(LineString([(-200, 0.01), (200, 0.01)]))
    bx = [c[0] for g in getattr(bot, "geoms", [bot]) for c in g.coords]
    v.hdim(min(bx) + LEAD, max(bx) - LEAD, -36, f"open bottom {max(bx) - min(bx) - 2 * LEAD:.0f}")
    v.text(0, H + 32, title, size=14, weight=700)
    v.text(78, -40, f"max overhang {worst:.0f}°", size=11, anchor="end",
           color=("#1e7d32" if worst <= OVERHANG_MAX + 0.01 else "#c0392b"), dy=24)
    return v


def render_top(sh, ox, oy, top, el_front):
    v = View(sh, ox, oy)
    outline = top["outline"]
    poly = Polygon(outline)
    rmax = max(math.hypot(x, y) for x, y in outline)
    v.poly(ellipse_pts(0, 0, ENV_D / 2, ENV_D / 2, 96), fill="none", stroke="#9aa5b1", sw=0.9,
           extra='stroke-dasharray="2 4"')
    v.poly(outline, fill="url(#glow)", stroke=INK, sw=4.2)
    for f in top.get("features", []):
        fill = {"open": "url(#hatch)", "thin": "url(#glow)", "solid": SOLID, "dark": "#5a5248", "blush": "#f4a7a0", "line": "none"}[f["kind"]]
        if f["kind"] == "line":
            v.line(f["pts"], stroke=INK, sw=f.get("sw", LEAD) * S)
        else:
            v.poly(f["pts"], fill=fill, stroke=INK, sw=LEAD * S * 0.8)
    # ribs (hidden) and ring
    wall = top.get("rib_r", 62)
    for k in range(3):
        a = math.radians(90 + 120 * k)
        v.line([(RING_OD / 2 * math.cos(a), RING_OD / 2 * math.sin(a)), (wall * math.cos(a), wall * math.sin(a))],
               stroke=HID, sw=1.6, extra='stroke-dasharray="5 3"')
    v.poly(ellipse_pts(0, 0, RING_OD / 2, RING_OD / 2), fill="#d9d2c3", stroke=INK, sw=1.0,
           extra='stroke-dasharray="5 3"')
    v.poly(ellipse_pts(0, 0, RING_ID / 2, RING_ID / 2), fill="#fbfaf7", stroke=INK, sw=1.0,
           extra='stroke-dasharray="5 3"')
    minx, miny, maxx, maxy = poly.bounds
    v.hdim(minx, maxx, maxy + 14, f"{maxx - minx:.0f}")
    v.vdim(maxx + 14, miny, maxy, f"{maxy - miny:.0f}", side=-1)
    v.hdim(-ENV_D / 2, ENV_D / 2, -ENV_D / 2 - 10, f"envelope Ø{ENV_D:.0f}")
    v.line([(RING_OD / 2 * 0.7, -RING_OD / 2 * 0.7), (46, -58)], stroke=DIM, sw=0.8)
    v.text(46, -58, f"ring Ø{RING_OD:.0f} / Ø{RING_ID:.0f}, {RING_T:.0f} thick", size=11, anchor="start",
           color=DIM, weight=600, dy=12)
    v.text(0, ENV_D / 2 + 26, "TOP", size=14, weight=700)
    v.text(-ENV_D / 2, ENV_D / 2 + 8, "front ↓", size=11, anchor="start", color=HID)
    if rmax > ENV_D / 2 + 0.01:
        raise SystemExit(f"top outline radius {rmax:.1f} > {ENV_D / 2}")
    return rmax


def render(c, idx):
    ground = int(165 + H * S)
    W, Hh = 1220, ground + 140
    sh = Sheet(W, Hh)
    sh.add(f'<text x="24" y="38" font-size="22" font-weight="700" fill="{INK}">Concept {c.get("label", idx)} — {c["name"]}</text>')
    sh.add(f'<text x="24" y="60" font-size="13" fill="#5b554c">{c["tagline"]}</text>')
    sh.add(f'<text x="{W - 24}" y="38" font-size="12" text-anchor="end" fill="#5b554c">All dimensions in mm · '
           f'concept sketch, not final geometry</text>')
    checks = []
    render_elevation(sh, 210, ground, "FRONT", c["front"], checks)
    render_elevation(sh, 590, ground, "SIDE", c["side"], checks)
    rmax = render_top(sh, 980, ground - H * S / 2 - 30, c["top"], c["front"])
    sh.add(f'<text x="980" y="{ground + 30}" font-size="12" text-anchor="middle" fill="{INK}">'
           f'access: {c["access"]}</text>')
    sh.add(f'<text x="980" y="{ground + 48}" font-size="12" text-anchor="middle" fill="#1e7d32">'
           f'fits Ø{2 * rmax:.0f} ≤ Ø{ENV_D:.0f} · no supports needed</text>')
    # print direction arrow
    sh.add(f'<line x1="70" y1="{ground - 20}" x2="70" y2="{ground - 90}" stroke="#c0392b" stroke-width="2" '
           f'marker-end="url(#ah)"/><text x="64" y="{ground - 96}" font-size="11" fill="#c0392b" '
           f'text-anchor="middle">print</text>')
    legend(sh, 24, Hh - 18)
    for name, worst in checks:
        if worst > OVERHANG_MAX + 0.01:
            raise SystemExit(f'{c["name"]} {name}: overhang {worst:.1f}° > {OVERHANG_MAX}°')
    return sh.svg(), checks, rmax


# =====================================================================================
# Concepts. Coordinates in mm: x across, z up from the lower edge (bed). Socket axis at x = 0.
# =====================================================================================
def eye_pair(cx, cz, w, h, pupil=True, slant=0.0):
    out = []
    for s in (1, -1):
        e = lens(0, 0, w, h)
        # turn the almond so it lies across, then slant the outer corner up a little
        a = math.radians(90 - s * slant)
        e = [(s * cx + x * math.cos(a) - z * math.sin(a), cz + x * math.sin(a) + z * math.cos(a)) for x, z in e]
        out.append({"kind": "thin", "pts": e, "sw": 2.0, "name": "eye"})
        if pupil:
            out.append({"kind": "open", "pts": lens(s * cx, cz, w * 0.22, h * 0.95), "sw": 1.2, "name": "pupil"})
    return out


def concept_sitting():
    half = [(68, 0), (71, 18), (71, 38), (67, 58), (59, 80), (49, 99), (41, 113), (46, 124), (53, 135),
            (56, 148), (54, 160), (52, 170), (43, 200), (27, 183), (0, 186)]
    front = profile(half, corners=(12, 13))
    side = poly_smooth([(53, 0), (56, 22), (55, 46), (49, 76), (41, 100), (37, 115), (44, 126), (50, 140),
                        (49, 155), (42, 168), (31, 179), (21, 200), (9, 187), (-8, 187), (-24, 173),
                        (-36, 161), (-42, 146), (-40, 129), (-45, 112), (-57, 91), (-66, 64), (-72, 38),
                        (-73, 14), (-70, 0)], corners=(0, 11, 12, 23))
    tail = catmull([(64, 6), (50, 16), (26, 22), (6, 20), (-6, 14), (-4, 6), (6, 4), (14, 9)], n=10)
    tail_s = catmull([(-70, 3), (-50, 4), (-20, 6), (12, 8), (40, 7), (52, 4)], n=10)
    face = eye_pair(19, 150, 17, 9, slant=12) + [
        {"kind": "thin", "pts": [(-4, 138), (4, 138), (0, 133)], "sw": 1.5, "name": "nose"},
        {"kind": "thin", "pts": [(36, 178), (45, 194), (33, 186)], "sw": 1.2, "cut": True},
        {"kind": "thin", "pts": [(-36, 178), (-45, 194), (-33, 186)], "sw": 1.2, "cut": True},
        {"kind": "line", "pts": [(0, 133), (0, 128)], "sw": 1.2},
        {"kind": "line", "pts": [(0, 128), (-7, 124), (-12, 127)], "sw": 1.2},
        {"kind": "line", "pts": [(0, 128), (7, 124), (12, 127)], "sw": 1.2},
    ] + [{"kind": "line", "pts": [(s * 12, 132 + k * 3), (s * 46, 128 + k * 7)], "sw": 0.6} for s in (1, -1) for k in range(3)]
    return dict(
        key="sitting-stained-glass", name="Sitting cat, stained glass",
        tagline="Closest to your reference: sitting cat, curled tail, mosaic of glowing and open panels. Head closed, ridge vent between the ears.",
        access="hand from below, through 3 gaps of ~35-40 mm beside the ring",
        front=dict(outline=front, features=face, leads=[tail], mosaic=("voronoi", 34, 7), open_share=0.55),
        side=dict(outline=side, leads=[tail_s], features=[
            {"kind": "thin", "pts": lens(36, 150, 6, 12), "sw": 1.5},
            {"kind": "open", "pts": [(-6, 187), (6, 187), (0, 181)][::-1] and [(-6, 185), (6, 185), (0, 191)], "sw": 1, "name": "vent"}],
            mosaic=("voronoi", 30, 3), open_share=0.55),
        top=dict(outline=ellipse_quarters(71, 56, 73), features=[
            {"kind": "open", "pts": [(-14, -2), (14, -2), (14, 2), (-14, 2)], "name": "ridge vent"},
            {"kind": "thin", "pts": [(28, -6), (44, 0), (28, 8)]}, {"kind": "thin", "pts": [(-28, -6), (-44, 0), (-28, 8)]}],
            rib_r=60),
    )


def ellipse_quarters(rx, ry_front, ry_back, n=72):
    """Top outline: half-ellipse to the front (y<0 drawn down = front), another to the back."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        ry = ry_front if math.sin(a) < 0 else ry_back
        pts.append((rx * math.cos(a), ry * math.sin(a)))
    return pts


def concept_head():
    half = [(58, 0), (63, 16), (71, 42), (76, 70), (77, 95), (75, 118), (70, 138), (60, 200), (50, 172),
            (30, 167), (0, 170)]
    front = profile(half, corners=(6, 7, 8))
    sideh = [(56, 0), (61, 20), (66, 48), (68, 82), (63, 110), (48, 132), (30, 150), (16, 166), (6, 200),
             (-4, 172), (-8, 168)]
    side = poly_smooth([*sideh, *[(-x, z) for x, z in reversed(sideh[:7])]], corners=(0, 7, 8, 9, 10, 17))
    feats = eye_pair(28, 112, 30, 14, slant=18) + [
        {"kind": "thin", "pts": [(-8, 94), (8, 94), (0, 85)], "sw": 1.8, "name": "nose"},
        {"kind": "line", "pts": [(0, 85), (0, 78)], "sw": 1.6},
        {"kind": "line", "pts": [(0, 78), (-9, 72), (-17, 76)], "sw": 1.6},
        {"kind": "line", "pts": [(0, 78), (9, 72), (17, 76)], "sw": 1.6},
        {"kind": "thin", "pts": [(55, 150), (60, 188), (49, 168)], "sw": 1.5, "cut": True},
        {"kind": "thin", "pts": [(-55, 150), (-60, 188), (-49, 168)], "sw": 1.5, "cut": True},
    ]
    for s in (1, -1):
        for k, (x, z) in enumerate([(30, 88), (42, 86), (54, 84), (32, 76), (44, 72), (56, 68)]):
            feats.append({"kind": "open", "pts": teardrop(s * x, z, 2.4), "sw": 0.8, "name": "whisker hole"})
    leads = [[(0, 160), (0, 132)], [(-10, 158), (-7, 136)], [(10, 158), (7, 136)],
             [(-20, 156), (-14, 138)], [(20, 156), (14, 138)],
             catmull([(-76, 72), (-60, 56), (-36, 46), (-14, 50), (0, 60)], n=8),
             catmull([(76, 72), (60, 56), (36, 46), (14, 50), (0, 60)], n=8),
             catmull([(-60, 6), (-30, 24), (0, 30), (30, 24), (60, 6)], n=8)]
    return dict(
        key="head-lantern", name="Cat-head lantern",
        tagline="The whole shade is one big round cat head. Glowing slanted eyes with open slit pupils, whisker holes, ears on top.",
        access="hand from below through the neck opening and the rib gaps",
        front=dict(outline=front, features=feats, leads=leads, mosaic=("none", 0, 0)),
        side=dict(outline=side, features=[{"kind": "open", "pts": [(-5, 160), (5, 160), (0, 170)], "name": "vent"}],
                  leads=[catmull([(-66, 60), (0, 66), (66, 60)], n=6), catmull([(-58, 8), (0, 26), (58, 8)], n=6),
                         catmull([(10, 150), (0, 140), (-10, 150)], n=4)],
                  mosaic=("bands", [(0, 26), (26, 64), (64, 120), (120, 175)], 0)),
        top=dict(outline=ellipse_quarters(77, 68, 68), features=[
            {"kind": "thin", "pts": [(46, -8), (64, 0), (46, 8)]}, {"kind": "thin", "pts": [(-46, -8), (-64, 0), (-46, 8)]},
            {"kind": "open", "pts": [(-14, -4), (14, -4), (14, 4), (-14, 4)], "name": "ridge vent"}], rib_r=70),
    )


def concept_lowpoly():
    half = [(64, 0), (71, 38), (62, 78), (44, 110), (52, 132), (55, 158), (51, 171), (42, 200), (25, 182), (0, 186)]
    front = mirror(half)
    sideo = [(50, 0), (55, 40), (47, 80), (37, 112), (46, 133), (45, 158), (31, 178), (21, 200), (7, 186),
             (-10, 186), (-28, 170), (-40, 150), (-38, 128), (-48, 104), (-64, 64), (-70, 24), (-68, 0)]
    feats = [{"kind": "thin", "pts": [(10, 146), (28, 154), (24, 142)], "sw": 1.6},
             {"kind": "thin", "pts": [(-10, 146), (-28, 154), (-24, 142)], "sw": 1.6},
             {"kind": "open", "pts": lens(20, 148, 3.2, 9), "sw": 1, "name": "pupil"},
             {"kind": "open", "pts": lens(-20, 148, 3.2, 9), "sw": 1, "name": "pupil"},
             {"kind": "solid", "pts": [(-5, 136), (5, 136), (0, 130)], "sw": 1.2}]
    extra = [(0, 118), (0, 160), (30, 130), (-30, 130), (20, 172), (-20, 172), (0, 60), (36, 40), (-36, 40)]
    return dict(
        key="low-poly", name="Low-poly faceted cat",
        tagline="Sitting cat made of flat triangles: every edge is a rib. Triangles with a point on top can be open. Head lifts off.",
        access="lift the head off (seat at z 118, opening ~Ø85), or from below",
        front=dict(outline=front, features=feats, mosaic=("tri", 22, 11), tri_extra=extra, open_share=0.45,
                   split_z=118, open_zmax=200),
        side=dict(outline=sideo, mosaic=("tri", 20, 5), tri_extra=[(0, 118), (-20, 60), (20, 150)], open_share=0.45,
                  split_z=118, features=[{"kind": "thin", "pts": [(30, 146), (40, 152), (40, 142)], "sw": 1.5}]),
        top=dict(outline=[(0, -55), (40, -46), (67, -18), (70, 20), (52, 52), (18, 70), (-18, 70), (-52, 52),
                          (-70, 20), (-67, -18), (-40, -46)],
                 features=[{"kind": "line", "pts": [(-44, 0), (44, 0)], "sw": 1.4},
                           {"kind": "thin", "pts": [(26, -6), (42, 0), (26, 8)]}, {"kind": "thin", "pts": [(-26, -6), (-42, 0), (-26, 8)]}],
                 rib_r=58),
    )


def concept_gothic():
    R = 75.0
    rf = R * math.cos(math.radians(22.5))
    body_top, roof_top = 128.0, 186.0
    slope = (roof_top - body_top) / (rf - 20)
    def front_outline(ear_x):
        e = [(-rf, 0), (rf, 0), (rf, body_top), (ear_x + 12, body_top + slope * (rf - ear_x - 12)),
             (ear_x + 4, 200), (ear_x - 14, body_top + slope * (rf - ear_x + 14)),
             (20, roof_top), (-20, roof_top), (-(ear_x - 14), body_top + slope * (rf - ear_x + 14)),
             (-(ear_x + 4), 200), (-(ear_x + 12), body_top + slope * (rf - ear_x - 12)), (-rf, body_top)]
        return e
    front = front_outline(46)
    half_face = R * math.sin(math.radians(22.5))  # half width of the front face
    feats = []
    for cx, w in ((0, 40), (-(half_face + rf) / 2 - 1, 22), ((half_face + rf) / 2 + 1, 22)):
        arch = gothic_arch(cx, 18, w, 96)
        feats.append({"kind": "thin", "pts": arch, "sw": 2.6})
        if w > 30:
            feats.append({"kind": "open", "pts": cat_cutout(cx, 30, 1.45), "sw": 1.4, "name": "cat cut-out"})
        else:
            feats.append({"kind": "open", "pts": gothic_arch(cx, 70, 8, 30), "sw": 1.2, "name": "slot"})
    feats += eye_pair(17, 152, 16, 8, slant=15)
    feats += [{"kind": "solid", "pts": [(-4, 141), (4, 141), (0, 136)], "sw": 1.2}]
    leads = [[(-half_face, 0), (-half_face, body_top)], [(half_face, 0), (half_face, body_top)],
             [(-rf, 10), (rf, 10)], [(-rf, body_top - 6), (rf, body_top - 6)]]
    side_feats = []
    for cx, w in ((0, 40), (-(half_face + rf) / 2 - 1, 22), ((half_face + rf) / 2 + 1, 22)):
        side_feats.append({"kind": "thin", "pts": gothic_arch(cx, 18, w, 96), "sw": 2.6})
        if w > 30:
            side_feats.append({"kind": "open", "pts": cat_cutout(cx, 30, 1.45), "sw": 1.4, "name": "cat cut-out"})
        else:
            side_feats.append({"kind": "open", "pts": gothic_arch(cx, 70, 8, 30), "sw": 1.2})
    side = [(-rf, 0), (rf, 0), (rf, body_top), (20, roof_top), (8, roof_top), (4, 200), (-6, roof_top + 2),
            (-20, roof_top), (-rf, body_top)]
    oct_pts = [(R * math.cos(math.radians(22.5 + 45 * k)), R * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
    return dict(
        key="gothic-lantern", name="Gothic lantern with cat windows",
        tagline="Eight-sided lantern with pointed-arch windows; a sitting cat is cut out of each big window. The roof is the cat's head and lifts off.",
        access="lift the roof cap off (seat at z 128, opening Ø133)",
        front=dict(outline=front, features=feats, leads=leads, mosaic=("none", 0, 0), split_z=body_top),
        side=dict(outline=side, features=side_feats, leads=leads, mosaic=("none", 0, 0), split_z=body_top),
        top=dict(outline=oct_pts, features=[
            {"kind": "line", "pts": [(oct_pts[k][0] * 0.29, oct_pts[k][1] * 0.29), oct_pts[k]], "sw": 1.0} for k in range(8)] + [
            {"kind": "open", "pts": [(o[0] * 0.27, o[1] * 0.27) for o in oct_pts], "name": "top vent"},
            {"kind": "thin", "pts": [(36, -16), (52, -24), (54, -6)]}, {"kind": "thin", "pts": [(-36, -16), (-52, -24), (-54, -6)]}],
            rib_r=66),
    )


def concept_backtoback():
    half = [(70, 0), (74, 20), (72, 46), (64, 80), (58, 104), (62, 120), (70, 138), (69, 150), (64, 162),
            (60, 174), (57, 200), (47, 184), (40, 196), (31, 178), (22, 166), (12, 156), (0, 152)]
    front = profile(half, corners=(9, 10, 11, 12, 13))
    sh = [(50, 0), (55, 25), (54, 60), (47, 95), (37, 120), (30, 133), (36, 145), (38, 160), (36, 172),
          (31, 200), (16, 183), (0, 186)]
    side = profile(sh, corners=(8, 9, 10))
    tails = [catmull([(66, 4), (40, 14), (18, 30), (8, 52), (16, 64), (26, 58)], n=8),
             catmull([(-66, 4), (-40, 14), (-18, 30), (-8, 52), (-16, 64), (-26, 58)], n=8),
             [(0, 70), (0, 152)]]
    feats = []
    for s in (1, -1):
        feats.append({"kind": "thin", "pts": lens(s * 58, 152, 6, 12), "sw": 1.5})
        feats.append({"kind": "open", "pts": lens(s * 58, 152, 1.8, 10), "sw": 0.8, "name": "pupil"})
        feats.append({"kind": "thin", "pts": [(s * 51, 180), (s * 56, 196), (s * 48, 186)], "sw": 1, "cut": True})
    sfeats = eye_pair(16, 156, 15, 8, slant=12) + [{"kind": "solid", "pts": [(-4, 146), (4, 146), (0, 141)], "sw": 1.2}]
    return dict(
        key="back-to-back", name="Two cats back to back",
        tagline="Two sitting cats lean back to back. From the front you see two profiles; from the side, a cat face. Tails curl to meet.",
        access="hand from below, through 3 gaps of ~35-40 mm beside the ring",
        front=dict(outline=front, features=feats, leads=tails, mosaic=("voronoi", 30, 21), open_share=0.55,
                   mosaic_clip=[(-90, 0), (90, 0), (90, 130), (-90, 130)]),
        side=dict(outline=side, features=sfeats, mosaic=("voronoi", 20, 8), open_share=0.55,
                  mosaic_clip=[(-90, 0), (90, 0), (90, 128), (-90, 128)]),
        top=dict(outline=[(x, y) for x, y in peanut()], features=[
            {"kind": "open", "pts": [(-4, -14), (4, -14), (4, 14), (-4, 14)], "name": "valley vent"},
            {"kind": "thin", "pts": [(50, -18), (62, -12), (52, -8)]}, {"kind": "thin", "pts": [(-50, -18), (-62, -12), (-52, -8)]},
            {"kind": "thin", "pts": [(50, 18), (62, 12), (52, 8)]}, {"kind": "thin", "pts": [(-50, 18), (-62, 12), (-52, 8)]}],
            rib_r=62),
    )


def peanut(n=90):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        r = 1.0 - 0.13 * math.cos(a) ** 2 * 0 + 0.0
        x = 74 * math.cos(a)
        y = 55 * math.sin(a) * (1 - 0.18 * math.exp(-(x / 22) ** 2))
        pts.append((x, y))
    return pts


CONCEPTS = [concept_sitting, concept_head, concept_lowpoly, concept_gothic, concept_backtoback]


def main():
    OUT.mkdir(exist_ok=True)
    for i, fn in enumerate(CONCEPTS, 1):
        c = fn()
        svg, checks, rmax = render(c, i)
        path = OUT / f"concept-{i}-{c['key']}.svg"
        path.write_text(svg, encoding="utf-8")
        print(f"{path.name}: " + ", ".join(f"{n} overhang {w:.0f}°" for n, w in checks) + f", top Ø{2 * rmax:.0f}")


if __name__ == "__main__":
    main()
