#!/usr/bin/env python3
"""Realistic lit renders of the cat shade on the lamp's black ceramic base (Blender Cycles).

Run:  python3 cad/render_lit.py [--quick] [--only NAME]
Out:  cad/renders/lit_<name>.png
Needs: bpy (Blender as a Python module, `pip install bpy`), and the STL files from cad/cat_shade.py.

The white shade is modelled as a light-scattering plastic (random-walk subsurface scattering),
so the glow depends on the real wall thickness: 0.7 mm features glow most, 1.0 mm panels glow,
the 3.4 mm ribs stay darker. This is a physically based estimate, not a photo: the real glow
depends on the filament and the print settings.
"""
import math
import pathlib
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "renders"
MM = 0.001

# Lamp base, estimated from the owner's photo (mm, shade coordinates: z = 0 is the cat's lower edge)
EGG_D, EGG_H = 105.0, 120.0
EGG_TOP = -15.0
SHOULDER_Z = 54.4          # adapter bottom = socket shoulder (cat_shade.adapter_z0)
BULB_D, BULB_L, BULB_Z0 = 45.0, 70.0, 75.0
TABLE_Z = EGG_TOP - EGG_H

QUICK = "--quick" in sys.argv
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None


def material(name, color, rough=0.5, metal=0.0, coat=0.0, sss=None, emit=None, emit_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    if sss:
        b.subsurface_method = "RANDOM_WALK"
        b.inputs["Subsurface Weight"].default_value = 1.0
        b.inputs["Subsurface Radius"].default_value = sss[0]
        b.inputs["Subsurface Scale"].default_value = sss[1]
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = emit_strength
    return m


def blackbody(k):
    """Approximate sRGB-linear colour of a black body (enough for 2700 K warm white)."""
    t = k / 100.0
    r = 255.0 if t <= 66 else 329.7 * (t - 60) ** -0.1332
    g = 99.47 * math.log(t) - 161.12 if t <= 66 else 288.1 * (t - 60) ** -0.0755
    b = 0.0 if t <= 19 else (255.0 if t >= 66 else 138.5 * math.log(t - 10) - 305.0)
    return tuple(max(0.0, min(1.0, c / 255.0)) ** 2.2 for c in (r, g, b))


def add_stl(path, mat):
    bpy.ops.wm.stl_import(filepath=str(path))
    ob = bpy.context.selected_objects[0]
    ob.scale = (MM, MM, MM)
    ob.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
    except Exception:
        pass
    return ob


def ellipsoid(name, rx, rz, z_center, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=1.0, location=(0, 0, z_center * MM))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (rx * MM, rx * MM, rz * MM)
    bpy.ops.object.shade_smooth()
    ob.data.materials.append(mat)
    return ob


def build_scene(evening):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 24 if QUICK else 160
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 12
    sc.cycles.transmission_bounces = 12
    sc.render.resolution_x, sc.render.resolution_y = (400, 500) if QUICK else (1000, 1250)
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = -1.8
    warm = blackbody(2700)

    world = bpy.data.worlds.new("world")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.02, 0.025, 1) if evening else (0.001, 0.001, 0.0012, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0

    petg = material("PETG white", (0.93, 0.91, 0.87), rough=0.4,
                    sss=((1.0, 0.8, 0.6), 0.9 * MM))
    for part in ("body", "head", "adapter"):
        add_stl(ROOT / "out" / f"cat_shade_{part}.stl", petg)
    # adapter STL is stored flat on z = 0: move it up to the shoulder
    bpy.data.objects["cat_shade_adapter"].location.z = SHOULDER_Z * MM

    ceramic = material("black ceramic", (0.006, 0.006, 0.007), rough=0.08, coat=1.0)
    ellipsoid("egg", EGG_D / 2, EGG_H / 2, EGG_TOP - EGG_H / 2, ceramic)
    plastic = material("socket", (0.02, 0.02, 0.02), rough=0.35)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=15 * MM, depth=(SHOULDER_Z - EGG_TOP + 3) * MM,
                                        location=(0, 0, (SHOULDER_Z + EGG_TOP - 3) / 2 * MM))
    bpy.context.active_object.data.materials.append(plastic)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=13.6 * MM, depth=16 * MM,
                                        location=(0, 0, (SHOULDER_Z + 8) * MM))
    bpy.context.active_object.data.materials.append(plastic)

    # bulb: frosted glass globe that glows
    glass = material("bulb", (1, 1, 1), rough=0.3, emit=warm, emit_strength=60.0)
    ellipsoid("bulb", BULB_D / 2, BULB_L / 2, BULB_Z0 + BULB_L / 2, glass)
    bpy.ops.object.light_add(type="POINT", location=(0, 0, (BULB_Z0 + BULB_L / 2) * MM))
    bulb_light = bpy.context.active_object
    bulb_light.data.energy = 30.0
    bulb_light.data.shadow_soft_size = 20 * MM
    bulb_light.data.color = warm

    lacquer = material("red lacquer", (0.42, 0.02, 0.018), rough=0.22, coat=0.6)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 40 * MM, (TABLE_Z - 15) * MM))
    tb = bpy.context.active_object
    tb.scale = (700 * MM, 420 * MM, 30 * MM)
    tb.data.materials.append(lacquer)
    wallm = material("wall", (0.78, 0.77, 0.74), rough=0.9)
    bpy.ops.mesh.primitive_plane_add(size=3, location=(0, 250 * MM, 0.4), rotation=(math.radians(90), 0, 0))
    bpy.context.active_object.data.materials.append(wallm)

    if evening:
        bpy.ops.object.light_add(type="AREA", location=(-0.9, -0.6, 1.1))
        room = bpy.context.active_object
        room.data.energy = 60.0
        room.data.size = 1.2
        room.data.color = blackbody(3000)
        room.rotation_euler = (math.radians(50), 0, math.radians(-55))
    return sc


def camera(sc, loc, target, lens):
    bpy.ops.object.camera_add(location=tuple(v * MM for v in loc))
    cam = bpy.context.active_object
    cam.data.lens = lens
    d = [t - l for t, l in zip(target, loc)]
    cam.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)
    sc.camera = cam


SHOTS = {
    "night_front": dict(evening=False, loc=(420, -880, 120), target=(0, 0, 45), lens=68),
    "night_side": dict(evening=False, loc=(940, -120, 60), target=(0, 0, 45), lens=68),
    "evening_front": dict(evening=True, loc=(420, -880, 120), target=(0, 0, 45), lens=68),
}


def main():
    OUT.mkdir(exist_ok=True)
    for name, s in SHOTS.items():
        if ONLY and name != ONLY:
            continue
        sc = build_scene(s["evening"])
        camera(sc, s["loc"], s["target"], s["lens"])
        sc.render.filepath = str(OUT / (f"lit_{name}_quick.png" if QUICK else f"lit_{name}.png"))
        bpy.ops.render.render(write_still=True)
        print("wrote", sc.render.filepath, flush=True)


if __name__ == "__main__":
    main()
