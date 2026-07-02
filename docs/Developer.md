# Developer Notes

## Flow

The collector loop owns backend access and updates `StateStore`. Protocol frontends read snapshots from the store.

## SNMP

The SNMP core is intentionally small and dependency-free. It supports enough BER and PDU handling for v1/v2c GET requests:

- INTEGER
- OCTET STRING
- NULL
- OBJECT IDENTIFIER
- SEQUENCE
- GetRequest
- GetResponse
- noSuchObject

GETNEXT returns the next registered OID in numeric order. This supports basic `snmpwalk` behavior over the read-only registry.

## OID Registration

OID handlers are registered with:

```python
@oid("1.3.6.1.2.1.1.5.0", type="string", name="sysName")
def sys_name(state: UPSState) -> str:
    return state.name
```

Handlers must be read-only.

## Maintenance

Keep `CHANGELOG.md` and `TODO.md` current with every codebase update.
