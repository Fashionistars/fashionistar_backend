# apps/client/services/client_provisioning_service.py
"""
ClientProvisioningService — Auto-provision a blank ClientProfile.

Called by the EventBus `user.registered` handler (role=client).
Idempotent: calling .provision() multiple times is safe.
"""
import logging

logger = logging.getLogger(__name__)


class ClientProvisioningService:
    """
    Idempotent provisioner for the client domain.

    Usage:
        ClientProvisioningService.provision(user)
    """

    @staticmethod
    def provision(user) -> "ClientProfile":  # noqa: F821
        """
        Create a blank ClientProfile for `user` if one doesn't exist.

        Args:
            user: UnifiedUser instance with role='client'.

        Returns:
            ClientProfile — either newly created or existing.
        """
        from apps.client.models import ClientProfile

        profile, created = ClientProfile.objects.get_or_create(user=user)

        if created:
            logger.info(
                "ClientProvisioningService: created ClientProfile for user %s",
                user.pk,
            )
        else:
            logger.debug(
                "ClientProvisioningService: ClientProfile already exists for user %s",
                user.pk,
            )

        return profile
