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
| `.agents/` | Shared agent kit (git submodule, refaqt/refaqt-agents) |
| `docs/` | Log, decisions, mistakes |
