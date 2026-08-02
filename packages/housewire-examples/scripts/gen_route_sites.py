#!/usr/bin/env python3
"""Generate Route_01..Route_20 example site YAML files (run from repo root)."""
from __future__ import annotations

from pathlib import Path

OUT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "housewire_examples"
    / "sites"
)


def _house(label: str, notes: str, body: str) -> str:
    # Quote scalars that may contain ':' (YAML mapping trap).
    return f"""schema: house/v2
type: House
label: {label!r}
notes: {notes!r}
elements:
{body}
view:
  physical:
    x: 0.0
    y: 0.0
    page:
      width: 640
      height: 480
"""


def route_01() -> str:
    # Same-box: two sockets, one cable (no conduit).
    return _house(
        "Route 01 — same box",
        "Single junction box, two sockets, one conductor pair (no conduit).",
        """  Box:
    type: JunctionBox
    label: Box
    openings: [N1, S1]
    opening_grid: {NS: 1, WE: 1}
    elements:
      Socket_A:
        type: Socket
        label: Socket A
        view:
          electrical: {x: 40.0, y: 40.0}
      Socket_B:
        type: Socket
        label: Socket B
        view:
          electrical: {x: 160.0, y: 40.0}
    cables:
      Link_1:
        type: Conductor
        section: 1.5 mm2
        color: BN
        from: Socket_A.N1
        to: Socket_B.N1
    view:
      physical: {x: 120.0, y: 80.0}
""",
    )


def route_02() -> str:
    return _house(
        "Route 02 — two boxes one tube",
        "Two device boxes, one conduit, one conductor.",
        """  Box_A:
    type: DeviceBox
    label: Box A
    openings: [E1]
    opening_grid: {E: 1}
    elements:
      Socket:
        type: Socket
        label: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 100.0}
  Box_B:
    type: DeviceBox
    label: Box B
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        label: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 320.0, y: 100.0}
cables:
  Run_1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Box_A/Socket.N1
    to: Box_B/Socket.N1
  Tube_1:
    type: Conduit
    subtype: tube
    from: Box_A.E1
    to: Box_B.W1
    contains: [Run_1]
    color: BK
""",
    )


def route_03() -> str:
    return _house(
        "Route 03 — twin conductors",
        "Two boxes, one conduit carrying BN+BU.",
        """  Box_A:
    type: DeviceBox
    label: Box A
    openings: [E1]
    opening_grid: {E: 1}
    elements:
      Socket:
        type: Socket
        label: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 80.0}
  Box_B:
    type: DeviceBox
    label: Box B
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        label: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 340.0, y: 80.0}
cables:
  L:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Box_A/Socket.N1
    to: Box_B/Socket.N1
  N:
    type: Conductor
    section: 1.5 mm2
    color: BU
    from: Box_A/Socket.N3
    to: Box_B/Socket.N3
  Cable:
    type: Cable
    contains: [L, N]
    color: BK
    section: 1.5 mm2
  Tube:
    type: Conduit
    subtype: tube
    from: Box_A.E1
    to: Box_B.W1
    contains: [Cable]
    color: BK
""",
    )


def route_04() -> str:
    return _house(
        "Route 04 — L shaped path",
        "Three boxes: horizontal then vertical conduit chain.",
        """  Box_A:
    type: DeviceBox
    label: A
    openings: [E1]
    opening_grid: {E: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 20.0, y: 40.0}
  Box_B:
    type: JunctionBox
    label: Bend
    openings: [W1, S1]
    opening_grid: {WE: 1, NS: 1}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 2}
        terminals:
          N1: {label: '1', direction: inout, role: phase}
          N2: {label: '2', direction: inout, role: neutral}
        view:
          electrical: {x: 60.0, y: 50.0}
    cables: {}
    view:
      physical: {x: 280.0, y: 40.0}
  Box_C:
    type: DeviceBox
    label: C
    openings: [N1]
    opening_grid: {N: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 280.0, y: 280.0}
cables:
  AB:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Box_A/Socket.N1
    to: Box_B/Strip.N1
  BC:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Box_B/Strip.N1
    to: Box_C/Socket.N1
  Tube_AB:
    type: Conduit
    subtype: tube
    from: Box_A.E1
    to: Box_B.W1
    contains: [AB]
  Tube_BC:
    type: Conduit
    subtype: tube
    from: Box_B.S1
    to: Box_C.N1
    contains: [BC]
""",
    )


