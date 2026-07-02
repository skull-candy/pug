# APC PowerNet Mapping

PUG exposes a safe read-only subset of APC PowerNet OIDs. It does not implement shutdown or control/write OIDs.

| OID | Name | Source |
| --- | --- | --- |
| `1.3.6.1.2.1.1.1.0` | `sysDescr` | `APC <model> via PowerPi UPS Gateway` |
| `1.3.6.1.2.1.1.2.0` | `sysObjectID` | APC Smart-UPS identity |
| `1.3.6.1.2.1.1.5.0` | `sysName` | `UPSState.name` |
| `1.3.6.1.4.1.318.1.1.1.1.1.1.0` | APC model | `MODEL` |
| `1.3.6.1.4.1.318.1.1.1.2.2.1.0` | battery status | `STATUS` |
| `1.3.6.1.4.1.318.1.1.1.2.2.2.0` | seconds on battery | state |
| `1.3.6.1.4.1.318.1.1.1.2.2.3.0` | runtime minutes | `TIMELEFT` |
| `1.3.6.1.4.1.318.1.1.1.2.2.8.0` | battery charge percent | `BCHARGE` |
| `1.3.6.1.4.1.318.1.1.1.2.2.9.0` | battery voltage | `BATTV` |
| `1.3.6.1.4.1.318.1.1.1.2.2.10.0` | internal temperature | `ITEMP` |
| `1.3.6.1.4.1.318.1.1.1.3.2.1.0` | input voltage | `LINEV` |
| `1.3.6.1.4.1.318.1.1.1.4.2.1.0` | output voltage | `OUTPUTV` |
| `1.3.6.1.4.1.318.1.1.1.4.2.3.0` | output load percent | `LOADPCT` |
| `1.3.6.1.4.1.318.1.1.1.4.2.4.0` | output current | `OUTCURNT` |
| `1.3.6.1.4.1.318.1.1.1.4.2.5.0` | output source | `STATUS` |
| `1.3.6.1.4.1.318.1.1.1.5.2.1.0` | nominal output voltage | state/default |
| `1.3.6.1.4.1.318.1.1.1.5.2.2.0` | nominal watts | `NOMPOWER` |
| `1.3.6.1.4.1.318.1.1.1.5.2.3.0` | nominal VA | `NOMAPNT` |
| `1.3.6.1.4.1.318.1.1.1.5.2.8.0` | low battery charge threshold | config/state |
| `1.3.6.1.4.1.318.1.1.1.5.2.14.0` | low runtime threshold | config/state |

Control and shutdown OIDs should remain unregistered unless a future design includes explicit safety controls.
