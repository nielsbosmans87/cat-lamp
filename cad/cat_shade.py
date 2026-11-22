#!/usr/bin/env python3
"""Cat lamp shade, concept 1C "Happy cat with heart": parametric 3D model.

Run:  python3 cad/cat_shade.py
Out:  cad/out/cat_shade_body.stl, cad/out/cat_shade_head.stl, cad/out/pattern.svg

Two parts, both printed upright without supports:
- body (0 to 140 mm): stained-glass mosaic, heart on the chest, paws, tail, mounting ring on a 45-degree bowl.
- head (140 to 250 mm): lift-off head with happy closed eyes, ears and a ridge vent.

How the pattern works: every pattern is drawn in an unwrapped (u, z) plane (u = arc length on a
reference cylinder of radius RREF, u = 0 is the front). Each pattern shape becomes a radial wedge
that cuts the shell. Lead ribs keep the full wall WALL and stand EMBOSS proud on the outside.
Panels are thinned to SKIN from the inside. Open panels are cut through and have pointed tops.
Steps between thicknesses are made in 0.3 mm stages, so every ledge stays within 45 degrees.
Needs: numpy, shapely, scipy, manifold3d, trimesh.
"""
import math
import pathlib
import random
import sys

import numpy as np
import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union

import manifold3d as m3
from manifold3d import CrossSection, Manifold, Mesh

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "out"
sys.path.insert(0, str(ROOT.parent / "tools"))
import sketch as sk  # noqa: E402  (catmull, lens, teardrop helpers)

# ---- Parameters (mm) ---------------------------------------------------------------------
H = 250.0            # total height, ear tips
ENV_R = 80.0         # must fit in a cylinder of this radius (Ø160)
NECK = 140.0         # joint between body and head
RING_Z = 67.0        # top face of the mounting ring
RING_OD, RING_ID, RING_T = 47.0, 28.0, 5.0
WALL = 2.5           # lead / full wall thickness
SKIN = 1.0           # thin glowing panel thickness
EMBOSS = 0.9         # leads stand this far proud of the outside
STEP = 0.3           # max ledge width inside recesses and under embossing
STEP_DZ = 0.6        # vertical shift per step; > STEP so ledges stay within 45 degrees on sloped walls too
BOWL_T = 1.2         # normal thickness of the 45-degree bowl under the ring
LIP_H, LIP_T, LIP_GAP = 6.0, 2.2, 0.4  # locating lip on the body for the head
SUPER_N = 2.2        # cross-section shape (2 = ellipse, higher = squarer)
RREF = 60.0          # reference radius for the unwrapped pattern
U_HALF = math.pi * RREF
N_RING = 192         # points per cross-section
DZ = 0.5             # loft step
TENT = 1.6           # opening tops: dz/du of the pointed top (>= 1.28 keeps 45 degrees on the real surface)
SEED = 57

# ---- Outline profiles (from the 1C sketch, mm): (z, value) ------------------------------------
XR = [(0, 70), (22, 73), (48, 73), (72, 70), (96, 63), (116, 53), (133, 44), (139, 41.5), (152, 52.5),
      (166, 64.5), (182, 70), (199, 68), (213, 62), (222, 55), (229, 46), (234, 38), (236, 33)]
YF = [(0, 54), (25, 57), (55, 56), (85, 50), (110, 42), (128, 36.5), (139, 37), (152, 46.5), (167, 54.5),
      (182, 57), (198, 53), (212, 44), (223, 33), (231, 18), (236, 4)]
YB = [(0, 72), (15, 75), (40, 74), (70, 68), (100, 58), (124, 46), (139, 40.5), (151, 42), (165, 47),
      (182, 49), (198, 45), (213, 35), (226, 22), (236, 4)]
Z_TOP = 236.0        # top of the head shell (ears go higher)


def make_profile(pts):
    sm = sk.catmull([(v, z) for z, v in pts], n=12)
    zs = np.array([p[1] for p in sm])
    vs = np.array([p[0] for p in sm])
    order = np.argsort(zs)
    zs, vs = zs[order], vs[order]
    grid = np.arange(-2.0, Z_TOP + 0.001, 0.05)
    val = np.interp(grid, zs, vs)
    der = np.gradient(val, grid)
    return grid, val, der


PROF = {k: make_profile(p) for k, p in (("xr", XR), ("yf", YF), ("yb", YB))}


