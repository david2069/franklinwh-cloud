# Capturing HAR Traffic from FranklinWH

This guide covers the recurring engineering protocol for proxying and extracting physical network payloads (`*.har`) emitted by the official FranklinWH mobile application.

## Why capture HARs?
The FranklinWH Cloud API is completely undocumented. The vendor does not publish changelogs when API surfaces mutate. Capturing HARs directly from the mobile app (or web dashboard) is the **exclusive mechanism** for deriving new API topologies securely. 

These captures provide:
1. Proof of authentication cycles.
2. Verified physical schemas for `--pedantic` API verification.
3. Cryptographic validations of URL parameters or headers.

## Prerequisites
To sniff the encrypted API calls inside the mobile app, you need a TLS-decrypting Man-in-the-Middle (MITM) proxy. We strongly recommend **HTTP Toolkit** or **Proxyman**.

1. Download and install [HTTP Toolkit](https://httptoolkit.com/).
2. You will need either:
  * A rooted Android device.
  * An Android emulator (like Android Studio's AVD) configured *without* Google Play Services locking down certificate storage.
  * Alternatively, HTTP Toolkit can automatically attempt to patch APKs on non-rooted devices (results vary).

## Step-by-Step Capture Protocol

### 1. Intercepting the App
1. Open HTTP Toolkit and select **"Android device via ADB"**.
2. Assuming your device is connected (or emulator running), HTTP Toolkit will inject its Certificate Authority (CA) into the device's keychain.
3. Open the **FranklinWH** app on the device.
4. If successful, HTTP Toolkit's `View` tab will immediately start populating with HTTPS requests directed at `energy.franklinwh.com`.

### 2. Generating the Footprint
Once intercepted, you want to generate a rich, comprehensive API surface for our parser. Inside the FranklinWH app:
1. Log out fully and log back in (captures `appUserOrInstallerLogin` and tokens).
2. Browse to the Home screen and wait 10 seconds (captures `getDeviceCompositeInfo`, `status`, etc).
3. Navigate to **Smart Circuits** and toggle a circuit on/off (captures POST states).
4. Navigate to **Energy Management** -> **Time of Use** and change a season peak hour (captures complex TOU JSON arrays).
5. Load the Battery details, warranty pages, and utility network settings.

### 3. Exporting the Footprint
1. Inside HTTP Toolkit, pause the capture.
2. Filter the view by typing `franklinwh.com` to isolate the core APIs.
3. Select **File -> Export -> Export HTTP Archive (HAR)**.
4. Save the file locally to your repository under:
  `/Users/davidhona/dev/franklinwh-cloud/hars/franklinwh_capture_YYYY-MM-DD.har`

### 4. Reconciling the Schema
Finally, use the generator tool to integrate the new capture against our official specs.

```bash
# Check if you unlocked entirely new URL paths:
python scripts/openapi_generator.py --mode fast

# Check if the existing pages returned hidden/new JSON schemas:
python scripts/openapi_generator.py --mode pedantic
```
Review the resulting `unmapped_endpoints.json` to identify what needs to be officially codified into `docs/franklinwh_openapi.json`.
