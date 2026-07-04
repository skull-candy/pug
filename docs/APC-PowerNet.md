# APC PowerNet Mapping

Project repository: `https://git.vns.ae/ahsan/pug`

PUG exposes a safe read-only subset of APC PowerNet OIDs. It does not implement shutdown or control/write OIDs.

| OID | Name | Source |
| --- | --- | --- |
| `1.3.6.1.2.1.1.1.0` | `sysDescr` | `APC <model> via PowerPi UPS Gateway` |
| `1.3.6.1.2.1.1.2.0` | `sysObjectID` | APC Smart-UPS identity |
| `1.3.6.1.2.1.1.5.0` | `sysName` | `UPSState.name` |
| `1.3.6.1.4.1.318.1.1.1.1.1.1.0` | APC model | `MODEL` |
| `1.3.6.1.4.1.318.1.1.1.2.1.1.0` | basic battery status | `STATUS` |
| `1.3.6.1.4.1.318.1.1.1.2.1.2.0` | basic time on battery | `CUMONBATT` as TimeTicks |
| `1.3.6.1.4.1.318.1.1.1.2.1.3.0` | last battery replacement date | `BATTDATE` |
| `1.3.6.1.4.1.318.1.1.1.2.2.1.0` | battery charge percent | `BCHARGE` as Gauge32 |
| `1.3.6.1.4.1.318.1.1.1.2.2.2.0` | internal temperature | `ITEMP` |
| `1.3.6.1.4.1.318.1.1.1.2.2.3.0` | runtime remaining | `TIMELEFT` as TimeTicks |
| `1.3.6.1.4.1.318.1.1.1.2.2.4.0` | replace battery indicator | `STATUS` |
| `1.3.6.1.4.1.318.1.1.1.2.2.8.0` | battery voltage | `BATTV` |
| `1.3.6.1.4.1.318.1.1.1.3.2.1.0` | input voltage | `LINEV` |
| `1.3.6.1.4.1.318.1.1.1.3.2.4.0` | input frequency | `LINEFREQ` |
| `1.3.6.1.4.1.318.1.1.1.3.3.1.0` | high precision input voltage | `LINEV * 10` |
| `1.3.6.1.4.1.318.1.1.1.3.3.4.0` | high precision input frequency | `LINEFREQ * 10` |
| `1.3.6.1.4.1.318.1.1.1.4.1.1.0` | output status | `STATUS` |
| `1.3.6.1.4.1.318.1.1.1.4.2.1.0` | output voltage | `OUTPUTV` |
| `1.3.6.1.4.1.318.1.1.1.4.2.2.0` | output frequency | `LINEFREQ` |
| `1.3.6.1.4.1.318.1.1.1.4.2.3.0` | output load percent | `LOADAPNT` fallback `LOADPCT` |
| `1.3.6.1.4.1.318.1.1.1.4.2.4.0` | output current | `OUTCURNT` |
| `1.3.6.1.4.1.318.1.1.1.4.2.5.0` | output source | `STATUS` |
| `1.3.6.1.4.1.318.1.1.1.4.3.1.0` | high precision output voltage | `OUTPUTV * 10` |
| `1.3.6.1.4.1.318.1.1.1.4.3.2.0` | high precision output frequency | `LINEFREQ * 10` |
| `1.3.6.1.4.1.318.1.1.1.4.3.3.0` | high precision output load | `LOADAPNT * 10` fallback `LOADPCT * 10` |
| `1.3.6.1.4.1.318.1.1.1.4.3.4.0` | high precision output current | `OUTCURNT * 10` |
| `1.3.6.1.4.1.318.1.1.1.5.2.1.0` | nominal output voltage | state/default |
| `1.3.6.1.4.1.318.1.1.1.5.2.2.0` | nominal watts | `NOMPOWER` |
| `1.3.6.1.4.1.318.1.1.1.5.2.3.0` | nominal VA | `NOMAPNT` |
| `1.3.6.1.4.1.318.1.1.1.5.2.8.0` | low battery charge threshold | config/state |
| `1.3.6.1.4.1.318.1.1.1.5.2.14.0` | low runtime threshold | config/state |

## Enum Values

| Value | APC battery status |
| --- | --- |
| `1` | unknown |
| `2` | normal |
| `3` | low/on battery |
| `4` | replace battery |

| Value | APC output source |
| --- | --- |
| `1` | unknown |
| `2` | on line |
| `3` | on battery |
| `4` | smart boost |
| `6` | bypass |

These values are covered by tests for the QNAP-facing states observed so far. Additional firmware captures should still be checked when available.

## PUG Raw Status Extension

PUG exposes known `apcaccess` raw keys as read-only text under:

`1.3.6.1.4.1.318.1.1.1.99.1`

Each raw row has:

- `<row>.1.0`: key name.
- `<row>.2.0`: value.

This subtree is for observability only. It does not implement control or shutdown behavior.

Control and shutdown OIDs should remain unregistered unless a future design includes explicit safety controls.
