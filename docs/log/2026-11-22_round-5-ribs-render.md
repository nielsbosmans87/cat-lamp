# Round 5: spoke ribs, lit renders

**Role(s):** 3D design, mechanical engineering

- Owner feared the thin 45-degree spokes in the bowl would sag. Each spoke now has a triangular rib below it that
  starts on the build plate at the wall and narrows towards the ring (4.0 mm to 2.4 mm thick, edge at most 42.4 degrees).
- Checks: all parts valid, no new overhang spots, adapter still free of the body.
- New `cad/render_lit.py`: Blender Cycles renders of the cat on the black ceramic base (base size estimated from the
  owner's photo). The shade is modelled as light-scattering white plastic, so thin panels glow more than ribs.