def route_05() -> str:
    return _house(
        "Route 05 — switch drop",
        "Junction box to switch on east opening.",
        """  Room:
    type: Room
    label: Room
    elements:
      JBox:
        type: JunctionBox
        label: JBox
        openings: [E1, W1]
        opening_grid: {WE: 1}
        elements:
          Strip:
            type: TerminalStrip
            terminal_grid: {NS: 2}
            terminals:
              N1: {label: L, direction: inout, role: phase}
              N2: {label: Lsw, direction: inout, role: phase}
            view:
              electrical: {x: 70.0, y: 60.0}
        cables: {}
        view:
          physical: {x: 40.0, y: 40.0}
      SwitchBox:
        type: DeviceBox
        label: Switch
        openings: [W1]
        opening_grid: {W: 1}
        elements:
          Switch:
            type: Switch
            subtype: unipolar
            view:
              electrical: {x: 80.0, y: 20.0}
        cables: {}
        view:
          physical: {x: 320.0, y: 40.0}
    cables:
      Sw1:
        type: Conductor
        section: 1.5 mm2
        color: BN
        from: JBox/Strip.N1
        to: SwitchBox/Switch.N1
      Sw2:
        type: Conductor
        section: 1.5 mm2
        color: BK
        from: SwitchBox/Switch.S1
        to: JBox/Strip.N2
      SwCable:
        type: Cable
        contains: [Sw1, Sw2]
        color: BK
        section: 1.5 mm2
      Tube:
        type: Conduit
        subtype: tube
        from: JBox.E1
        to: SwitchBox.W1
        contains: [SwCable]
    view:
      physical: {x: 40.0, y: 40.0, page: {width: 480, height: 280}}
""",
    )


def route_06() -> str:
    return _house(
        "Route 06 — lamp plane boca",
        "Junction to light point via B1-1 plane opening.",
        """  Room:
    type: Room
    label: Room
    elements:
      JBox:
        type: JunctionBox
        label: JBox
        openings: [N1, E1]
        opening_grid: {NS: 1, WE: 1}
        elements:
          Strip:
            type: TerminalStrip
            terminal_grid: {NS: 3}
            terminals:
              N1: {label: L, direction: inout, role: phase}
              N2: {label: N, direction: inout, role: neutral}
              N3: {label: PE, direction: inout, role: pe}
            view:
              electrical: {x: 70.0, y: 70.0}
        cables: {}
        view:
          physical: {x: 40.0, y: 120.0}
      Lamp:
        type: LightPoint
        label: Lamp
        openings: [B1-1]
        opening_grid: {B: 1}
        elements:
          Luminaire:
            type: Luminaire
            terminal_grid: {N: 3}
            terminals:
              N1: {label: '1', direction: in, role: phase}
              N2: {label: '2', direction: in, role: earth}
              N3: {label: '3', direction: in, role: neutral}
            view:
              electrical: {x: 100.0, y: 80.0}
        cables: {}
        view:
          physical: {x: 280.0, y: 40.0}
    cables:
      Ph:
        type: Conductor
        section: 1.5 mm2
        color: BK
        from: JBox/Strip.N1
        to: Lamp/Luminaire.N1
      Nu:
        type: Conductor
        section: 1.5 mm2
        color: BU
        from: JBox/Strip.N2
        to: Lamp/Luminaire.N3
      Pe:
        type: Conductor
        section: 1.5 mm2
        color: GNYE
        from: JBox/Strip.N3
        to: Lamp/Luminaire.N2
      Cable:
        type: Cable
        contains: [Ph, Nu]
        color: WH
        section: 1.5 mm2
      Tube:
        type: Conduit
        subtype: tube
        from: JBox.N1
        to: Lamp.B1-1
        contains: [Cable, Pe]
    view:
      physical: {x: 20.0, y: 20.0, page: {width: 480, height: 320}}
""",
    )


