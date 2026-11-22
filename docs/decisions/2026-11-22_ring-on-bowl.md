# Mounting ring on a 45-degree bowl, head lifts off

**Status:** accepted, 2026-11-22

## Context

The mounting ring (Ø47 / Ø28, top face at 67 mm) floats inside the body. It must print without supports.
With three or six ribs, the lowest layer of the ring hangs in the air between the ribs.

## Decision

- The ring has a flat top for the nut and a 45-degree cone underneath. The cone continues as a thin
  (1.2 mm) bowl that meets the inside wall between 2 and 22 mm height. Every layer then rests on the one below.
- The bowl closes the bottom, so the hand reaches the bulb and the ring nut from the top: the head lifts off
  at 140 mm. A lip on the body (6 mm high, 0.4 mm gap) locates the head.
- Update (round 4): a separate adapter ring (Ø40 / Ø28, printed flat) sits between the socket shoulder and the
  cone. Its flat bottom rests on the shoulder; its 45-degree top fits under the shade cone with 0.1 mm play.
  So the mount has a flat face on both sides: the shade ring's top for the nut, the adapter's bottom for the shoulder.
  Stack on the thread: 12.6 mm.
- Update (round 4): the bowl has 24 light windows between 3 mm radial spokes. Each window has a pointed inner end
  (half-width grows 0.25 mm per mm of radius), so the bowl still prints without supports.
- Update (round 5): thin 45-degree spokes could sag while printing. Under each spoke there is now a triangular rib
  in the radial plane. It starts on the build plate at the inside wall and rises in a straight edge to the ring
  (at most 42.4 degrees from vertical). It is 4.0 mm thick at the bottom and 2.4 mm at the ring. Every layer of
  the bowl now rests on a rib or on the layer below.

## Consequences

- Light goes down through the bowl windows. Air comes in there and leaves through the ridge vent.
- Changing the bulb always means lifting the head first.
