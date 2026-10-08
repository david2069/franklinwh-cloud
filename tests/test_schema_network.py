"""Tests for the network inventory and health check in the schema command.

network_health() derives findings from a get_network_state() snapshot. It has to
be derived rather than read, because the API exposes no connection-attempt
history — selectDeviceRunLogList is a static alarm-code dictionary, not an event
log.
"""

import pytest

from franklinwh_cloud.cli_commands.schema import (
    NETWORK_NOTES,
    NETWORK_SCHEMA,
    network_health,
)


def _state(**over):
    """A healthy baseline matching live hardware on 2026-08-09."""
    base = {
        "active": {"id": 3, "key": "wifi", "label": "WiFi", "ip": "192.168.0.110",
                   "selection": "device-managed"},
        "interfaces": [
            {"id": 1, "key": "eth0", "enabled": True, "link": True, "ip": "10.0.0.5",
             "is_active": False, "available": True},
            {"id": 2, "key": "eth1", "enabled": False, "link": False, "ip": None,
             "is_active": False, "available": False},
            {"id": 3, "key": "wifi", "enabled": True, "link": True,
             "ip": "192.168.0.110", "is_active": True, "available": True,
             "signal_pct": 84},
            {"id": 4, "key": "4g", "enabled": True, "link": False, "ip": None,
             "is_active": False, "available": True, "signal_raw": 22,
             "sim_status": 2, "sim_status_name": "Active"},
        ],
        "cloud": {"aws_connected": True, "internet": True, "router_status_raw": 1},
        "linked_transports": ["eth0", "wifi"],
        "available_transports": ["eth0", "wifi", "4g"],
        "redundant": True,
        "source": {"cmds": [317, 339, 341], "extended_339": True},
    }
    base.update(over)
    return base


def _set_iface(state, key, **fields):
    for i in state["interfaces"]:
        if i["key"] == key:
            i.update(fields)
    return state


def _codes(state):
    return [f["code"] for f in network_health(state)]


class TestInventory:

    def test_every_entry_is_a_four_tuple(self):
        for field, spec in NETWORK_SCHEMA.items():
            assert len(spec) == 4, field

    def test_groups_are_all_network_prefixed_so_filter_network_catches_them(self):
        for field, (_, _, _, group) in NETWORK_SCHEMA.items():
            assert group.lower().startswith("network"), f"{field} -> {group}"

    def test_covers_all_three_cmdtypes_plus_the_rest_sim_lookup(self):
        sources = " ".join(s for _, s, _, _ in NETWORK_SCHEMA.values())
        for expected in ("317", "339", "341", "getHomeGatewayList"):
            assert expected in sources

    def test_semantics_travel_with_the_data(self):
        """The availability rule and the two signal scales are easy to misread,
        so they are printed alongside the inventory."""
        notes = " ".join(NETWORK_NOTES).lower()
        assert "sim active" in notes
        assert "address" in notes
        assert "0-52" in notes
        assert "not a boolean" in notes


class TestHealthCheck:

    def test_healthy_state_reports_no_warnings(self):
        findings = network_health(_state())
        assert [f for f in findings if f["level"] == "WARN"] == []

    def test_wifi_associated_without_lease_warns(self):
        """The 2026-03-21 and 2026-08-08 failure mode."""
        s = _set_iface(_state(), "wifi", ip=None, link=False, available=False,
                       signal_pct=76)
        findings = network_health(s)

        hit = next(f for f in findings if f["code"] == "wifi_no_lease")
        assert hit["level"] == "WARN"
        assert "76%" in hit["detail"]

    def test_wifi_with_no_signal_at_all_does_not_warn_about_lease(self):
        """No signal means out of range, not a DHCP problem."""
        s = _set_iface(_state(), "wifi", ip=None, link=False, signal_pct=0)
        assert "wifi_no_lease" not in _codes(s)

    def test_inactive_sim_warns(self):
        s = _set_iface(_state(), "4g", sim_status=1,
                       sim_status_name="Installed (Inactive)", available=False)
        hit = next(f for f in network_health(s) if f["code"] == "sim_not_active")
        assert hit["level"] == "WARN"

    def test_unknown_sim_does_not_warn(self):
        """A failed REST lookup must not manufacture an alarm."""
        s = _set_iface(_state(), "4g", sim_status=None, sim_status_name=None)
        assert "sim_not_active" not in _codes(s)

    def test_cellular_disabled_warns_about_losing_the_lifeline(self):
        s = _set_iface(_state(), "4g", enabled=False, available=False)
        hit = next(f for f in network_health(s) if f["code"] == "cellular_disabled")
        assert hit["level"] == "WARN"
        assert "on-site" in hit["detail"]

    def test_no_reception_warns(self):
        s = _set_iface(_state(), "4g", signal_raw=0, available=False)
        assert "no_cellular_reception" in _codes(s)

    def test_loss_of_redundancy_warns(self):
        s = _state(redundant=False, available_transports=["wifi"])
        hit = next(f for f in network_health(s) if f["code"] == "no_redundancy")
        assert hit["level"] == "WARN"

    def test_unplugged_ethernet_is_info_not_warn(self):
        s = _set_iface(_state(), "eth0", link=False, ip=None, available=False)
        hit = next(f for f in network_health(s) if f["code"] == "eth0_no_link")
        assert hit["level"] == "INFO"

    def test_disabled_ethernet_is_not_reported(self):
        """eth1 is switched off in the baseline — silence, not noise."""
        assert "eth1_no_link" not in _codes(_state())

    def test_unreliable_cloud_flags_are_info_only(self):
        """awsStatus=0 while the data arrived through the cloud is a known
        contradiction — worth surfacing, not worth alarming about."""
        s = _state(cloud={"aws_connected": False, "internet": False,
                          "router_status_raw": 0})
        hit = next(f for f in network_health(s) if f["code"] == "cloud_flags_unreliable")
        assert hit["level"] == "INFO"

    def test_warnings_sort_before_info(self):
        s = _set_iface(_state(redundant=False, available_transports=["wifi"]),
                       "eth0", link=False, ip=None, available=False)
        levels = [f["level"] for f in network_health(s)]
        assert levels == sorted(levels, key=lambda l: {"WARN": 0, "INFO": 1}[l])

    def test_empty_state_does_not_crash(self):
        assert isinstance(network_health({}), list)