def route_07() -> str:
    return _house(
        "Route 07 — bipolar V",
        "Two exits from one strip via distinct openings (expects V at pin).",
        """  Box_A:
    type: JunctionBox
    label: A
    openings: [E1, S1]
    opening_grid: {E: 1, S: 1}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 1}
        terminals:
          N1: {label: L, direction: inout, role: phase}
        view:
          electrical: {x: 80.0, y: 60.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 80.0}
  Box_B:
    type: DeviceBox
    label: B
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 340.0, y: 80.0}
  Box_C:
    type: DeviceBox
    label: C
    openings: [N1]
    opening_grid: {N: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 280.0}
cables:
  To_B:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Box_A/Strip.N1
    to: Box_B/Socket.N1
  To_C:
    type: Conductor
    section: 1.5 mm2
    color: BK
    from: Box_A/Strip.N1
    to: Box_C/Socket.N1
  Tube_B:
    type: Conduit
    subtype: tube
    from: Box_A.E1
    to: Box_B.W1
    contains: [To_B]
  Tube_C:
    type: Conduit
    subtype: tube
    from: Box_A.S1
    to: Box_C.N1
    contains: [To_C]
""",
    )


def route_08() -> str:
    return _house(
        "Route 08 — strip two pairs",
        "Feed BN+BU into a 2-pair terminal strip via one tube.",
        """  Panel:
    type: Panel
    label: Panel
    openings: [S1]
    opening_grid: {S: 1}
    elements:
      Supply:
        type: Supply
        view:
          electrical: {x: 40.0, y: 20.0}
    cables: {}
    view:
      physical: {x: 160.0, y: 20.0}
  Box:
    type: JunctionBox
    label: Box
    openings: [N1]
    opening_grid: {N: 1}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 2}
        terminals:
          N1: {label: L, direction: inout, role: phase}
          N2: {label: N, direction: inout, role: neutral}
        view:
          electrical: {x: 70.0, y: 70.0}
    cables: {}
    view:
      physical: {x: 160.0, y: 220.0}
cables:
  L:
    type: Conductor
    section: 2.5 mm2
    color: BN
    from: Panel/Supply.S1
    to: Box/Strip.N1
  N:
    type: Conductor
    section: 2.5 mm2
    color: BU
    from: Panel/Supply.S2
    to: Box/Strip.N2
  Cable:
    type: Cable
    contains: [L, N]
    color: BK
    section: 2.5 mm2
  Tube:
    type: Conduit
    subtype: tube
    from: Panel.S1
    to: Box.N1
    contains: [Cable]
""",
    )


def route_09() -> str:
    return _house(
        "Route 09 — strip four pairs feed",
        "Panel feed to 4-pair strip (phase, switched, neutral, PE).",
        """  Panel:
    type: Panel
    label: Panel
    openings: [S1]
    opening_grid: {S: 1}
    elements:
      Supply:
        type: Supply
        view:
          electrical: {x: 40.0, y: 20.0}
      Earth:
        type: EarthElectrode
        view:
          electrical: {x: 180.0, y: 20.0}
    cables: {}
    view:
      physical: {x: 140.0, y: 10.0}
  Box:
    type: JunctionBox
    label: Box
    openings: [N1, E1]
    opening_grid: {NS: 1, WE: 1}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 4}
        terminals:
          N1: {label: L, direction: inout, role: phase}
          N2: {label: Lsw, direction: inout, role: phase}
          N3: {label: N, direction: inout, role: neutral}
          N4: {label: PE, direction: inout, role: pe}
        view:
          electrical: {x: 70.0, y: 80.0}
    cables: {}
    view:
      physical: {x: 140.0, y: 220.0}
cables:
  L:
    type: Conductor
    section: 2.5 mm2
    color: BN
    from: Panel/Supply.S1
    to: Box/Strip.N1
  N:
    type: Conductor
    section: 2.5 mm2
    color: BU
    from: Panel/Supply.S2
    to: Box/Strip.N3
  PE:
    type: Conductor
    section: 2.5 mm2
    color: GNYE
    from: Panel/Earth.S1
    to: Box/Strip.N4
  Power:
    type: Cable
    contains: [L, N]
    color: BK
    section: 2.5 mm2
  EarthCable:
    type: Cable
    contains: [PE]
    color: BK
    section: 2.5 mm2
  Tube:
    type: Conduit
    subtype: tube
    from: Panel.S1
    to: Box.N1
    contains: [Power, EarthCable]
""",
    )


