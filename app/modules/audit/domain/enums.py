from enum import StrEnum


class AuditActorType(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    API_CLIENT = "API_CLIENT"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    RESTORE = "RESTORE"
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    STATUS_CHANGE = "STATUS_CHANGE"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    LOGIN_FAILED = "LOGIN_FAILED"
    EDI_SEND = "EDI_SEND"
    EDI_RESEND = "EDI_RESEND"
    EDI_RECEIVE = "EDI_RECEIVE"
    EDI_ACK_RECEIVED = "EDI_ACK_RECEIVED"
    EDI_FAILED = "EDI_FAILED"
    ASSIGN = "ASSIGN"
    UNASSIGN = "UNASSIGN"
    PERMISSION_CHANGE = "PERMISSION_CHANGE"
    ROLE_CHANGE = "ROLE_CHANGE"
    GROUP_CHANGE = "GROUP_CHANGE"


class AuditSource(StrEnum):
    UI = "UI"
    API = "API"
    IMPORT = "IMPORT"
    EDI = "EDI"
    SYSTEM = "SYSTEM"
    JOB = "JOB"
    ADMIN = "ADMIN"


class AuditStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class AuditChangeType(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"


class AuditValueType(StrEnum):
    STRING = "STRING"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    UUID = "UUID"
    ENUM = "ENUM"
    JSON = "JSON"
    NULL = "NULL"
