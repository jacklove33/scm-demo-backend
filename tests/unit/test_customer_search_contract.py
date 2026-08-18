from sqlalchemy.dialects import postgresql

from app.modules.customers.infrastructure.repository import customer_search_predicate


def test_customer_search_matches_code_or_name_in_the_database() -> None:
    compiled = customer_search_predicate("apple").compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()

    assert "business_partners.partner_code ilike" in sql
    assert "business_partners.partner_name ilike" in sql
    assert " or " in sql
    assert set(compiled.params.values()) == {"%apple%"}


def test_customer_search_escapes_user_supplied_sql_wildcards() -> None:
    compiled = customer_search_predicate(r"A%_\\B").compile(dialect=postgresql.dialect())

    assert set(compiled.params.values()) == {r"%A\%\_\\\\B%"}