def route_10() -> str:
    # Minimal Test_01-like without room chrome
    return _house(
        "Route 10 — feed plus earth",
        "Panel supply and earth into junction strip.",
        """  Panel:
    type: Panel
    label: Panel
    openings: [S1]
    opening_grid: {S: 1}
    elements:
      Supply:
        type: Supply
        view:
          electrical: {x: 40.0, y: 20.0}
      Earth:
        type: EarthElectrode
        view:
          electrical: {x: 160.0, y: 20.0}
    cables: {}
    view:
      physical: {x: 180.0, y: 20.0}
  Box:
    type: JunctionBox
    label: Box
    openings: [N1]
    opening_grid: {N: 1}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 3}
        terminals:
          N1: {label: L, direction: inout, role: phase}
          N2: {label: N, direction: inout, role: neutral}
          N3: {label: PE, direction: inout, role: pe}
        view:
          electrical: {x: 70.0, y: 70.0}
    cables: {}
    view:
      physical: {x: 180.0, y: 240.0}
cables:
  L:
    type: Conductor
    section: 2.5 mm2
    color: BN
    from: Panel/Supply.S1
    to: Box/Strip.N1
  N:
    type: Conductor
    section: 2.5 mm2
    color: BU
    from: Panel/Supply.S2
    to: Box/Strip.N2
  PE:
    type: Conductor
    section: 2.5 mm2
    color: GNYE
    from: Panel/Earth.S1
    to: Box/Strip.N3
  Power:
    type: Cable
    contains: [L, N]
    color: BK
    section: 2.5 mm2
  Tube:
    type: Conduit
    subtype: tube
    from: Panel.S1
    to: Box.N1
    contains: [Power, PE]
""",
    )


def route_11() -> str:
    return _house(
        "Route 11 — two parallel tubes",
        "Two independent conduits side by side.",
        """  Box_A:
    type: JunctionBox
    label: A
    openings: [E1, E2]
    opening_grid: {E: 2}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 2}
        terminals:
          N1: {label: '1', direction: inout, role: phase}
          N2: {label: '2', direction: inout, role: phase}
        view:
          electrical: {x: 60.0, y: 50.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 60.0}
  Box_B:
    type: DeviceBox
    label: B1
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 360.0, y: 40.0}
  Box_C:
    type: DeviceBox
    label: B2
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 360.0, y: 180.0}
cables:
  R1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Box_A/Strip.N1
    to: Box_B/Socket.N1
  R2:
    type: Conductor
    section: 1.5 mm2
    color: BK
    from: Box_A/Strip.N2
    to: Box_C/Socket.N1
  T1:
    type: Conduit
    subtype: tube
    from: Box_A.E1
    to: Box_B.W1
    contains: [R1]
  T2:
    type: Conduit
    subtype: tube
    from: Box_A.E2
    to: Box_C.W1
    contains: [R2]
""",
    )


