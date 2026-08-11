from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.modules.audit.domain.entities import AuditChange, JsonValue
from app.modules.audit.domain.enums import AuditChangeType, AuditValueType
from app.modules.customers.domain.entities import Customer


@dataclass(frozen=True, slots=True)
class AuditField:
    label: str
    value: object
    value_type: AuditValueType | None = None


class SensitiveFieldPolicy:
    SENSITIVE_TERMS = frozenset(
        {
            "password",
            "password_hash",
            "access_token",
            "refresh_token",
            "authorization",
            "jwt_secret",
            "secret",
            "api_key",
            "credential",
        }
    )

    def is_sensitive(self, field_path: str) -> bool:
        normalized = field_path.lower().replace("-", "_")
        return any(term in normalized for term in self.SENSITIVE_TERMS)


class AuditDiffService:
    def __init__(self, sensitive_policy: SensitiveFieldPolicy | None = None) -> None:
        self.sensitive_policy = sensitive_policy or SensitiveFieldPolicy()

    def customer_snapshot(self, customer: Customer) -> dict[str, AuditField]:
        fields = {
            "customer.customer_code": AuditField("Customer Code", customer.customer_code),
            "customer.customer_name": AuditField("Customer Name", customer.customer_name),
            "customer.tax_id": AuditField("Tax ID", customer.tax_id),
            "customer.country_code": AuditField("Country", customer.country_code),
            "customer.currency_code": AuditField("Currency", customer.currency_code),
            "customer.payment_term_id": AuditField("Payment Terms", customer.payment_term_id),
            "customer.owner_user_id": AuditField("Owner", customer.owner_user_id),
            "customer.status": AuditField("Status", customer.status, AuditValueType.ENUM),
            "customer.relationship_active": AuditField(
                "Customer Relationship Active", customer.deleted_at is None, AuditValueType.BOOLEAN
            ),
        }
        address_fields = (
            ("address_type", "Address Type", "address_type"),
            ("address_code", "Address Code", "address_code"),
            ("contact_name", "Contact Name", "contact_name"),
            ("address_line1", "Address Line 1", "address1"),
            ("address_line2", "Address Line 2", "address2"),
            ("city", "City", "city"),
            ("state", "State", "state"),
            ("postal_code", "Postal Code", "postal_code"),
            ("country_code", "Country", "country_code"),
            ("phone", "Phone", "phone"),
            ("email", "Email", "email"),
            ("is_default", "Default Address", "is_default"),
        )
        for address in customer.addresses:
            key = address.address_code
            for path_name, label, attribute in address_fields:
                fields[f"addresses[{key}].{path_name}"] = AuditField(
                    label, getattr(address, attribute)
                )
        return fields

    def diff(
        self,
        before: dict[str, AuditField] | None,
        after: dict[str, AuditField] | None,
    ) -> list[AuditChange]:
        before = before or {}
        after = after or {}
        changes: list[AuditChange] = []
        for path in sorted(before.keys() | after.keys()):
            old_field, new_field = before.get(path), after.get(path)
            old_raw = old_field.value if old_field else None
            new_raw = new_field.value if new_field else None
            if old_raw == new_raw:
                continue
            field = new_field or old_field
            if field is None:
                continue
            sensitive = self.sensitive_policy.is_sensitive(path)
            old_value = None if sensitive else self._json_value(old_raw)
            new_value = None if sensitive else self._json_value(new_raw)
            changes.append(
                AuditChange(
                    sequence_no=len(changes) + 1,
                    field_path=path,
                    field_label=field.label,
                    change_type=self._change_type(old_raw, new_raw),
                    value_type=field.value_type or self._value_type(new_raw, old_raw),
                    old_value=old_value,
                    new_value=new_value,
                    old_display_value="[REDACTED]" if sensitive else self._display(old_raw),
                    new_display_value="[REDACTED]" if sensitive else self._display(new_raw),
                    is_sensitive=sensitive,
                )
            )
        return changes

    @staticmethod
    def _change_type(old: object, new: object) -> AuditChangeType:
        if old is None:
            return AuditChangeType.ADD
        if new is None:
            return AuditChangeType.REMOVE
        return AuditChangeType.UPDATE

    @staticmethod
    def _value_type(primary: object, fallback: object) -> AuditValueType:
        value = primary if primary is not None else fallback
        if value is None:
            return AuditValueType.NULL
        if isinstance(value, bool):
            return AuditValueType.BOOLEAN
        if isinstance(value, (int, float)):
            return AuditValueType.NUMBER
        if isinstance(value, datetime):
            return AuditValueType.DATETIME
        if isinstance(value, date):
            return AuditValueType.DATE
        if isinstance(value, UUID):
            return AuditValueType.UUID
        if isinstance(value, (dict, list)):
            return AuditValueType.JSON
        return AuditValueType.STRING

    @staticmethod
    def _json_value(value: object) -> JsonValue:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (UUID, date, datetime)):
            return str(value)
        if isinstance(value, list):
            return [AuditDiffService._json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): AuditDiffService._json_value(item) for key, item in value.items()}
        return str(value)

    @staticmethod
    def _display(value: object) -> str | None:
        return None if value is None else str(value)
