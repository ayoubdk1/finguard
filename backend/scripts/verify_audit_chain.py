"""Nightly audit log hash-chain verifier. Exits non-zero on any mismatch."""

import sys

from app.db.session import SessionLocal
from app.services.audit import verify_audit_log_chain


def main() -> int:
    with SessionLocal() as db:
        errors = verify_audit_log_chain(db)
    if errors:
        print(f"AUDIT CHAIN VERIFICATION FAILED ({len(errors)} errors): {errors}", file=sys.stderr)
        return 1
    print("Audit log hash chain verified OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