def extents(z, d=0.0):
    """Half width, front and back extent at height z, moved inward by a normal offset d
    (negative d moves outward)."""
    out = []
    for k in ("xr", "yf", "yb"):
        g, v, dv = PROF[k]
        val = np.interp(z, g, v)
        slope = np.interp(z, g, dv)
        out.append(val - d * math.sqrt(1 + slope * slope))
    return out


def check_profiles():
    """Outward-going slope must stay at or below 45 degrees (dr/dz <= 1) except at the bed."""
    worst = 0
    for k in ("xr", "yf", "yb"):
        g, v, dv = PROF[k]
        m = (g > 1) & (g < Z_TOP - 0.5)
        worst = max(worst, float(dv[m].max()))
    return math.degrees(math.atan(worst))


def ring_pts(z, d=0.0, min_e=0.35):
    xr, yf, yb = (max(e, min_e) for e in extents(z, d))
    a = np.linspace(0, 2 * np.pi, N_RING, endpoint=False)
    c, s = np.cos(a), np.sin(a)
    p = 2.0 / SUPER_N
    x = xr * np.sign(c) * np.abs(c) ** p
    y = np.sign(s) * np.abs(s) ** p * np.where(s > 0, yb, yf)
    return np.stack([x, y], axis=1)


def loft(d=0.0, z0=0.0, z1=Z_TOP, d_fn=None):
    """Closed solid between z0 and z1 whose sides follow the outline moved inward by d.
    Stops early where the shape gets thinner than 0.8 mm (closed with a flat cap)."""
    levels = list(np.arange(z0, z1 + 1e-6, DZ))
    if levels[-1] < z1 - 1e-6:
        levels.append(z1)
    rings, zs = [], []
    for z in levels:
        dd = d_fn(z) if d_fn else d
        e = extents(z, dd)
        if min(e) < 0.8 and zs:
            break
        rings.append(ring_pts(z, dd))
        zs.append(z)
    K, N = len(rings), N_RING
    verts = [np.column_stack([r, np.full(N, z)]) for r, z in zip(rings, zs)]
    verts = np.vstack(verts + [np.array([[0, 0, zs[0]], [0, 0, zs[-1]]])])
    cb, ct = K * N, K * N + 1
    tris = []
    j = np.arange(N)
    jn = (j + 1) % N
    for k in range(K - 1):
        a0, a1 = k * N + j, k * N + jn
        b0, b1 = (k + 1) * N + j, (k + 1) * N + jn
        tris.append(np.column_stack([a0, a1, b1]))
        tris.append(np.column_stack([a0, b1, b0]))
    tris.append(np.column_stack([np.full(N, cb), jn, j]))
    tris.append(np.column_stack([np.full(N, ct), (K - 1) * N + j, (K - 1) * N + jn]))
    mesh = Mesh(vert_properties=verts.astype(np.float32), tri_verts=np.vstack(tris).astype(np.uint32))
    man = Manifold(mesh)
    assert man.status() == m3.Error.NoError, man.status()
    return man


# ---- Pattern helpers (u, z plane) -------------------------------------------------------------
def x_to_u(x, z):
    """Front-view x at height z -> u on the unwrapped pattern (front half)."""
    xr, yf, _ = extents(z)
    t = min(abs(x) / xr, 0.999)
    c = t ** (SUPER_N / 2)
    s = math.sqrt(1 - c * c)
    y = -yf * s ** (2 / SUPER_N)
    th = math.atan2(y, math.copysign(xr * c ** (2 / SUPER_N), x))
    return RREF * (th + math.pi / 2)


def front_line(pts, step=1.0):
    ls = LineString(pts).segmentize(step)
    return LineString([(x_to_u(x, z), z) for x, z in ls.coords])


def front_poly(pts, step=1.0):
    pg = Polygon(pts).segmentize(step)
    return Polygon([(x_to_u(x, z), z) for x, z in pg.exterior.coords]).buffer(0)


def pointed(poly, k=TENT):
    """Cut a pointed top (slope dz/du = k) over an opening, peak at its highest point."""
    top = max(poly.exterior.coords, key=lambda q: q[1])
    tent = Polygon([(top[0] - 500, top[1] - 500 * k), (top[0], top[1]), (top[0] + 500, top[1] - 500 * k)])
    g = poly.intersection(tent)
    if g.geom_type != "Polygon":
        g = max(getattr(g, "geoms", []), key=lambda h: h.area, default=Polygon())
    return g


def lower_top(poly, dz):
    return poly.intersection(translate(poly, 0, -dz)) if dz else poly


