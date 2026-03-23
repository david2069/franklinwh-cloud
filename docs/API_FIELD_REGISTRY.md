# FranklinWH Cloud API — Static Field Registry

> Every key returned by static/config APIs, categorized and annotated.
> Source: live capture from AU system (aGate X-01-AU, 1× aPower X-01-AU)

**Categories:** 🔧 Hardware | 🏷️ Identity | 📍 Location | 📅 Date | ⚡ Electrical | 🔌 Accessory | 📋 Service/Programme | 💰 Billing | ❓ Unknown

---

## `get_entrance_info` — Feature Flags

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `tariffSettingFlag` | `true` | 📋 | TOU tariff configured | ✅ |
| `pcsEntrance` | `1` | 🔧 | Grid import/export controls enabled | ✅ |
| `solarFlag` | `true` | 🔧 | Solar panels installed | ✅ |
| `gridFlag` | `true` | 🔧 | Grid-connected (not off-grid) | ✅ |
| `sgipEntrance` | `0` | 📋 | SGIP (CA Self-Generation Incentive) | ✅ |
| `bbEntrance` | `0` | 📋 | BB (Hawaii Battery Bonus) | ✅ |
| `ja12Entrance` | `0` | 📋 | JA12 (CA Joint Appendix 12) | ✅ |
| `sdcpFlag` | `false` | 📋 | SDCP (CA sustainable dev) | ✅ |
| `slSettingFlag` | `1` | ❓ | SL settings — purpose unclear | ⚠️ |
| `needCtTest` | `false` | 🔧 | CT calibration required | ✅ |
| `globalGridDischargeMax` | `-1.0` | ⚡ | Export limit kW (-1 = unlimited) | ✅ |
| `globalGridChargeMax` | `-1.0` | ⚡ | Import limit kW (-1 = unlimited) | ✅ |
| `gridFeedMaxFlag` | `2` | ⚡ | Feed-in limit mode (2 = default) | ✅ |
| `gridMaxFlag` | `2` | ⚡ | Import limit mode (2 = default) | ✅ |
| `gridFeedMax` | `null` | ⚡ | Feed-in limit kW (null = unlimited) | ✅ |
| `gridMax` | `null` | ⚡ | Import limit kW (null = unlimited) | ✅ |
| `peakDemandGridMax` | `null` | ⚡ | Peak demand limit | ✅ |
| `backupSolution` | `null` | 🔧 | Backup solution type | ✅ |
| `bbDischargePower` | `null` | 📋 | HI BB discharge power limit | ✅ |
| `bonusEnable` | `null` | 📋 | HI bonus enable flag | ✅ |
| `ahubAddressingFlag` | `null` | 🔌 | aHub (253) detected | ✅ |
| `chargingPowerLimited` | `false` | ⚡ | Charging power limited flag | ❌ NEW |

---

## `get_home_gateway_list` — aGate Identity

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `id` | `10060006A02F...` | 🏷️ | aGate serial number | ✅ |
| `name` | `FHP` | 🏷️ | User-assigned aGate name | ✅ |
| `status` | `1` | 🔧 | Device status (1=normal) | ✅ |
| `activeStatus` | `1` | 🔧 | Activation status | ✅ |
| `connType` | `3` | 🔧 | Connection type (3=WiFi) | ✅ |
| `sysHdVersion` | `102` | 🔧 | Hardware version → model lookup | ✅ |
| `realSysHdVersion` | `FranklinWH System1.2` | 🔧 | Human-readable HW version | ✅ |
| `protocolVer` | `V1.11.01` | 🔧 | Protocol version | ✅ |
| `version` | `V12R02B85D00_250624` | 🔧 | Firmware version | ✅ |
| `simCardStatus` | `2` | 🔧 | SIM card (0=none, 2=active) | ✅ |
| `activeTime` | `1721621848000` | 📅 | Activation timestamp (ms) | ✅ |
| `installTime` | `null` | 📅 | Installation timestamp | ✅ |
| `createTime` | `1713857542000` | 📅 | Account creation timestamp | ✅ |
| `deviceTime` | `2026-03-23 09:47` | 📅 | Current aGate local time | ✅ |
| `zoneInfo` | `Australia/Sydney` | 📍 | IANA timezone | ✅ |
| `countryId` | `3` | 📍 | Country (3=AU) | ✅ |
| `provinceId` | `87` | 📍 | State/province ID | ✅ |
| `account` | `[REDACTED]@...` | 🏷️ | Owner email | ⚠️ PII |
| `loadOption` | `1` | ❓ | Load configuration option | ❌ NEW |
| `gerOption` | `2` | ❓ | Generator configuration option | ❌ NEW |
| `groupId` / `groupName` / `groupFlag` | `null/null/0` | 🏷️ | Fleet/group membership | ✅ |
| `benefitShowFlag` | `1` | 📋 | Show benefit/savings UI | ❌ NEW |
| `isJoinJA12` | `false` | 📋 | Joined JA12 programme | ❌ NEW |

