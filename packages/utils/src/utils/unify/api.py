import enum

import pydantic


class UnifyApiDnsRecordType(enum.StrEnum):
    A = 'A'


class UnifyApiDnsRecord(pydantic.BaseModel):
    object_id: str | None = pydantic.Field(default=None, validation_alias='_id', exclude=True)
    record_type: UnifyApiDnsRecordType = UnifyApiDnsRecordType.A
    key: str
    value: str
    enabled: bool = True
