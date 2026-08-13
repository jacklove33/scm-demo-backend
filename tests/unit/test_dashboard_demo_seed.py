from collections import Counter
from decimal import Decimal

from app.modules.customer_pos.domain.enums import CustomerPoSource, CustomerPoStatus
from scripts.seed_dashboard_demo import PREFIX, amount_components, build_specs, stable_uuid


def test_demo_specs_are_deterministic_complete_and_dashboard_eligible() -> None:
    first = build_specs()
    second = build_specs()

    assert first == second
    assert len(first) == 48
    assert len({spec.po_number for spec in first}) == 48
    assert all(spec.po_number.startswith(PREFIX) for spec in first)
    assert all(spec.po_date is not None for spec in first)
    assert all(len(spec.country_code) == 2 for spec in first)
    assert all(len(spec.currency_code) == 3 for spec in first)
    assert {spec.status for spec in first} == set(CustomerPoStatus)
    assert {spec.source for spec in first} == set(CustomerPoSource)
    assert len({spec.country_code for spec in first}) == 8
    assert len({spec.customer_code for spec in first}) == 4
    assert stable_uuid(first[0].po_number) == stable_uuid(second[0].po_number)


def test_demo_distributions_and_line_amounts_are_business_like() -> None:
    specs = build_specs()
    statuses = Counter(spec.status for spec in specs)
    sources = Counter(spec.source for spec in specs)
    customers = Counter(spec.customer_code for spec in specs)

    assert statuses[CustomerPoStatus.CONVERTED] == 15
    assert statuses[CustomerPoStatus.ON_HOLD] == 5
    assert statuses[CustomerPoStatus.CANCELLED] == 2
    assert sources == {
        CustomerPoSource.EDI: 17,
        CustomerPoSource.API: 12,
        CustomerPoSource.IMPORT: 10,
        CustomerPoSource.MANUAL: 9,
    }
    assert sorted(customers.values(), reverse=True) == [17, 12, 11, 8]

    for spec in specs:
        total = Decimal("0")
        for line_index in range(spec.line_count):
            quantity, unit_price = amount_components(spec, (line_index + 1) * 10)
            assert quantity > 0
            assert unit_price >= 0
            total += quantity * unit_price
        assert total > 0
