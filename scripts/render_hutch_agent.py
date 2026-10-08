#!/usr/bin/env python3
"""Render the hutch hero agent — a 3D derivative of the user-supplied FF avatar.

Real Blender render (bpy wheel, isolated venv — NOT a project dependency):
    uv venv ~/.cache/bpyenv/venv --python 3.11
    uv pip install bpy --python ~/.cache/bpyenv/venv/bin/python

Usage:
    venv/bin/python scripts/render_hutch_agent.py --palette blue --preview \
        --out /tmp/opencode/agent-preview.png
    venv/bin/python scripts/render_hutch_agent.py --palette blue --grid \
        --outdir /tmp/opencode/agent-frames

--grid renders a 7x3 rotation grid (yaw -18..18deg, pitch -8..8deg) of the
rig parented to an empty, from a fixed camera. The website maps desktop
pointer position to the nearest frame, so the agent appears to look at the
cursor. Native alpha (transparent film); no chroma keying.
"""
import argparse
import math
import sys

import bpy


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def link(obj):
    bpy.context.collection.objects.link(obj)
    return obj


def sphere(name, loc, scale, seg=48, ring=24):
    import bmesh
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.scale = scale
    for p in mesh.polygons:
        p.use_smooth = True
    return link(obj)


def rounded_panel(name, loc, scale, rot=(0, 0, 0), bevel=0.45):
    import bmesh
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)  # +/- 1 local
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel,
                    segments=10, affect="EDGES", profile=0.5)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = rot
    obj.scale = scale
    for p in mesh.polygons:
        p.use_smooth = True
    return link(obj)