def route_12() -> str:
    return _house(
        "Route 12 — switch and lamp",
        "Room with junction, switch, and lamp (subset of Test_01).",
        """  Room:
    type: Room
    label: Room
    elements:
      JBox:
        type: JunctionBox
        label: JBox
        openings: [N1, E1, W1]
        opening_grid: {NS: 1, WE: 1}
        elements:
          Strip:
            type: TerminalStrip
            terminal_grid: {NS: 4}
            terminals:
              N1: {label: L, direction: inout, role: phase}
              N2: {label: Lsw, direction: inout, role: phase}
              N3: {label: N, direction: inout, role: neutral}
              N4: {label: PE, direction: inout, role: pe}
            view:
              electrical: {x: 70.0, y: 80.0}
        cables: {}
        view:
          physical: {x: 40.0, y: 80.0}
      SwitchBox:
        type: DeviceBox
        label: Switch
        openings: [W1]
        opening_grid: {W: 1}
        elements:
          Switch:
            type: Switch
            subtype: unipolar
            view:
              electrical: {x: 90.0, y: 20.0}
        cables: {}
        view:
          physical: {x: 300.0, y: 200.0}
      Lamp:
        type: LightPoint
        label: Lamp
        openings: [B1-1]
        opening_grid: {B: 1}
        elements:
          Luminaire:
            type: Luminaire
            terminal_grid: {N: 3}
            terminals:
              N1: {label: '1', direction: in, role: phase}
              N2: {label: '2', direction: in, role: earth}
              N3: {label: '3', direction: in, role: neutral}
            view:
              electrical: {x: 100.0, y: 80.0}
        cables: {}
        view:
          physical: {x: 300.0, y: 40.0}
    cables:
      Sw1:
        type: Conductor
        section: 1.5 mm2
        color: BN
        from: JBox/Strip.N1
        to: SwitchBox/Switch.N1
      Sw2:
        type: Conductor
        section: 1.5 mm2
        color: BK
        from: SwitchBox/Switch.S1
        to: JBox/Strip.N2
      SwCable:
        type: Cable
        contains: [Sw1, Sw2]
        color: BK
        section: 1.5 mm2
      Lp:
        type: Conductor
        section: 1.5 mm2
        color: BK
        from: JBox/Strip.N2
        to: Lamp/Luminaire.N1
      Ln:
        type: Conductor
        section: 1.5 mm2
        color: BU
        from: JBox/Strip.N3
        to: Lamp/Luminaire.N3
      Lpe:
        type: Conductor
        section: 1.5 mm2
        color: GNYE
        from: JBox/Strip.N4
        to: Lamp/Luminaire.N2
      LampCable:
        type: Cable
        contains: [Lp, Ln]
        color: WH
        section: 1.5 mm2
      TubeSw:
        type: Conduit
        subtype: tube
        from: JBox.E1
        to: SwitchBox.W1
        contains: [SwCable]
      TubeLp:
        type: Conduit
        subtype: tube
        from: JBox.N1
        to: Lamp.B1-1
        contains: [LampCable, Lpe]
    view:
      physical: {x: 20.0, y: 20.0, page: {width: 520, height: 360}}
""",
    )


def route_13() -> str:
    # Alias complexity: copy structure of Test_01 notes
    return Path(
        Path(__file__).resolve().parents[1]
        / "src"
        / "housewire_examples"
        / "sites"
        / "Test_01.yaml"
    ).read_text(encoding="utf-8").replace(
        "label: Test 01", "label: Route 13 — Test_01 twin", 1
    ).replace(
        "notes: Minimal house",
        "notes: Route_13 twin of Test_01 (full panel + room routing)",
        1,
    )


def route_14() -> str:
    return _house(
        "Route 14 — three hop chain",
        "Panel → junction → device → lamp (three tubes).",
        """  Panel:
    type: Panel
    label: Panel
    openings: [S1]
    opening_grid: {S: 1}
    elements:
      Supply:
        type: Supply
        view:
          electrical: {x: 40.0, y: 20.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 20.0}
  JBox:
    type: JunctionBox
    label: JBox
    openings: [N1, E1]
    opening_grid: {NS: 1, WE: 1}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 2}
        terminals:
          N1: {label: L, direction: inout, role: phase}
          N2: {label: N, direction: inout, role: neutral}
        view:
          electrical: {x: 60.0, y: 60.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 200.0}
  Mid:
    type: DeviceBox
    label: Mid
    openings: [W1, E1]
    opening_grid: {WE: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 280.0, y: 200.0}
  End:
    type: DeviceBox
    label: End
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 480.0, y: 200.0}
cables:
  FeedL:
    type: Conductor
    section: 2.5 mm2
    color: BN
    from: Panel/Supply.S1
    to: JBox/Strip.N1
  FeedN:
    type: Conductor
    section: 2.5 mm2
    color: BU
    from: Panel/Supply.S2
    to: JBox/Strip.N2
  Feed:
    type: Cable
    contains: [FeedL, FeedN]
    color: BK
    section: 2.5 mm2
  M1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: JBox/Strip.N1
    to: Mid/Socket.N1
  M2:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Mid/Socket.N1
    to: End/Socket.N1
  Tube0:
    type: Conduit
    subtype: tube
    from: Panel.S1
    to: JBox.N1
    contains: [Feed]
  Tube1:
    type: Conduit
    subtype: tube
    from: JBox.E1
    to: Mid.W1
    contains: [M1]
  Tube2:
    type: Conduit
    subtype: tube
    from: Mid.E1
    to: End.W1
    contains: [M2]
""",
    )


