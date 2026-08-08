"""Tests for cable link UI actions (select / insert / open-run)."""

from __future__ import annotations

from pathlib import Path

import pytest

from housewire.site import abm
from housewire.site.cable_actions import (
    cable_detail,
    claim_run,
    delete_cables,
    find_cable_owner,
    insert_conductor,
    insert_conduit,
    insert_cable,
    land_run,
    open_run,
    ungroup_cable,
    update_cable_properties,
)
from housewire.site.delete_selection import delete_selection
from housewire.site.session import SiteSession


def _session(tmp_path: Path) -> SiteSession:
    yaml_path = tmp_path / "housewire.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "schema: house/v2",
                "type: House",
                "elements:",
                "  RoomA:",
                "    type: Room",
                "    openings: [E1]",
                "    opening_grid: {E: 1}",
                "    elements:",
                "      SockA:",
                "        type: Socket",
                "        subtype: Schuko",
                "  RoomB:",
                "    type: Room",
                "    openings: [W1]",
                "    opening_grid: {W: 1}",
                "    elements:",
                "      SockB:",
                "        type: Socket",
                "        subtype: Schuko",
                "cables: {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return SiteSession(tmp_path, site_yaml=yaml_path)


def test_insert_conduit_creates_empty_tube(tmp_path: Path) -> None:
    session = _session(tmp_path)
    detail = insert_conduit(
        session,
        from_ref="RoomA.E1",
        to_ref="RoomB.W1",
        owner_id=".",
    )
    assert detail["kind"] == "conduit"
    assert detail["from"] == "RoomA.E1"
    assert detail["to"] == "RoomB.W1"
    assert detail["contains"] == []
    _path, doc = session.ensure_doc()
    assert list(doc["cables"]) == [detail["id"]]


def test_insert_conductor_and_patch(tmp_path: Path) -> None:
    session = _session(tmp_path)
    detail = insert_conductor(
        session,
        from_ref="RoomA/SockA.N1",
        to_ref="RoomB/SockB.N1",
        owner_id=".",
        color="BN",
    )
    assert detail["kind"] == "conductor"
    assert detail["from"] == "RoomA/SockA.N1"
    updated = update_cable_properties(
        session, cable_id=detail["id"], fields={"notes": "test note", "color": "BU"}
    )
    assert updated["notes"] == "test note"
    assert updated["color"] == "BU"


def test_cable_group_and_delete(tmp_path: Path) -> None:
    session = _session(tmp_path)
    a = insert_conductor(
        session,
        from_ref="RoomA/SockA.N1",
        to_ref="RoomB/SockB.N1",
        owner_id=".",
        name="L1",
        color="BN",
    )
    b = insert_conductor(
        session,
        from_ref="RoomA/SockA.N2",
        to_ref="RoomB/SockB.N2",
        owner_id=".",
        name="N1",
        color="BU",
    )
    cable = insert_cable(
        session, contains=[a["id"], b["id"]], owner_id=".", name="Funda1"
    )
    assert cable["kind"] == "cable"
    assert set(cable["contains"]) == {"L1", "N1"}
    _path, doc = session.ensure_doc()
    deleted = delete_cables(doc, ["Funda1"])
    assert "Funda1" in deleted
    with pytest.raises(ValueError):
        find_cable_owner(doc, "Funda1")
    # Children remain
    find_cable_owner(doc, "L1")


def test_ungroup_cable_preserves_members_in_conduit(tmp_path: Path) -> None:
    session = _session(tmp_path)
    conduit = insert_conduit(
        session, from_ref="RoomA.E1", to_ref="RoomB.W1", owner_id=".", name="Tube"
    )
    a = insert_conductor(
        session,
        from_ref="RoomA/SockA.N1",
        to_ref="RoomB/SockB.N1",
        owner_id=".",
        name="L1",
        conduit_id=conduit["id"],
    )
    cable = insert_cable(session, contains=[a["id"]], owner_id=".", name="Funda1")

    assert ungroup_cable(session, cable_id=cable["id"]) == ["L1"]
    _path, doc = session.ensure_doc()
    assert doc["cables"]["Tube"]["contains"] == ["L1"]
    with pytest.raises(ValueError):
        find_cable_owner(doc, "Funda1")


def test_delete_selection_cable_id(tmp_path: Path) -> None:
    session = _session(tmp_path)
    detail = insert_conductor(
        session,
        from_ref="RoomA/SockA.N1",
        to_ref="RoomB/SockB.N1",
        owner_id=".",
        name="WireX",
    )
    _path, doc = session.ensure_doc()
    result = delete_selection(doc, [detail["id"]])
    assert detail["id"] in result.deleted
    with pytest.raises(ValueError):
        find_cable_owner(doc, detail["id"])


def test_open_claim_land_flow(tmp_path: Path) -> None:
    session = _session(tmp_path)
    opened = open_run(session, leaves="RoomA.E1", owner_id=".", colors=["BN", "BU"])
    assert opened["id"].startswith("OPEN_")
    claimed = claim_run(
        session, cable_id=opened["id"], enter="RoomB.W1"
    )
    assert claimed.get("conduit")
    landed = land_run(
        session,
        cable_id=opened["id"],
        from_ref="RoomA/SockA.[N1,N2]",
        to_ref="RoomB/SockB.[N1,N2]",
        as_name="LineaAB",
    )
    assert landed["id"] == "LineaAB"
    assert landed["is_open_run"] is False