def arc(name, center_x, center_z, radius, a0, a1, bevel, y, segs=48):
    """Emissive arc in the X-Z plane facing the camera (camera sits at -Y).
    30..150 -> inverted-U happy eye; -150..-30 -> smile."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = 6
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(segs)
    for i in range(segs + 1):
        t = math.radians(a0 + (a1 - a0) * i / segs)
        sp.points[i].co = (math.cos(t) * radius, 0, math.sin(t) * radius, 1)
    obj = bpy.data.objects.new(name, cu)
    obj.location = (center_x, y, center_z)
    return link(obj)


def torus(name, loc, major, minor, scale_y=1.0, segs=72, sides=14):
    import bmesh
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    grid = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        ring = []
        for j in range(sides):
            b = 2 * math.pi * j / sides
            ring.append(bm.verts.new((
                (major + minor * math.cos(b)) * math.cos(a),
                (major + minor * math.cos(b)) * math.sin(a),
                minor * math.sin(b),
            )))
        grid.append(ring)
    for i in range(segs):
        for j in range(sides):
            bm.faces.new((grid[i][j], grid[(i + 1) % segs][j],
                          grid[(i + 1) % segs][(j + 1) % sides], grid[i][(j + 1) % sides]))
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.scale = (1, scale_y, 1)
    for p in mesh.polygons:
        p.use_smooth = True
    return link(obj)


def principled(name, color, rough=0.32, metallic=0.0, coat=0.4):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    for key in ("Coat Weight", "Clearcoat"):
        if key in b.inputs:
            b.inputs[key].default_value = coat
            break
    return mat


def emissive(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


PALETTES = {
    "blue": {
        "body": (0.030, 0.112, 0.78),
        "cap": (0.020, 0.075, 0.55),
        "flipper": (0.026, 0.098, 0.68),
        "panel": (0.006, 0.011, 0.024),
        "face": (0.90, 0.96, 1.0),
        "glow": (0.55, 0.75, 1.0),
        "core": (0.75, 0.87, 1.0),
    },
    "emerald": {
        "body": (0.016, 0.372, 0.255),
        "cap": (0.011, 0.26, 0.19),
        "flipper": (0.014, 0.33, 0.23),
        "panel": (0.005, 0.015, 0.012),
        "face": (0.92, 0.99, 0.95),
        "glow": (0.42, 1.0, 0.72),
        "core": (0.9, 1.0, 0.95),
    },
}

YAWS = [-18, -12, -6, 0, 6, 12, 18]
PITCHES = [-8, 0, 8]


def build(pal):
    clear()
    scene = bpy.context.scene

    m_body = principled("body", pal["body"], rough=0.24, coat=0.6)
    m_cap = principled("cap", pal["cap"], rough=0.30, coat=0.5)
    m_flip = principled("flipper", pal["flipper"], rough=0.26, coat=0.55)
    m_glass = principled("visor", pal["panel"], rough=0.06, coat=1.0)
    m_face = emissive("face", pal["face"], 16.0)
    m_glow = emissive("glow", pal["glow"], 24.0)
    m_core = emissive("core", pal["core"], 1.9)

    def assign(obj, mat):
        obj.data.materials.clear()
        obj.data.materials.append(mat)

    # rig root: whole-agent rotation; head group: visor/cap/face turn around the neck
    rig = bpy.data.objects.new("rig", None)
    rig.location = (0, 0, 0)
    link(rig)
    head = bpy.data.objects.new("head", None)
    head.location = (0, 0.02, 1.16)
    link(head)
    head.parent = rig

    parts = []

    def reg(obj, mat, headgroup=False):
        assign(obj, mat)
        if headgroup:
            obj.parent = head
            obj.location = (obj.location.x, obj.location.y - head.location.y,
                            obj.location.z - head.location.z)
        else:
            obj.parent = rig
        parts.append(obj)
        return obj

    reg(sphere("body", (0, 0, 0), (1.10, 0.97, 1.55), 64, 32), m_body)
    reg(torus("band", (0, 0, 1.42), 0.60, 0.045, scale_y=0.88), m_glow, True)
    reg(sphere("cap", (0, 0.02, 1.62), (0.62, 0.58, 0.34)), m_cap, True)
    reg(sphere("tip", (0, 0.02, 1.88), (0.26, 0.25, 0.16)), m_cap, True)
    for sx in (-1, 1):
        f = sphere(f"flipper{sx}", (sx * 1.16, 0.04, 0.18), (0.15, 0.30, 0.52))
        f.rotation_euler = (0, math.radians(-sx * 16), 0)
        reg(f, m_flip)
    reg(rounded_panel("visor", (0, -0.90, 0.72), (0.78, 0.22, 0.50),
                      rot=(math.radians(-6), 0, 0)), m_glass, True)
    y_face = -1.18
    reg(arc("eye_l", -0.30, 0.92, 0.155, 30, 150, 0.026, y_face), m_face, True)
    reg(arc("eye_r", 0.30, 0.92, 0.155, 30, 150, 0.026, y_face), m_face, True)
    reg(arc("mouth", 0.0, 0.60, 0.10, -150, -30, 0.022, y_face), m_face, True)
    reg(rounded_panel("core", (0, -0.84, -0.46), (0.30, 0.10, 0.44),
                      rot=(math.radians(8), 0, 0), bevel=0.5), m_core)
    reg(sphere("foot", (0, 0.04, -1.62), (0.52, 0.50, 0.30)), m_cap)
    reg(torus("footring", (0, 0.02, -1.46), 0.44, 0.028, scale_y=0.95), m_glow)

    def area(name, loc, energy, color, size=5.0, aim_to=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.size = size
        ld.energy = energy
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        if aim_to is not None:
            d = bpy.data.objects.new("aim", None)
            d.location = aim_to
            link(d)
            c = lo.constraints.new("TRACK_TO")
            c.target = d
            c.track_axis = "TRACK_NEGATIVE_Z"
            c.up_axis = "UP_Y"
        scene.collection.objects.link(lo)

    area("key", (-3.6, -5.2, 4.6), 1300, (1.0, 0.97, 0.92), 5.0, (0, 0, 0.6))
    area("fill", (4.6, -4.4, 0.4), 340, (0.85, 0.92, 1.0), 6.0, (0, 0, 0))
    area("rim", (0.6, 5.6, 3.2), 900, (0.75, 0.86, 1.0), 4.0, (0, 0, 0.8))

    world = bpy.data.worlds.new("world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.010, 0.016, 0.030, 1)

    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 68
    cam = bpy.data.objects.new("cam", cam_d)
    cam.location = (0, -9.6, -0.02)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = True
    scene.render.film_transparent = True
    scene.render.resolution_x = 880
    scene.render.resolution_y = 1060
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    # no compositor: Blender 5.0 headless compositor groups are brittle;
    # emissive bloom is added in post by the webp conversion (magick).

    return scene, rig, head


def render_still(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--palette", choices=list(PALETTES), default="blue")
    ap.add_argument("--out")
    ap.add_argument("--preview", action="store_true", help="single front-facing frame")
    ap.add_argument("--grid", action="store_true", help="7x3 look-at-cursor frames")
    ap.add_argument("--outdir")
    args = ap.parse_args()
    scene, rig, head = build(PALETTES[args.palette])

    if args.preview or args.out:
        rig.rotation_euler = (0, 0, 0)
        head.rotation_euler = (0, 0, 0)
        render_still(scene, args.out or "/tmp/agent-preview.png")
    if args.grid:
        outdir = args.outdir or "/tmp/agent-frames"
        import os
        os.makedirs(outdir, exist_ok=True)
        for py, yaw in enumerate(YAWS):
            for px, pitch in enumerate(PITCHES):
                # body follows gently; the head group turns most of the way
                rig.rotation_euler = (math.radians(pitch * 0.32), math.radians(-yaw * 0.34), 0)
                head.rotation_euler = (math.radians(pitch * 0.72), math.radians(-yaw * 0.72), 0)
                render_still(scene, f"{outdir}/f{py}-p{px}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
