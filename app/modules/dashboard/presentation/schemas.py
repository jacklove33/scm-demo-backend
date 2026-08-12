from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AmountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    currency: str
    amount: Decimal


class SummaryMetricsResponse(BaseModel):
    total_po_count: int
    open_po_count: int
    on_hold_count: int
    converted_count: int
    cancelled_count: int
    amount_by_currency: list[AmountResponse]
    open_amount_by_currency: list[AmountResponse]
    on_hold_amount_by_currency: list[AmountResponse]
    converted_amount_by_currency: list[AmountResponse]
    average_po_value_by_currency: list[AmountResponse]


class SummaryChangeResponse(BaseModel):
    po_count_percent: Decimal | None
    po_amount_percent_by_currency: list["CurrencyPercentResponse"]


class CurrencyPercentResponse(BaseModel):
    currency: str
    percent: Decimal


class SummaryResponse(SummaryMetricsResponse):
    previous_period: SummaryMetricsResponse | None = None
    change: SummaryChangeResponse | None = None


class TrendPointResponse(BaseModel):
    period: str
    po_count: int
    amount_by_currency: list[AmountResponse]


class TrendResponse(BaseModel):
    granularity: str
    series: list[TrendPointResponse]


class DimensionItemResponse(BaseModel):
    key: str
    count: int
    percentage: Decimal
    amount_by_currency: list[AmountResponse]
    entity_id: UUID | None = None
    label: str | None = None


class DimensionResponse(BaseModel):
    items: list[DimensionItemResponse]


class StatusItemResponse(BaseModel):
    status: str
    count: int
    percentage: Decimal
    amount_by_currency: list[AmountResponse]


class StatusResponse(BaseModel):
    items: list[StatusItemResponse]


class SourceItemResponse(BaseModel):
    source: str
    count: int
    percentage: Decimal
    amount_by_currency: list[AmountResponse]


class SourceResponse(BaseModel):
    items: list[SourceItemResponse]


class CustomerItemResponse(BaseModel):
    customer_id: UUID
    customer_code: str
    customer_name: str
    po_count: int
    percentage: Decimal
    amount_by_currency: list[AmountResponse]


class CustomerResponse(BaseModel):
    items: list[CustomerItemResponse]


class CountryItemResponse(BaseModel):
    country_code: str
    country_name: str
    po_count: int
    percentage: Decimal
    amount_by_currency: list[AmountResponse]


class CountryResponse(BaseModel):
    items: list[CountryItemResponse]


class AttentionItemResponse(BaseModel):
    code: str
    severity: str
    title: str
    count: int
    amount_by_currency: list[AmountResponse]


class AttentionResponse(BaseModel):
    items: list[AttentionItemResponse]


class ModuleResponse(BaseModel):
    code: str
    label: str
    enabled: bool


class ModulesResponse(BaseModel):
    modules: list[ModuleResponse]


class OverviewResponse(BaseModel):
    summary: SummaryResponse
    trend: TrendResponse
    by_status: StatusResponse
    by_customer: CustomerResponse
    by_source: SourceResponse
    attention: AttentionResponse