---

## `get_device_info` — Hardware Detail

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `gatewayId` | `1006...` | 🏷️ | aGate serial | ✅ |
| `date` | `2026-03-23` | 📅 | Current date on aGate | ❌ NEW |
| `deviceTime` | `2026-03-23 09:46:54` | 📅 | Current time on aGate | ✅ |
| `countryId` | `3` | 📍 | Country | ✅ |
| `provinceId` | `87` | 📍 | Province | ✅ |
| `sysHdVersion` | `102` | 🔧 | Hardware version string | ✅ |
| `sysHdVersionInt` | `102` | 🔧 | Hardware version int | ❌ NEW |
| `realSysHdVersion` | `FranklinWH System1.2` | 🔧 | Human-readable | ✅ |
| `protocolVer` | `V1.11.01` | 🔧 | Protocol | ✅ |
| `offGirdFlag` | `0` | 🔧 | Off-grid active (note: typo in API) | ✅ |
| `offMessage` | `null` | 🔧 | Off-grid reason message | ❌ NEW |
| `genEn` | `0` | 🔌 | Generator enabled | ✅ |
| `v2lModeEnable` | `null` | 🔌 | V2L mode enabled | ✅ |
| `v2lRunState` | `null` | 🔌 | V2L running state | ✅ |
| `solarFlag` | `true` | 🔧 | Solar installed | ✅ |
| `solarTipMsg` | `""` | 🔧 | Solar tip message | ❌ |
| `mpptEnFlag` | `false` | 🔌 | MPPT enabled (aPower S only) | ✅ |
| `apbox20Num` | `0` | 🔌 | aPBox 2.0 count | ❌ NEW |
| `installerId` | `2541` | 🏷️ | Installer account ID | ❌ NEW |
| `chooseFinancierId` | `0` | 📋 | Financier selection | ❌ NEW |
| `serviceVoltageFlag` | `null` | ⚡ | Service voltage flag | ❌ NEW |
| `gridPhaseConSet` | `null` | ⚡ | Grid phase configuration | ❌ NEW |
| `emsDeviceVer` | `0` | 🔧 | EMS device version | ❌ |
| `activeStatus` | `1` | 🔧 | Active | ✅ |
| `newHomeFlag` | `null` | ❓ | New home flag | ❌ NEW |
| `sleepStatus` | `null` | 🔧 | Sleep mode status | ❌ NEW |
| `blackSleepFlag` | `false` | 🔧 | Black sleep mode flag | ❌ NEW |
| `fixedPowerTotal` | `5.0` | ⚡ | Total rated power kW | ✅ |
| `fixedPowerAverage` | `5.0` | ⚡ | Average rated power kW | ✅ |
| `totalCap` | `13.6` | ⚡ | Total battery capacity kWh | ✅ |
| `apowerList[].id` | `10050013...` | 🏷️ | aPower serial | ✅ |
| `apowerList[].ratedPwr` | `5000` | ⚡ | Rated power (W) | ✅ |
| `apowerList[].rateBatCap` | `13600` | ⚡ | Rated capacity (Wh) | ✅ |
| `peHwVerList` | `[2]` | 🔧 | PE hardware version per unit | ❌ NEW |
| `firstName` / `lastName` | `[REDACTED]` | 🏷️ | Owner name | ⚠️ PII |
| `fhpSn` | `10050013...` | 🏷️ | Primary aPower serial | ❌ |
| `equipType` | `null` | 🔧 | Equipment type | ❌ NEW |
| `msaInstallStartDetectTime` | `null` | 📅 | MAC-1 / MSA install start time | ❌ NEW |

---

## `get_agate_info` — Firmware Versions

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `protocolVer` | `V1.11.01` | 🔧 | Protocol version | ✅ |
| `sysHdVersion` | `102` | 🔧 | Hardware version | ✅ |
| `emsDeviceVer` | `0` | 🔧 | EMS device version | ❌ |
| `ibgVersion` | `V12R02B85D00_250624` | 🔧 | IBG firmware (main inverter) | ✅ |
| `ibgMainVersion` | `""` | 🔧 | IBG main version | ❌ |
| `connType` | `3` | 🔧 | Connection type | ✅ |
| `slVersion` | `V12R02B07D00` | 🔧 | SL firmware (safety/logic) | ✅ |
| `slVersionApp` | `null` | 🔧 | SL app version | ❌ |
| `slVersionBoot` | `null` | 🔧 | SL boot version | ❌ |
| `awsVersion` | `V12R00B06D00_241306` | 🔧 | AWS comms firmware | ✅ |
| `appVersion` | `V12R00B07D00_241306` | 🔧 | App comms firmware | ✅ |
| `meterVersion` | `V12R00B11D00` | 🔧 | Meter firmware | ✅ |
| `msaModel` | `null` | 🔌 | MAC-1 / MSA model | ❌ NEW |
| `msaSn` | `null` | 🔌 | MAC-1 / MSA serial | ❌ NEW |

