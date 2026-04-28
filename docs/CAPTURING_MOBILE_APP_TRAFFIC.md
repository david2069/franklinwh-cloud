# Capturing FranklinWH Mobile App Traffic — Generator & V2L

> **Who this guide is for:** FranklinWH system owners who have a **Generator Module**
> and/or **V2L (Vehicle-to-Load)** capability installed, and want to help the
> `franklinwh-cloud` project verify the speculative `set_v2l_mode()` API.
>
> **What you are capturing:** The raw HTTPS request/response payloads that the
> FranklinWH mobile app sends when you toggle V2L on/off, and when you switch the
> generator between Auto and Manual mode.
>
> **Time required:** ~20–30 minutes, one-time.

---

## Background

The `set_v2l_mode()` method in this library is currently a **speculative placeholder**.
We believe toggling V2L maps to a Smart Circuit 3 (Sw3 / CarSW port) write via the
same `sendMqtt` cmdType 311 path used for Smart Circuit control — but this has never
been confirmed from live hardware traffic.

A single capture from someone with V2L hardware is all that is needed to either
confirm or correct this hypothesis.

See: [Generator & V2L API](GENERATOR_V2L_API.md) for the full speculative analysis.

---

## Compatible Capture Tools

| Tool | Platform | Certificate handling | Notes |
|---|---|---|---|
| **[HTTP Toolkit](https://httptoolkit.com/)** | Android, iOS | Automatic on Android | Recommended — free tier sufficient |
| **[Proxyman](https://proxyman.io/)** | iOS (Mac host) | Certificate wizard built-in | Excellent iOS support |
| **[Charles Proxy](https://www.charlesproxy.com/)** | Android & iOS | Manual cert install | Classic tool, paid |
| **[mitmproxy](https://mitmproxy.org/)** | Android (rooted) | Manual | CLI-based, free |

> **HTTP Toolkit** is the recommended tool (it's what this project uses for API
> research). The steps below lead with HTTP Toolkit and include iOS alternatives.

---

## Prerequisites

### Hardware required

- FranklinWH aGate (US model — AU has no V2L)
- Generator Module (SKU: `ACCY-GENV1-US` or `ACCY-GENV2-US`) — **installed and configured in the app**
- Smart Circuits V1 (SKU: `ACCY-SCV1-US`) — **if capturing V2L (CarSW port)**
- System must be able to go off-grid (grid relay can open)

### Device requirements

**Android (easier — recommended):**
- Android phone with the FranklinWH app installed
- USB cable or ADB over WiFi
- **Rooted device** strongly preferred. Non-rooted works with HTTP Toolkit's APK patching
  but may fail if the app uses certificate pinning.

**iOS (harder):**
- iPhone with the FranklinWH app installed
- Mac with HTTP Toolkit, Proxyman, or Charles installed
- Both phone and Mac on the **same WiFi network**

---

## Step 1 — Set Up the Proxy

### Option A: HTTP Toolkit (Android)

1. Download and install [HTTP Toolkit](https://httptoolkit.com/) on your computer.
2. Connect your Android phone via USB cable (or enable ADB over WiFi).
3. Open HTTP Toolkit → click **"Android device via ADB"**.
4. HTTP Toolkit will automatically install its CA certificate on the device.
5. Open the **FranklinWH app** — you should see requests appearing in HTTP Toolkit's
   **Traffic** tab within a few seconds.

> **If you see SSL errors / requests not appearing:** The app may be using certificate
> pinning. Try HTTP Toolkit's **"Android Device (Rooted)"** option if your device is rooted,
> or the **"Android APK"** option to patch the APK binary directly.

### Option B: Proxyman (iOS — Mac only)

1. Download [Proxyman](https://proxyman.io/) on your Mac.
2. In Proxyman: **Certificate** → **Install Certificate on iOS** → follow the wizard.
3. On your iPhone: **Settings → General → VPN & Device Management** → trust the Proxyman CA.
4. In Proxyman: **Settings → Proxy Settings** → note the IP and port (default: 9090).
5. On iPhone: **Settings → WiFi → your network → Configure Proxy → Manual**
   → enter the Mac's IP and port 9090.
6. Open the FranklinWH app and verify traffic appears in Proxyman.

### Option C: Charles Proxy (Android or iOS)

1. Download [Charles](https://www.charlesproxy.com/) on your computer.
2. Go to **Help → SSL Proxying → Install Charles Root Certificate on Mobile Device**.
3. Follow the on-screen instructions for your platform.
4. On your phone, set the WiFi proxy to your computer's IP on port **8888**.
5. In Charles: **Proxy → SSL Proxying Settings → add `*.franklinwh.com` and `*.amazonaws.com`**.

---

## Step 2 — Filter to FranklinWH Traffic Only

Once the app is connected through your proxy:

**HTTP Toolkit:** In the search/filter bar, type:
```
franklinwh.com
```

**Charles / Proxyman:** In the Structure view, look for:
```
energy.franklinwh.com
```

The FranklinWH app communicates exclusively with this host (routed through AWS CloudFront).
You should see periodic `POST /hes-gateway/manage/sendMqtt` calls — those are the MQTT relay
commands that control the hardware.

---

## Step 3 — Capture Generator Traffic

### What to capture

With the proxy running and the FranklinWH app open:

1. Navigate to: **App Home → Gateway → Settings → Generator**
   (exact path may vary by app version — look for Generator or Standby Power section)

2. Switch the generator from **Auto** to **Manual** mode (or vice versa).
   This generates the `updateIotGenerator` call.

3. If the generator is running or in standby, note its current status display in the app.

### What to look for in the captured traffic

Look for a `POST` to a URL ending in:
```
/hes-gateway/terminal/updateIotGenerator
```

The request body should look like:
```json
{
  "gatewayId": "10060006A0XXXXXXXXXX",
  "manuSw": 1,
  "opt": 1
}
```

Where `manuSw` is the mode: `1` = Auto-schedule, `2` = Manual.

Also look for:
```
/hes-gateway/terminal/selectIotGenerator
```
This is the read call — its **response** shows the current generator state fields.
Please capture the full response body as it will reveal all available fields.

---

## Step 4 — Capture V2L Traffic

> **Important:** V2L only operates when the system is **off-grid** (grid relay open).
> You may need to manually invoke "Go Off-Grid" in the app first, or wait for a real
> outage. Do not disconnect your grid physically — use the app's simulated off-grid mode.

### Prerequisites check (in the app)

Before capturing V2L, verify the app shows the V2L / CarSW port as available.
On US V1 Smart Circuits with Generator Module, this typically appears as a third
"circuit" slot or as a dedicated "V2L" toggle.

### What to capture

1. With the proxy still running, navigate to the Smart Circuits / V2L section.
2. Note the **current V2L state** (enabled/disabled, run state).
3. **Toggle V2L ON** — press the enable/start button.
4. Wait 5 seconds.
5. **Toggle V2L OFF** — press the disable/stop button.

### What to look for in the captured traffic

#### Scenario A — V2L is Sw3 (our hypothesis)

Look for `POST /hes-gateway/manage/sendMqtt` with a body containing `"cmdType": 311`.

The request body (inside `dataArea`) would look something like:
```json
{
  "opt": 1,
  "Sw3Mode": 1,
  "Sw3ProLoad": 0,
  "Sw3MsgType": 1,
  "modeChoose": 3
}
```

#### Scenario B — Dedicated V2L endpoint (alternative)

Look for `POST` to any URL ending in something like:
```
/hes-gateway/terminal/updateV2l
/hes-gateway/terminal/selectV2lMode
/hes-gateway/terminal/updateCarSw
```

With a body potentially containing:
```json
{
  "gatewayId": "10060006A0XXXXXXXXXX",
  "v2lModeEnable": 1,
  "opt": 1
}
```

#### Key fields to record regardless of which scenario

Note down:
- The **full URL path** of the POST request
- The **`cmdType`** value if it's a `sendMqtt` call
- All keys present in the request body, especially:
  - `Sw3Mode`, `modeChoose`, `v2lModeEnable`, `opt`, `cmdType`
- The **response body** shape

---

## Step 5 — Export the Captured Traffic

### HTTP Toolkit

1. In the Traffic tab, filter to show only the relevant requests.
2. Select the specific requests (updateIotGenerator, sendMqtt V2L calls).
3. Right-click → **Export** → **Export as HAR** (or copy the raw request).
4. Save as `v2l_generator_capture_YYYY-MM-DD.har`.

### Charles Proxy

1. In the Structure view, right-click the `franklinwh.com` host.
2. **Export → Export Selected → HAR**.

### Proxyman

1. Select the relevant requests in the list.
2. **File → Export → as HAR**.

### Manual copy (simplest)

If you just want to share the raw JSON:
1. Click on the relevant request in the proxy tool.
2. Copy the **Request Body** and **Response Body** tabs.
3. Paste into a text file.

---

## Step 6 — Redact Before Sharing

**Before sharing any capture**, please redact the following PII:

| Field | What to replace with |
|---|---|
| Gateway serial (`gatewayId`) | `10060006A0XXXXXXXXXX` |
| `Authorization` / `token` headers | `[REDACTED]` |
| Email address | `user@example.com` |
| `userId` | `99999` |
| Site address fields | `[REDACTED]` |

A quick find-replace in any text editor is sufficient.

**Do not redact:**
- `cmdType` values — essential for identification
- `Sw3Mode`, `v2lModeEnable`, `opt`, `modeChoose` — these are the key fields
- Response field names and their integer values
- URL paths (these contain no PII)

---

## Step 7 — Share the Capture

Open a GitHub issue at:
**[github.com/david2069/franklinwh-cloud/issues](https://github.com/david2069/franklinwh-cloud/issues)**

Title: `[V2L Capture] <your hardware model>`

Include:
- Your aGate model (X-01, X-02, etc.) and approximate manufacture year
- Generator Module SKU (`ACCY-GENV1-US` or `ACCY-GENV2-US`)
- Smart Circuits SKU
- The captured request/response bodies (redacted)
- Whether the app toggle worked as expected

---

## Troubleshooting

### "I can see traffic but the V2L requests are encrypted / not visible"

The FranklinWH app may enforce **certificate pinning** on some Android versions.
Options:
- Use a rooted device with **HTTP Toolkit Rooted Android** setup
- Use **Frida** to bypass pinning (advanced — see [HTTP Toolkit docs](https://httptoolkit.com/blog/android-certificate-pinning-bypassing/))
- Use iOS with Proxyman (iOS apps often have weaker pinning)

### "I can't find the V2L toggle in the app"

- V2L is only visible when the Generator Module is installed and configured
- The system must be able to go off-grid — check that "Go Off-Grid" works first
- Some app versions show it under **Smart Circuits → CarSW** rather than a dedicated V2L section

### "The app shows V2L but I can't toggle it"

- Confirm `v2lModeEnable = 1` in the device composite info
- The system must be in off-grid mode for V2L to activate
- Some firmware versions require the generator to be running before V2L enables

### "I only have a V2 Smart Circuits (ACCY-SCV2-US)"

V2 Smart Circuits have **built-in V2L** (no Generator Module required). The control
path may differ from V1 — your capture is equally valuable and may reveal a different
cmdType or field structure.

---

## Reference — Key Endpoints to Watch

| URL pattern | Type | What it does |
|---|---|---|
| `/hes-gateway/manage/sendMqtt` | POST | All MQTT relay commands — check `cmdType` inside |
| `/hes-gateway/terminal/selectIotGenerator` | GET | Read current generator state |
| `/hes-gateway/terminal/updateIotGenerator` | POST | Set generator mode (confirmed) |
| `/hes-gateway/terminal/getEntranceInfo` | GET | Feature flags incl. `v2lModeEnable` |
| Any URL with `V2l`, `CarSw`, `v2l` | POST/GET | Possible dedicated V2L endpoint |

**`sendMqtt` cmdTypes to watch for:**

| `cmdType` | Known purpose |
|---|---|
| `203` | Device composite status |
| `211` | Electrical / relay states |
| `311` | Smart Circuit config read/write ← **V2L likely here** |
| `353` | Accessory load power |
| `310` | Smart Circuit toggle |
| Any new number | Possible dedicated V2L command |

---

## Related Docs

- [Generator & V2L API](GENERATOR_V2L_API.md) — what we know and what is speculative
- [Capturing HAR Traffic](CAPTURING_HAR_TRAFFIC.md) — general API capture guide
- [MQTT Command Catalog](MQTT_CMD_CATALOG.md) — all known cmdType values