def route_15() -> str:
    return _house(
        "Route 15 — two rooms",
        "Two rooms with a conduit between junction boxes.",
        """  Room_A:
    type: Room
    label: Room A
    elements:
      JBox:
        type: JunctionBox
        label: JA
        openings: [E1]
        opening_grid: {E: 1}
        elements:
          Strip:
            type: TerminalStrip
            terminal_grid: {NS: 2}
            terminals:
              N1: {label: L, direction: inout, role: phase}
              N2: {label: N, direction: inout, role: neutral}
            view:
              electrical: {x: 60.0, y: 50.0}
        cables: {}
        view:
          physical: {x: 30.0, y: 40.0}
    cables: {}
    view:
      physical: {x: 20.0, y: 40.0, page: {width: 240, height: 200}}
  Room_B:
    type: Room
    label: Room B
    elements:
      JBox:
        type: JunctionBox
        label: JB
        openings: [W1]
        opening_grid: {W: 1}
        elements:
          Strip:
            type: TerminalStrip
            terminal_grid: {NS: 2}
            terminals:
              N1: {label: L, direction: inout, role: phase}
              N2: {label: N, direction: inout, role: neutral}
            view:
              electrical: {x: 60.0, y: 50.0}
        cables: {}
        view:
          physical: {x: 30.0, y: 40.0}
    cables: {}
    view:
      physical: {x: 320.0, y: 40.0, page: {width: 240, height: 200}}
cables:
  L:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Room_A/JBox/Strip.N1
    to: Room_B/JBox/Strip.N1
  N:
    type: Conductor
    section: 1.5 mm2
    color: BU
    from: Room_A/JBox/Strip.N2
    to: Room_B/JBox/Strip.N2
  Cable:
    type: Cable
    contains: [L, N]
    color: BK
    section: 1.5 mm2
  Tube:
    type: Conduit
    subtype: tube
    from: Room_A/JBox.E1
    to: Room_B/JBox.W1
    contains: [Cable]
""",
    )


def route_16() -> str:
    return _house(
        "Route 16 — dense strip exits",
        "Four conductors leave a strip through two tubes.",
        """  Box:
    type: JunctionBox
    label: Hub
    openings: [E1, S1]
    opening_grid: {E: 1, S: 1}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 4}
        terminals:
          N1: {label: '1', direction: inout, role: phase}
          N2: {label: '2', direction: inout, role: phase}
          N3: {label: '3', direction: inout, role: neutral}
          N4: {label: '4', direction: inout, role: pe}
        view:
          electrical: {x: 70.0, y: 80.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 40.0}
  East:
    type: DeviceBox
    label: East
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 360.0, y: 40.0}
  South:
    type: DeviceBox
    label: South
    openings: [N1]
    opening_grid: {N: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 300.0}
cables:
  E1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Box/Strip.N1
    to: East/Socket.N1
  E2:
    type: Conductor
    section: 1.5 mm2
    color: BU
    from: Box/Strip.N3
    to: East/Socket.N3
  S1:
    type: Conductor
    section: 1.5 mm2
    color: BK
    from: Box/Strip.N2
    to: South/Socket.N1
  S2:
    type: Conductor
    section: 1.5 mm2
    color: GNYE
    from: Box/Strip.N4
    to: South/Socket.N2
  EastCable:
    type: Cable
    contains: [E1, E2]
    color: BK
    section: 1.5 mm2
  SouthCable:
    type: Cable
    contains: [S1, S2]
    color: BK
    section: 1.5 mm2
  TubeE:
    type: Conduit
    subtype: tube
    from: Box.E1
    to: East.W1
    contains: [EastCable]
  TubeS:
    type: Conduit
    subtype: tube
    from: Box.S1
    to: South.N1
    contains: [SouthCable]
""",
    )


def route_17() -> str:
    """Two parallel east tubes (NESW fan stand-in)."""
    return _house(
        "Route 17 — NESW fan",
        "Two parallel east tubes (fan-out stand-in until empty tubes are fixed).",
        """  Box_A:
    type: JunctionBox
    label: Hub
    openings: [E1, E2]
    opening_grid: {E: 2}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 2}
        terminals:
          N1: {label: '1', direction: inout, role: phase}
          N2: {label: '2', direction: inout, role: phase}
        view:
          electrical: {x: 70.0, y: 60.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 100.0}
  Box_B:
    type: DeviceBox
    label: North-east
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 360.0, y: 40.0}
  Box_C:
    type: DeviceBox
    label: South-east
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 360.0, y: 220.0}
cables:
  Run_B:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Box_A/Strip.N1
    to: Box_B/Socket.N1
  Run_C:
    type: Conductor
    section: 1.5 mm2
    color: BK
    from: Box_A/Strip.N2
    to: Box_C/Socket.N1
  Tube_B:
    type: Conduit
    subtype: tube
    from: Box_A.E1
    to: Box_B.W1
    contains: [Run_B]
  Tube_C:
    type: Conduit
    subtype: tube
    from: Box_A.E2
    to: Box_C.W1
    contains: [Run_C]
""",
    )


