from pug.collector.simulator import simulator_state
from pug.snmp.registry import OidRegistry


def test_registry_hit_and_miss() -> None:
    local = OidRegistry()

    def handler(state):
        return state.model

    local.register("1.2.3.0", "string", "example", handler)

    hit = local.resolve("1.2.3.0")
    assert hit is not None
    assert hit.handler(simulator_state()) == "Smart-UPS 3000"
    assert local.resolve("1.2.4.0") is None


def test_registry_next_after_uses_numeric_oid_order() -> None:
    local = OidRegistry()
    local.register("1.3.6.1.2.1.1.10.0", "string", "ten", lambda state: "ten")
    local.register("1.3.6.1.2.1.1.2.0", "string", "two", lambda state: "two")

    assert local.next_after("1.3.6.1.2.1.1.1.0").oid == "1.3.6.1.2.1.1.2.0"
    assert local.next_after("1.3.6.1.2.1.1.2.0").oid == "1.3.6.1.2.1.1.10.0"
    assert local.next_after("1.3.6.1.2.1.1.10.0") is None
