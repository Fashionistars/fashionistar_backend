# apps/support/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model

from apps.admin_backend.permissions import IsAdminUser
from apps.support.models.support_ticket import SupportTicket
from apps.support.admin_backend.serializers import AdminAssignTicketSerializer, AdminResolveTicketSerializer
from apps.support.admin_backend.services import admin_assign_ticket, admin_resolve_ticket

User = get_user_model()
logger = logging.getLogger(__name__)

class AdminAssignTicketView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, ticket_id):
        try:
            ticket = SupportTicket.objects.get(id=ticket_id)
        except SupportTicket.DoesNotExist:
            return Response({"status": "error", "message": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = AdminAssignTicketSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            assignee = User.objects.get(id=serializer.validated_data["assignee_id"])
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Assignee user not found."}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            admin_assign_ticket(
                ticket_id=ticket_id,
                admin_user=request.user,
                assignee_user=assignee,
            )
            return Response({"status": "success", "message": "Ticket assigned successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminResolveTicketView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, ticket_id):
        try:
            ticket = SupportTicket.objects.get(id=ticket_id)
        except SupportTicket.DoesNotExist:
            return Response({"status": "error", "message": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = AdminResolveTicketSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            admin_resolve_ticket(
                ticket_id=ticket_id,
                admin_user=request.user,
                notes=serializer.validated_data["notes"],
            )
            return Response({"status": "success", "message": "Ticket resolved successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