def raise_bottom(poly, dz):
    return poly.intersection(translate(poly, 0, dz)) if dz else poly


def heart_pts(cx, cz, s):
    pts = []
    for i in range(120):
        t = 2 * math.pi * i / 120
        x = 16 * math.sin(t) ** 3
        z = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s, cz + z * s))
    return pts


def design():
    """Return pattern geometry in (u, z): leads (thick + embossed), panels (thin), openings."""
    rng = random.Random(SEED)
    lead_lines, lead_polys = [], []   # (LineString, width) and filled shapes
    # -- body mosaic ------------------------------------------------------------------------
    BZ0, BZ1 = 27.0, 133.0
    dom = box(-U_HALF, BZ0, U_HALF, BZ1)
    heart = front_poly(heart_pts(0, 86, 1.4))
    window = front_poly(sk.teardrop(0, 84, 6.0, n=24))
    keep_out = heart.buffer(4)
    seeds = []
    while len(seeds) < 48:
        p = (rng.uniform(-U_HALF, U_HALF), rng.uniform(BZ0 + 4, BZ1 - 4))
        if not keep_out.buffer(8).contains(Point(p)):
            seeds.append(p)
    allp = seeds + [(x + 2 * U_HALF, z) for x, z in seeds] + [(x - 2 * U_HALF, z) for x, z in seeds]
    cells = shapely.voronoi_polygons(MultiPoint(allp), extend_to=box(-3 * U_HALF, BZ0 - 50, 3 * U_HALF, BZ1 + 50))
    seam = unary_union([LineString([(s * U_HALF, -10), (s * U_HALF, 300)]) for s in (-1, 1)]).buffer(0.05)
    edges = []
    for c in cells.geoms:
        cc = c.intersection(dom)
        if cc.is_empty:
            continue
        for g in getattr(cc, "geoms", [cc]):
            if g.geom_type == "Polygon":
                edges.append(g.exterior.difference(seam))
    mosaic = unary_union(edges).difference(heart)  # ribs run into the heart outline
    lead_lines.append((mosaic, WALL))
    lead_lines.append((heart.exterior, WALL * 1.2))
    for z in (BZ0, BZ1):
        lead_lines.append((LineString([(-U_HALF - 1, z), (U_HALF + 1, z)]), WALL))
    # paws and tail (below the mosaic: relief only)
    for s in (1, -1):
        paw = [(s * 4, 0.5), (s * 4, 12), (s * 9, 21), (s * 17, 23), (s * 25, 20), (s * 29, 11), (s * 29, 0.5)]
        lead_lines.append((front_line(sk.catmull(paw, n=6)), 2.0))
        for xt in (12, 21):
            lead_lines.append((front_line([(s * xt, 14), (s * xt, 20.5)]), 1.4))
    tail = sk.catmull([(68, 4), (62, 12), (50, 17), (39, 16), (33, 10)], n=10)
    lead_lines.append((front_line(tail), 2.4))
    # -- head ---------------------------------------------------------------------------------
    HZ0, HZ1 = 146.0, 212.0
    hdom = box(-U_HALF, HZ0, U_HALF, HZ1)
    w = 70.0
    face = []
    for s in (1, -1):
        ex, ez = 26, 180
        face.append((sk.catmull([(s * ex - 10, ez - 3), (s * ex, ez + 6), (s * ex + 10, ez - 3)], n=8), 2.4))
        face.append((sk.catmull([(s * (w - 9), 171), (s * 30, 165), (s * 16, 150), (0, 145.5)], n=10), WALL))
        for k in range(3):
            face.append(([(s * 14, 160 + k * 3.5), (s * (w - 20), 157 + k * 7 - 4)], 1.3))
    face.append((sk.catmull([(-w + 4, 196), (-34, 203), (0, 206), (34, 203), (w - 4, 196)], n=10), WALL))
    face.append(([(0, 163.5), (0, 160)], 1.4))
    face.append((sk.catmull([(0, 160), (-4, 156.5), (-8.5, 159)], n=6), 1.4))
    face.append((sk.catmull([(0, 160), (4, 156.5), (8.5, 159)], n=6), 1.4))
    for x0 in (-7, 0, 7):
        face.append(([(x0, 220), (x0 * 0.8, 211)], 1.8))
    for pts, wd in face:
        lead_lines.append((front_line(pts), wd))
    lead_polys.append(front_poly([(-4.5, 169), (4.5, 169), (0, 162.5)]).buffer(0.6))
    # back of the head: brow ring continues round the back, plus meridians
    ub = x_to_u(w - 4, 196)
    for s in (1, -1):
        lead_lines.append((LineString([(s * ub, 196), (s * (U_HALF + 1), 196)]), WALL))
        for um in (110, 150):
            lead_lines.append((LineString([(s * um, HZ0), (s * um, HZ1)]), WALL))
    for z in (HZ0, HZ1):
        lead_lines.append((LineString([(-U_HALF - 1, z), (U_HALF + 1, z)]), WALL))

    leads = unary_union([g.buffer(wd / 2, cap_style=1, join_style=1) for g, wd in lead_lines] + lead_polys)
    panel_area = unary_union([dom.difference(heart.buffer(WALL * 0.6)), heart.buffer(-WALL * 0.6), hdom])
    panels = panel_area.difference(leads)
    panels = [g for g in getattr(panels, "geoms", [panels]) if g.area > 3]
    # -- openings: some body panels, plus the heart window ------------------------------------
    cand = []
    for g in panels:
        minx, minz, maxx, maxz = g.bounds
        if maxz > BZ1 or g.area < 60 or g.area > 900 or minx < -U_HALF + 1 or maxx > U_HALF - 1:
            continue
        if g.intersects(heart.buffer(2)):
            continue
        hole = pointed(g.buffer(-0.3, join_style=2))
        if hole.area > 45:
            cand.append(hole)
    rng.shuffle(cand)
    openings = cand[: int(len(cand) * 0.55)] + [pointed(window)]
    return leads, panels, openings, dict(body=(BZ0, BZ1), head=(HZ0, HZ1))