---

## `get_apower_info` — Per-Battery Detail

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `apowerSn` | `10050013...` | 🏷️ | aPower serial | ✅ |
| `ratedPower` | `5.0` | ⚡ | Rated power kW | ✅ |
| `ratedCapacity` | `13.6` | ⚡ | Rated capacity kWh | ✅ |
| `status` | `0` | 🔧 | Status code | ✅ |
| `remainingPower` | `3.1` | ⚡ | Current stored energy kWh | ❌ NEW |
| `soc` | `22.7` | ⚡ | Current SoC % | ✅ |
| `fpgaVer` | `V12R01B00D00` | 🔧 | FPGA firmware | ✅ |
| `dcdcVer` | `V12R02B06D00` | 🔧 | DC-DC firmware | ✅ |
| `invVer` | `V12R02B08D00` | 🔧 | Inverter firmware | ✅ |
| `bmsVer` | `V11R50B03D00` | 🔧 | BMS firmware | ✅ |
| `blVer` | `V11R06B00D00` | 🔧 | Bootloader version | ❌ NEW |
| `thVer` | `V11R02B01D00` | 🔧 | Thermal version | ❌ NEW |
| `peHwVer` | `2` | 🔧 | PE hardware version | ✅ |
| `mpptAppVer` | `""` | 🔌 | MPPT app version (aPower S) | ❌ NEW |

---

## `get_equipment_location` — Geo/Site

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `gatewayId` | `1006...` | 🏷️ | aGate serial | ✅ |
| `gatewayName` | `FHP` | 🏷️ | User-assigned name | ✅ |
| `latitude` | `0.0000000` | 📍 | Latitude | ✅ |
| `longitude` | `0.0000000` | 📍 | Longitude | ✅ |
| `postCode` | `[REDACTED]` | 📍 | Postcode | ✅ |
| `timezone` | `10.0` | 📍 | UTC offset (numeric) | ✅ |
| `zoneInfo` | `Australia/Sydney` | 📍 | IANA timezone | ✅ |
| `country` | `Australia` | 📍 | Country name | ✅ |
| `province` | `New South Wales` | 📍 | State/province | ✅ |
| `city` | `[REDACTED]` | 📍 | City | ✅ |
| `dst` | `0` | 📍 | Daylight savings active | ❌ NEW |
| `addressSecondLast` | `[REDACTED]` | 📍 | Street address | ✅ |
| `completeAddress` | `[REDACTED]` | 📍 | Full address | ✅ |
| `region` | `null` | 📍 | Region | ❌ |
| `alphaCode` | `AU,CX,CC,HM,NF` | 📍 | ISO country codes | ❌ NEW |
| `address` | `null` | 📍 | Address (unused?) | ❌ |
| `alertMessage` | `null` | 📋 | Alert message for location | ❌ NEW |

---

## `get_warranty_info` — Warranty & Installer

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `expirationTime` | `2036-07-22` | 📅 | Overall warranty expiry | ✅ |
| `throughput` | `43` | ⚡ | Total warranted throughput MWh | ✅ |
| `remainThroughput` | `37164.36` | ⚡ | Remaining throughput kWh | ✅ |
| `installerCompany` | `AULA CO.` | 🏷️ | Installer company name | ❌ NEW |
| `installerCompanyPhone` | `[REDACTED]` | 🏷️ | Installer phone | ❌ NEW |
| `installerCompanyEmail` | `[REDACTED]` | 🏷️ | Installer email | ❌ NEW |
| `equipmentSupplierPhone` | `+1 888 851 3188` | 🏷️ | FranklinWH support phone | ❌ NEW |
| `warrantyLink` | `https://...` | 📋 | Warranty document URL | ❌ NEW |
| `deviceExpirationList[].sn` | serial | 🏷️ | Per-device serial | ✅ |
| `deviceExpirationList[].model` | `aGate`/`aPower X` | 🔧 | Device model name | ✅ |
| `deviceExpirationList[].type` | `0`/`1` | 🔧 | Device type (0=aGate, 1=aPower) | ❌ NEW |
| `deviceExpirationList[].expirationTime` | `2036-07-22` | 📅 | Per-device warranty expiry | ✅ |
| `deviceExpirationList[].subModuleExpirationTime` | `2029-07-22` | 📅 | Sub-module warranty (shorter) | ❌ NEW |

---

