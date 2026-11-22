# Architecture

Short map of this repository. Update when the layout, start points, or main parts change.
Write this file in B2 English. Follow `.agents/rules/communication.md`.

## Purpose

A 3D-printed lamp shade in the shape of a cat. It replaces the fabric shade of an E14 table lamp.
Fixed requirements: 250 mm high (was 200 mm in round 1), fits in a Ø160 mm cylinder, mounting ring Ø47 / Ø28 mm, 5 mm thick,
67 mm above the lower edge, printed in white without supports.

## Repository layout

| Path | Role |
| ---- | ---- |
| `tools/sketch.py` | Makes the dimensioned concept sketches and checks overhang and size rules |
| `tools/sketch_v2.py` | Round 2 sketches: variations of concept 1, built on `tools/sketch.py` |
| `sketches/` | Concept sketches (SVG); round 2 in `sketches/round-2/` |
| `cad/cat_shade.py` | Parametric 3D model of concept 1C: builds, checks and exports both parts |
| `cad/out/` | Print files: `cat_shade_body` and `cat_shade_head` (.stl and .3mf), `pattern.svg` |
| `cad/renders/` | Review renders of the current model |
| `.agents/` | Shared agent kit (git submodule, refaqt/refaqt-agents) |
| `docs/` | Log, decisions, mistakes |

## Start points

- Change the design: edit the parameters and outline profiles at the top of `cad/cat_shade.py`,
  then run `python3 cad/cat_shade.py` (about 5 minutes). It prints the checks for both parts.
- Needs Python with numpy, shapely, scipy, manifold3d and trimesh (plus networkx and lxml for .3mf).
