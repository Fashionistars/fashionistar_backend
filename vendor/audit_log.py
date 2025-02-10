# ======================= LATER TO USE ======================================

from auditlog.registry import auditlog
from auditlog.models import AuditlogHistoryField

class Vendor(models.Model):
    history = AuditlogHistoryField()
    # ... existing fields ...

# Register for auditing
auditlog.register(Vendor)
auditlog.register(BankAccountDetails)