## `get_programme_info` — VPP/Utility Programmes

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `flag` | `0` | 📋 | Programme enrolled (0=no) | ✅ |
| `programId` | `null` | 📋 | Programme ID | ❌ |
| `programName` | `null` | 📋 | Programme name | ❌ |
| `partnerName` | `null` | 📋 | VPP partner name | ❌ |
| `partnerId` | `null` | 📋 | Partner ID | ❌ |
| `programList` | `null` | 📋 | Available programmes | ❌ |
| `showRegisterBanner` | `false` | 📋 | Show VPP registration banner | ❌ NEW |
| `registerStartDate` / `EndDate` | `null` | 📅 | Registration window | ❌ |
| `vppBannerDetail` | `null` | 📋 | VPP banner content | ❌ |
| `registerGuideDesc` | `null` | 📋 | Registration guide | ❌ |

---

## `get_benefit_info` — Billing/Savings

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `carbonReduction` | `0` | 💰 | Carbon reduction kg | ❌ NEW |
| `treeConversion` | `0` | 💰 | Tree equivalent | ❌ NEW |
| `evMileageConversion` | `0` | 💰 | EV mileage equivalent | ❌ NEW |
| `fuelConversion` | `0` | 💰 | Fuel savings | ❌ NEW |
| `solarToHouseList` | `[0.678]` | 💰 | Solar→home kWh (daily) | ❌ NEW |
| `solarToGridList` | `[0.014]` | 💰 | Solar→grid kWh (daily) | ❌ NEW |
| `apowerToHouseList` | `[2.555]` | 💰 | Battery→home kWh (daily) | ❌ NEW |
| `apowerToGridList` | `[0.033]` | 💰 | Battery→grid kWh (daily) | ❌ NEW |
| `batFeedEarnList` / `batLoadEarn*` | `[0]` | 💰 | Battery earnings arrays | ❌ NEW |
| `solarFeedEarnList` / `solarLoadEarnList` | `[0]` | 💰 | Solar earnings arrays | ❌ NEW |
| `dayTimeList` | `[2026-03-23]` | 📅 | Date array for values | ❌ NEW |
| `currency` | `null` | 💰 | Currency code | ❌ NEW |
| `priceFlag` | `true` | 💰 | Pricing configured | ❌ NEW |

---

## `siteinfo` — Account/Login

| Key | Value (live) | Cat | Meaning | Used? |
|-----|-------------|-----|---------|-------|
| `userId` | `21447` | 🏷️ | User ID | ❌ |
| `email` | `[REDACTED]@...` | 🏷️ | Account email | ⚠️ PII |
| `version` | `2.0.0.250506_release` | 🔧 | App/API version | ❌ NEW |
| `distributorId` | `null` | 🏷️ | Distributor | ❌ |
| `installerId` | `null` | 🏷️ | Installer | ❌ |
| `userTypes` | `[0]` | 🏷️ | Account types (0=user) | ❌ NEW |
| `currentType` | `0` | 🏷️ | Active account type | ❌ NEW |
| `passwordUpdateFlag` | `1` | 📋 | Password change required | ❌ NEW |
| `ninetyDaysPwdUpdate` | `0` | 📋 | 90-day password rotation | ❌ NEW |
| `surveyFlag` | `0` | 📋 | Survey required | ❌ |
| `needAgreeTerm` | `false` | 📋 | ToS agreement needed | ❌ NEW |
| `failureVersion` | `null` | 🔧 | Failure version | ❌ |
| `serviceVoltageFlag` | `null` | ⚡ | Service voltage flag | ❌ |

---

## Summary

| Status | Count | Meaning |
|--------|-------|---------|
| ✅ Used | ~65 | Currently displayed or processed |
| ❌ NEW | ~55 | Available but not surfaced in discover |
| ⚠️ PII | ~5 | Personal data — redact in output |
| ❓ Unknown | ~3 | Meaning not yet determined |

### Key ❌ NEW Fields to Surface

| Field | API | Why it matters |
|-------|-----|----------------|
| `isJoinJA12` | home_gateway_list | CA JA12 programme participation |
| `benefitShowFlag` | home_gateway_list | Whether savings UI is enabled |
| `msaInstallStartDetectTime` | device_info | MAC-1 install detection |
| `msaModel` / `msaSn` | agate_info | MAC-1 model and serial |
| `mpptAppVer` | apower_info | aPower S MPPT firmware |
| `blVer` / `thVer` | apower_info | Bootloader + thermal firmware |
| `remainingPower` | apower_info | Current stored energy kWh |
| `subModuleExpirationTime` | warranty_info | Sub-module warranty (shorter!) |
| `installerCompany` + contact | warranty_info | Installer details |
| `chargingPowerLimited` | entrance_info | Charging power restriction |
| `loadOption` / `gerOption` | home_gateway_list | Load/generator config options |
| `alphaCode` | equipment_location | ISO country code list |
| `dst` | equipment_location | Daylight savings active |