# ---- Pattern -> solids ------------------------------------------------------------------------
def to_cs(geom):
    polys = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and not g.is_empty]
    rings = []
    for p in polys:
        p = shapely.geometry.polygon.orient(p.segmentize(1.0), 1.0)
        rings.append(np.array(p.exterior.coords[:-1]))
        rings += [np.array(r.coords[:-1]) for r in p.interiors]
    return CrossSection(rings, m3.FillRule.EvenOdd)


def _wedge(geom, r0, r1):
    cs = to_cs(geom)
    if cs.is_empty():
        return Manifold()
    ex = Manifold.extrude(cs, 1.0)

    def f(v):
        u, z, t = v[:, 0], v[:, 1], v[:, 2]
        th = -np.pi / 2 + u / RREF
        r = r0 + t * (r1 - r0)
        return np.column_stack([r * np.cos(th), r * np.sin(th), z])
    return ex.warp_batch(f)


def wedge(geom, r0=3.0, r1=115.0):
    """Radial solid of a (u, z) shape. Built from two halves that overlap by 1 mm at the front
    and at the back seam, so the solid never touches itself where the pattern wraps round."""
    zb = (-50, 400)
    left = geom.intersection(box(-U_HALF, zb[0], 0.5, zb[1]))
    right = unary_union([geom.intersection(box(-0.5, zb[0], U_HALF, zb[1])),
                         translate(geom.intersection(box(-U_HALF, zb[0], -U_HALF + 1.0, zb[1])), 2 * U_HALF)])
    return _wedge(left, r0, r1) + _wedge(right, r0, r1)


def ear(sign, inner=False):
    """Ear as the hull of a patch of head surface and a short tip ridge. inner=True gives the hollow.
    The patch is limited so the inner edge of the ear leans out at 45 degrees at most."""
    d = WALL + 0.6 if inner else 0.4
    tip_x, tip_y = 50.0, -19.0
    pts = []
    for z in np.arange(208, 235, 1.0):
        rp = ring_pts(z, d)
        x_min = max(30.0, tip_x - (H - z) + 3.0)
        sel = (rp[:, 0] * sign >= x_min) & (rp[:, 0] * sign <= 66) & (rp[:, 1] >= -31) & (rp[:, 1] <= -7)
        for x, y in rp[sel]:
            pts.append((x, y, z))
    pts = np.array(pts)
    tip = np.array([[sign * (tip_x - 1.5), tip_y - 3.5, H], [sign * (tip_x + 1.5), tip_y + 3.5, H]])
    if inner:
        c = np.array([sign * 49.0, tip_y])
        v = pts[:, :2] - c
        n = np.linalg.norm(v, axis=1, keepdims=True)
        pts[:, :2] = c + v * np.maximum(n - WALL, 0.5) / np.maximum(n, 1e-6)
        pts[:, 2] -= 1.5
        tip = np.array([[sign * tip_x, tip_y, H - WALL * 2.6]])
    return Manifold.hull_points(np.vstack([pts, tip]))


