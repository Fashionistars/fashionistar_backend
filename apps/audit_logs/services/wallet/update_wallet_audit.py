import os

file_path = r"c:/Users/FASHIONISTAR/OneDrive/Documenti/FASHIONISTAR_ANTAGRAVITY/fashionistar_backend/apps/audit_logs/services/wallet/wallet_audit.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if i + 1 == 216: # actor=actor, in log_escrow_hold
        new_lines.append(line)
        indent = line[:line.find('actor=actor')]
        new_lines.append(f'{indent}actor_role=getattr(actor, "user_type", None),\n')
    elif i + 1 == 245: # actor=actor, in log_escrow_release
        new_lines.append(line)
        indent = line[:line.find('actor=actor')]
        new_lines.append(f'{indent}actor_role=getattr(actor, "user_type", None),\n')
    else:
        new_lines.append(line)

# Add log_escrow_refunded at the end
new_lines.append("\n\ndef log_escrow_refunded(\n")
new_lines.append("    *, actor, wallet_id: str, amount: str, order_id: str = \"\", request=None\n")
new_lines.append(") -> None:\n")
new_lines.append("    \"\"\"Record an escrow refund to a wallet.\n\n")
new_lines.append("    Args:\n")
new_lines.append("        actor: The admin or system performing the refund.\n")
new_lines.append("        wallet_id: Wallet PK.\n")
new_lines.append("        amount: Refunded amount as string.\n")
new_lines.append("        order_id: Associated order PK.\n")
new_lines.append("        request: Django HttpRequest.\n")
new_lines.append("    \"\"\"\n")
new_lines.append("    from apps.audit_logs.services.audit import AuditService\n")
new_lines.append("    from apps.audit_logs.models import EventType, EventCategory\n\n")
new_lines.append("    AuditService.log(\n")
new_lines.append("        event_type=EventType.WALLET_ESCROW_REFUNDED,\n")
new_lines.append("        event_category=EventCategory.WALLET,\n")
new_lines.append("        action=f\"Escrow refunded: {amount} NGN for order={order_id}\",\n")
new_lines.append("        actor=actor,\n")
new_lines.append("        actor_role=getattr(actor, \"user_type\", None),\n")
new_lines.append("        resource_type=\"Wallet\",\n")
new_lines.append("        resource_id=wallet_id,\n")
new_lines.append("        request=request,\n")
new_lines.append("        new_values={\"amount\": amount, \"order_id\": order_id},\n")
new_lines.append("        is_compliance=True,\n")
new_lines.append("        retention_days=-1,\n")
new_lines.append("    )\n")

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Replacement complete.")
