# SPAN Panel Integration

> How the aGate talks to a SPAN panel, and why it matters to anything that
> changes the gateway's network transport.

**Source:** SPAN Tech Portal, *App Note: Integration with FranklinWH* and
*Solar + Storage Quickstart* — screenshots supplied by the user 2026-09-18.
The pages are a JavaScript-rendered Salesforce portal and cannot be fetched
directly. Evidence tiers per
[AP-14](../.agents/policies/evidence_standard.md).

---

## What the link actually is

**CONFIRMED** (SPAN app note screenshots):

- The integration is **SunSpec Modbus over TCP port 502**.
- The **aGate is the Modbus client**. It is configured with the **SPAN panel's
  IP address** and polls it — e.g. `192.168.0.103:502`.
- Physically, the SPAN panel's **Aux Comms / ETH-1** port connects to the
  aGate's Ethernet port.
- **The SPAN panel provides the aGate's internet connection over that same
  link.** It is not merely a peer on the household LAN.

SPAN panel generation changes the connector:

| SPAN PN | Aux Comms |
|---|---|
| `1-00800-08` and lower | USB port, requires a **USB-Ethernet dongle** |
| `1-00800-09` and higher | native **ETH-1** RJ45 |

## Enabling it

In the FranklinWH app, on an **installer account**:

```
Settings → Modbus → SPAN Panel → Connect to SPAN → Confirm
```

with a "Connect to SPAN Panel?" toggle, the panel's **IP address**, and
**port 502**. So `spanFlag` reflects a deliberate installer action, not
autodetection.

## Consequences for this library

### 1. Changing transport is riskier than the preflight assumes

`switch_to_wifi()` can move the active transport (observed 4G→WiFi in the
corpus; confirmed live by U2). On a SPAN site the Ethernet link is carrying
**both** the SPAN Modbus session **and**, per the app note, the gateway's
internet. Moving to WiFi therefore risks losing the SPAN integration, and the
write-safety preflight checks neither — it only asks whether *some* transport
survives. See `DEF-WIFI-SWITCH-BREAKS-SPAN`.

**INFERRED, not confirmed:** whether SPAN remains reachable over WiFi depends
on the site's topology. The captured example address, `192.168.0.103`, sits on
an ordinary household subnet, so a WiFi-attached aGate might still reach it —
or might not, if the link is point-to-point. Nothing here establishes which.

### 2. Our Modbus 502 probe tests a different thing

`discover(probe_local=True)` and `get_connectivity_overview(deep_scan=True)`
probe **port 502 on the aGate**. The SPAN integration runs 502 on the **SPAN
panel**, with the aGate as client. These are not the same service, and a result
from one says nothing about the other. The probe is reported as informational
for exactly this reason.

### 3. Which Ethernet port

The aGate photograph in the app note shows ports labelled **Debug** and
**ETH-2**. That matches the *Commissioning Guide* (`COMM-2.8.0` p.7) for
aGate X 1.1, where the household cable goes to **Eth2** and **Eth1 is the Debug
port** — and contradicts the *Installation Guide* (`INST-1.2.07` p.62), which
says Eth1.

**Note the collision of names:** SPAN's **ETH-1** is a port on the *SPAN panel*.
It is not the aGate's Eth1. Cabling SPAN ETH-1 to the aGate's "Eth1" because the
numbers match would land on the Debug port on that hardware revision.

This narrows `DEF-ETH-PORT-IDENTITY-UNCONFIRMED` but does not close it: the
photo is a US aGate, and which **API field** (`eth0` or `eth1`) corresponds to
the physical port is still unestablished.

## Not established

- Whether SPAN stays reachable if the aGate moves to WiFi.
- Which API field maps to the physical port SPAN is cabled to.
- Whether the aGate re-establishes the Modbus session automatically after a
  transport change.
- Whether AU/NZ installs support SPAN at all — the integration is documented by
  SPAN, a US company, and `spanFlag` is false on the reference gateway.