def ring_and_bowl():
    """Mounting ring with a 45-degree cone underneath that becomes a thin bowl to the wall."""
    ri, ro = RING_ID / 2, RING_OD / 2
    zl = RING_Z - RING_T                       # underside at the hole edge
    zo = zl - (ro - ri) + BOWL_T * math.sqrt(2)  # where the bowl's upper surface leaves the ring
    R = 140.0
    prof = [(ri, zl), (ri, RING_Z), (ro, RING_Z), (ro, zo), (R, zo - (R - ro)), (R, zl - (R - ri))]
    return Manifold.revolve(CrossSection([np.array(prof)], m3.FillRule.EvenOdd), 256)


def lip_and_support():
    """Lip on the body that locates the head, carried by a 45-degree ledge on the inside."""
    a = WALL + LIP_GAP
    b = WALL + LIP_GAP + LIP_T
    lip = loft(a - 0.01, NECK - 0.2, NECK + LIP_H) - loft(b, NECK - 1, NECK + LIP_H + 1)
    z_s = NECK - 6.0

    def d_in(z):
        return min(b, WALL + max(0.0, z - z_s))
    sup = loft(WALL - 0.3, z_s, NECK) - loft(0, z_s - 1, NECK + 1, d_fn=lambda z: d_in(z) if z >= z_s else WALL)
    return lip + sup


def build():
    leads, panels, openings, doms = design()
    print(f"pattern: {len(panels)} panels, {len(openings)} openings")
    outer = loft(0.0, 0.0, Z_TOP)
    inner = loft(WALL, -1.0, Z_TOP)
    shell = (outer + ear(1) + ear(-1)) - (inner + ear(1, True) + ear(-1, True))
    # thin panels, recessed from the inside in 0.5 mm stages
    P = unary_union(panels)
    cut = Manifold()
    depths = np.arange(SKIN, WALL - 1e-6, STEP)
    for i, d in enumerate(depths):
        band = loft(d, -1.0, Z_TOP) - loft(d + STEP, -1.0, Z_TOP) if d + STEP < WALL - 1e-6 else loft(d, -1.0, Z_TOP)
        cut += wedge(lower_top(P, i * STEP_DZ)) ^ band
    shell -= cut
    # openings
    shell -= wedge(unary_union(openings))
    # embossed leads, with a stepped underside
    emb = Manifold()
    lead_area = leads.intersection(box(-U_HALF, 0.0, U_HALF, Z_TOP - 14))
    steps = np.arange(0.0, EMBOSS - 1e-6, STEP)
    for i, d in enumerate(steps):
        band = loft(-(d + STEP), 0.0, Z_TOP - 0.5) - loft(-d - 0.0, -1.0, Z_TOP)
        emb += wedge(raise_bottom(lead_area, (i + 1) * STEP_DZ)) ^ band
    emb = (emb + (wedge(lead_area) ^ loft(-0.01, 0.0, Z_TOP))) - inner
    shell += emb
    # ridge vent between the ears
    shell -= Manifold.cube([56, 5, 20], True).translate([0, 0, Z_TOP])
    body = shell.trim_by_plane([0, 0, -1], -NECK)
    head = shell.trim_by_plane([0, 0, 1], NECK)
    bowl = ring_and_bowl() ^ loft(0.4, 0.0, NECK)
    body = body + bowl + lip_and_support()
    return main_solid(body), main_solid(head), (leads, panels, openings, doms)


def main_solid(man):
    """Keep the largest connected solid; drops zero-volume slivers where pattern wedges touch."""
    parts = man.decompose()
    big = max(parts, key=lambda p: p.volume())
    dropped = sum(p.volume() for p in parts) - big.volume()
    assert dropped < 2.0, f"dropped {dropped:.1f} mm3: real pieces are loose"
    return big


# ---- Checks -----------------------------------------------------------------------------------
def to_trimesh(man):
    import trimesh
    m = man.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(m.vert_properties)[:, :3], faces=np.asarray(m.tri_verts), process=True)


def section(man, z):
    """Horizontal section of a solid as a shapely geometry (even-odd rings)."""
    rings = man.slice(float(z)).to_polygons()
    g = Polygon()
    for r in rings:
        if len(r) >= 3:
            g = g.symmetric_difference(Polygon(r).buffer(0))
    return g