def route_18() -> str:
    return Path(
        Path(__file__).resolve().parents[1]
        / "src"
        / "housewire_examples"
        / "sites"
        / "Test_01.yaml"
    ).read_text(encoding="utf-8").replace(
        "label: Test 01", "label: Route 18 — multi cable stress", 1
    ).replace(
        "notes: Minimal house",
        "notes: Route_18 multi-cable twin of Test_01",
        1,
    )


def route_19() -> str:
    return _house(
        "Route 19 — staggered heights",
        "Vertical stagger of three device boxes from one hub.",
        """  Hub:
    type: JunctionBox
    label: Hub
    openings: [E1]
    opening_grid: {E: 1}
    elements:
      Strip:
        type: TerminalStrip
        terminal_grid: {NS: 3}
        terminals:
          N1: {label: '1', direction: inout, role: phase}
          N2: {label: '2', direction: inout, role: phase}
          N3: {label: '3', direction: inout, role: phase}
        view:
          electrical: {x: 60.0, y: 70.0}
    cables: {}
    view:
      physical: {x: 40.0, y: 140.0}
  Top:
    type: DeviceBox
    label: Top
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 360.0, y: 40.0}
  Mid:
    type: DeviceBox
    label: Mid
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 360.0, y: 160.0}
  Bot:
    type: DeviceBox
    label: Bot
    openings: [W1]
    opening_grid: {W: 1}
    elements:
      Socket:
        type: Socket
        view:
          electrical: {x: 40.0, y: 30.0}
    cables: {}
    view:
      physical: {x: 360.0, y: 280.0}
cables:
  C1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Hub/Strip.N1
    to: Top/Socket.N1
  C2:
    type: Conductor
    section: 1.5 mm2
    color: BK
    from: Hub/Strip.N2
    to: Mid/Socket.N1
  C3:
    type: Conductor
    section: 1.5 mm2
    color: BU
    from: Hub/Strip.N3
    to: Bot/Socket.N1
  T1:
    type: Conduit
    subtype: tube
    from: Hub.E1
    to: Top.W1
    contains: [C1]
  T2:
    type: Conduit
    subtype: tube
    from: Hub.E1
    to: Mid.W1
    contains: [C2]
  T3:
    type: Conduit
    subtype: tube
    from: Hub.E1
    to: Bot.W1
    contains: [C3]
""",
    )


def route_20() -> str:
    # Highest public complexity alias: same topology as Test_01 / Route_13.
    return Path(
        Path(__file__).resolve().parents[1]
        / "src"
        / "housewire_examples"
        / "sites"
        / "Test_01.yaml"
    ).read_text(encoding="utf-8").replace(
        "label: Test 01", "label: Route 20 — full stress", 1
    ).replace(
        "notes: Minimal house",
        "notes: Route_20 full-stress twin of Test_01",
        1,
    )


GENERATORS = [
    ("Route_01", route_01),
    ("Route_02", route_02),
    ("Route_03", route_03),
    ("Route_04", route_04),
    ("Route_05", route_05),
    ("Route_06", route_06),
    ("Route_07", route_07),
    ("Route_08", route_08),
    ("Route_09", route_09),
    ("Route_10", route_10),
    ("Route_11", route_11),
    ("Route_12", route_12),
    ("Route_13", route_13),
    ("Route_14", route_14),
    ("Route_15", route_15),
    ("Route_16", route_16),
    ("Route_17", route_17),
    ("Route_18", route_18),
    ("Route_19", route_19),
    ("Route_20", route_20),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in GENERATORS:
        path = OUT / f"{name}.yaml"
        path.write_text(fn(), encoding="utf-8")
        print("wrote", path.relative_to(OUT.parent.parent.parent.parent))


if __name__ == "__main__":
    main()
