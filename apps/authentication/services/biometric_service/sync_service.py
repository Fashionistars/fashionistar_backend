# apps/authentication/services/biometric_service/sync_service.py

import logging
from fido2.server import Fido2Server
from fido2.webauthn import UserVerificationRequirement, AuthenticatorAttachment
from django.conf import settings
from django.db import transaction

from apps.authentication.models import BiometricCredential, UnifiedUser
from apps.audit_logs.services.authentication import auth_audit

# Configure logger for application-level events
logger = logging.getLogger("application")

# FIDO2 Server Initialization
# Relying Party (RP) configuration sourced from settings with secure defaults
RP_ID = getattr(settings, "FIDO2_RP_ID", "localhost")
RP_NAME = getattr(settings, "FIDO2_RP_NAME", "Fashionistar")
server = Fido2Server(
    {"id": RP_ID, "name": RP_NAME},
    verify_origin=lambda x: True,  # TODO: Implement strict origin check for production environments
)


class SyncBiometricService:
    """
    Synchronous Service for WebAuthn / FIDO2 Authentication.

    This service handles the lifecycle of biometric credentials, including
    generation of registration/authentication options and verification of
    responses from authenticators.
    """

    @staticmethod
    def generate_registration_options(user: UnifiedUser):
        """
        Generates WebAuthn registration options for a user.

        Args:
            user (UnifiedUser): The user attempting to register a biometric device.

        Returns:
            tuple: A pair containing the (options, state) required by the fido2 library.

        Raises:
            Exception: If registration options generation fails.
        """
        try:
            # Exclude already registered credentials to prevent duplicate enrollment
            credentials = list(BiometricCredential.objects.filter(user=user))
            exclude_list = [
                {"type": "public-key", "id": cred.credential_id} for cred in credentials
            ]

            user_data = {
                "id": str(user.id).encode("utf-8"),
                "name": user.email or str(user.phone),
                "displayName": f"{user.first_name} {user.last_name}".strip() or "User",
            }

            options, state = server.register_begin(
                user_data,
                credentials=exclude_list,
                user_verification=UserVerificationRequirement.PREFERRED,
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            )
            return options, state
        except Exception as e:
            logger.error(
                "❌ Biometric Reg Options Error for user=%s: %s", user.email, e
            )
            raise Exception("Failed to generate biometric options.")

    @staticmethod
    def verify_registration_response(
        user: UnifiedUser, request, response_data, state, device_name="Unknown"
    ):
        """
        Verifies the biometric registration response and persists the credential.

        Args:
            user (UnifiedUser): The user registering the device.
            request (HttpRequest): The current request context for auditing.
            response_data (dict): The registration response data from the client.
            state (dict): The registration state saved in the session.
            device_name (str, optional): A friendly name for the device. Defaults to "Unknown".

        Returns:
            bool: True if registration was successful.

        Raises:
            Exception: If verification fails or data is invalid.
        """
        try:
            # Complete registration via FIDO2 server
            auth_data = server.register_complete(state, response_data)

            with transaction.atomic():
                # Persist the new biometric credential
                BiometricCredential.objects.create(
                    user=user,
                    credential_id=auth_data.credential_data.credential_id,
                    public_key=auth_data.credential_data.public_key,
                    sign_count=auth_data.sign_count,
                    device_name=device_name,
                )

                # ── Audit Dispatch ───────────────────────────────────────────
                # Log the successful registration of a new biometric device.
                transaction.on_commit(
                    lambda: auth_audit.log_biometric_registered(
                        actor=user,
                        request=request,
                        device_name=device_name,
                    )
                )

            logger.info("✅ Biometric Credential Registered: user=%s device=%s", user.email, device_name)
            return True
        except Exception as e:
            logger.error("❌ Biometric Reg Verify Error for user=%s: %s", user.email, e)
            raise Exception("Invalid biometric data.")

    @staticmethod
    def generate_auth_options(user: UnifiedUser):
        """
        Generates WebAuthn authentication options for a user.

        Args:
            user (UnifiedUser): The user attempting biometric login.

        Returns:
            tuple: A pair containing the (options, state) for fido2 authentication.

        Raises:
            Exception: If no credentials found or generation fails.
        """
        try:
            credentials = list(BiometricCredential.objects.filter(user=user))
            if not credentials:
                raise Exception("No biometric credentials found.")

            allow_list = [
                {"type": "public-key", "id": cred.credential_id} for cred in credentials
            ]

            options, state = server.authenticate_begin(
                allow_list, user_verification=UserVerificationRequirement.PREFERRED
            )
            return options, state
        except Exception as e:
            logger.error("❌ Biometric Auth Options Error for user=%s: %s", user.email, e)
            raise

    @staticmethod
    def verify_auth_response(user: UnifiedUser, request, response_data, state):
        """
        Verifies the biometric authentication response.

        Args:
            user (UnifiedUser): The user attempting to authenticate.
            request (HttpRequest): The current request context for auditing.
            response_data (dict): The authentication response from the client.
            state (dict): The authentication state saved in the session.

        Returns:
            bool: True if authentication was successful.

        Raises:
            Exception: If verification fails.
        """
        try:
            credentials = list(BiometricCredential.objects.filter(user=user))
            if not credentials:
                raise Exception("No credentials found for user.")

            # Identify the credential used and complete authentication
            server.authenticate_complete(state, credentials, response_data)

            # ── Audit Dispatch ───────────────────────────────────────────
            # Record successful biometric authentication.
            transaction.on_commit(
                lambda: auth_audit.log_biometric_auth(
                    actor=user,
                    request=request,
                    success=True,
                )
            )

            logger.info("✅ Biometric Login Success: user=%s", user.email)
            return True
        except Exception as e:
            logger.error("❌ Biometric Auth Verify Error for user=%s: %s", user.email, e)

            # Record failed biometric authentication attempt
            auth_audit.log_biometric_auth(
                actor=user,
                request=request,
                success=False,
                reason=str(e),
            )
            raise Exception("Biometric authentication failed.")
