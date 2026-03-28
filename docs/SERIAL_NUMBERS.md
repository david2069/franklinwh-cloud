# Hardware Serial Number Formats

FranklinWH explicitly encodes product hierarchy, date codes, and revisions directly into their 20-character hardware serial numbers. This registry is useful for physical audits and identifying specific physical units across cloud boundaries.

## Global Pattern
All primary system components natively adhere to a strict **20-character** alphanumeric length. 

Despite some legacy documentation showing conceptual `10060006XXXXXXXXXXXXX` (21-character) masks, actual manufactured barcodes (and Cloud API payloads) are uniformly fixed to 20 characters with no variances.

### Breakdown Structure
The serial maps perfectly into an `[8] + [4] + [4] + [4]` block sequence:
`PPPPPPPP-MRRV-YYWW-UUUU`

| Block | Characters | Description | Example |
| :--- | :--- | :--- | :--- |
| **P** (Prefix) | 8 | Main Component Family Identity | `10060006` (aGate) |
| **M/R/V** (Sub-Model) | 4 | Alphanumeric Revision/SKU Code | `A00X` (aPower X) |
| **Y/W** (Date Code) | 4 | Build Date: Year (`YY`) and Week (`WW`) | `2343` (Week 43, 2023) |
| **U** (Unit Sequence) | 4 | Manufacturing Sequence Count | `0165` (165th unit) |

> [!NOTE] 
> E.g., a Power Electronics (PE) Inverter serial of `10050013AXXXXXXXXX` decodes to an aPower X built in late October 2023.

## Known Family Prefixes

### **aGate** (Main Gateway)
* **Prefix:** `1006...` (e.g., `10060006`)
* **Length:** 20 Characters.
* *Example:* `10060006AXXXXXXXXX`

### **aPower** (Battery + PCS)
* **Prefix:** `1005...` (e.g., `10050013`)
* **Length:** 20 Characters.
* **Component Note:** The aPower physically contains multiple sub-components (like the standalone Battery pack and the PE / DC-DC Inverter). The `1005` prefix is universally used for the top-level unit enclosure and internal Power Electronics (PE) board alike.
* *Example:* `10050013AXXXXXXXXX`

### **Smart Circuits** (Accessories)
* **Prefix:** `1007...` (e.g., `10070022`)
* **Length:** 20 Characters.
* *Example:* `10070022A00F23390067`

---

*This guide acts as a reverse-engineered reference to properly cast or validate FranklinWH strings locally without relying upon API calls directly.*