def layer_check(man, z0, z1, layer=0.2):
    """Print-without-supports check: every layer must sit on the layer below, grown by one
    layer height (45 degrees). Reports material that overhangs more than about 0.6 mm."""
    zs = np.arange(z0 + layer / 2, z1, layer)
    prev, worst = None, []
    for z in zs:
        cur = section(man, z)
        if prev is not None and not cur.is_empty:
            bad = cur.difference(prev.buffer(layer + 0.02)).buffer(-0.3).buffer(0.3)
            if bad.area > 0.05:
                c = bad.centroid
                worst.append((round(float(z), 1), round(bad.area, 1), (round(c.x), round(c.y))))
        prev = cur
    return worst


def export_clean(man, path):
    """Write an STL that slicers read cleanly: simplify away sub-0.03 mm slivers, write,
    read back the float32 file and simplify once more. Returns the final solid."""
    import trimesh
    to_trimesh(man.as_original().simplify(0.03)).export(path)
    tm = trimesh.load(path)
    again = Manifold(Mesh(vert_properties=tm.vertices.astype(np.float32), tri_verts=tm.faces.astype(np.uint32)))
    final = again.simplify(0.03)
    out = to_trimesh(final)
    out.export(path)
    out.export(path.with_suffix(".3mf"))
    return final, out


def main():
    OUT.mkdir(exist_ok=True)
    print(f"profile: steepest outward slope {check_profiles():.1f} deg (limit 45)")
    body, head, pat = build()
    report = []
    for name, man in (("body", body), ("head", head)):
        man, tm = export_clean(man, OUT / f"cat_shade_{name}.stl")
        _, uses = np.unique(tm.edges_sorted, axis=0, return_counts=True)
        r = np.linalg.norm(tm.vertices[:, :2], axis=1).max()
        zmin, zmax = tm.vertices[:, 2].min(), tm.vertices[:, 2].max()
        bad = layer_check(man, zmin, zmax)
        report.append(dict(part=name, valid=str(man.status()), triangles=len(tm.faces),
                           nonmanifold_edges=int((uses != 2).sum()), volume_cm3=round(tm.volume / 1000, 1),
                           max_radius=round(float(r), 1), z=(round(float(zmin), 2), round(float(zmax), 2)),
                           overhang_spots=bad))
    for rp in report:
        print(rp)
    write_pattern_svg(*pat)
    return report


def write_pattern_svg(leads, panels, openings, doms):
    s = 2.0
    W = 2 * U_HALF * s + 40
    Hh = (H + 10) * s + 40

    def path(g):
        out = []
        for p in getattr(g, "geoms", [g]):
            if p.geom_type != "Polygon":
                continue
            for ring in [p.exterior, *p.interiors]:
                out.append("M" + " L".join(f"{20 + (x + U_HALF) * s:.1f},{20 + (H + 5 - z) * s:.1f}" for x, z in ring.coords) + " Z")
        return " ".join(out)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {Hh:.0f}" font-family="Inter, sans-serif">',
           f'<rect width="{W:.0f}" height="{Hh:.0f}" fill="#fbfaf7"/>']
    svg.append(f'<path d="{path(unary_union(panels))}" fill="#f7c46c" fill-rule="evenodd"/>')
    svg.append(f'<path d="{path(unary_union(openings))}" fill="#ffffff" stroke="#7aa7d6" stroke-width="0.8" fill-rule="evenodd"/>')
    svg.append(f'<path d="{path(leads.intersection(box(-U_HALF, 0, U_HALF, H)))}" fill="#2b2620" fill-rule="evenodd"/>')
    for z in (NECK, RING_Z):
        y = 20 + (H + 5 - z) * s
        svg.append(f'<line x1="20" x2="{W - 20:.0f}" y1="{y:.1f}" y2="{y:.1f}" stroke="#c0392b" stroke-dasharray="6 4"/>')
    for u, lab in ((0, "front"), (U_HALF / 2, "right side"), (-U_HALF / 2, "left side"), (U_HALF - 1, "back")):
        svg.append(f'<text x="{20 + (u + U_HALF) * s:.0f}" y="{Hh - 6:.0f}" font-size="14" text-anchor="middle">{lab}</text>')
    svg.append("</svg>")
    (OUT / "pattern.svg").write_text("\n".join(svg))


if __name__ == "__main__":
    main()
