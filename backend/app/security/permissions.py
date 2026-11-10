from enum import StrEnum


class Role(StrEnum):
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"
    FRAUD_ANALYST = "FRAUD_ANALYST"
    AUDITOR = "AUDITOR"


class Permission(StrEnum):
    ACCOUNT_CREATE_OWN = "account:create_own"
    ACCOUNT_CREATE_ANY = "account:create_any"
    ACCOUNT_READ_OWN = "account:read_own"
    ACCOUNT_READ_ALL = "account:read_all"
    DEPOSIT_CREATE = "deposit:create"
    TRANSFER_CREATE = "transfer:create"
    RISK_ASSESS = "risk:assess"
    MONITORING_READ = "monitoring:read"
    FRAUD_ALERT_READ = "fraud_alert:read"
    FRAUD_ALERT_RESOLVE = "fraud_alert:resolve"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    Role.CUSTOMER: frozenset({
        Permission.ACCOUNT_CREATE_OWN,
        Permission.ACCOUNT_READ_OWN,
        Permission.DEPOSIT_CREATE,
        Permission.TRANSFER_CREATE,
        Permission.RISK_ASSESS,
    }),
    Role.ADMIN: frozenset(Permission),
    Role.FRAUD_ANALYST: frozenset({
        Permission.ACCOUNT_READ_ALL,
        Permission.RISK_ASSESS,
        Permission.MONITORING_READ,
        Permission.FRAUD_ALERT_READ,
        Permission.FRAUD_ALERT_RESOLVE,
    }),
    Role.AUDITOR: frozenset({
        Permission.ACCOUNT_READ_ALL,
        Permission.MONITORING_READ,
        Permission.FRAUD_ALERT_READ,
    }),
}


def get_permissions_for_role(role: str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: Permission) -> bool:
    return permission in get_permissions_for_role(role)
