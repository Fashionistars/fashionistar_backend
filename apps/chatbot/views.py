"""
Chatbot Views for Fashionistar.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import ChatbotSession, Conversation, Message
from .serializers import (
    ChatbotSessionSerializer, ConversationSerializer, ConversationListSerializer,
    MessageSerializer, SendMessageRequestSerializer,
    SendMessageResponseSerializer, StartSessionResponseSerializer,
    StyleAssessmentRequestSerializer, SizeRecommendationRequestSerializer,
    ProductInquiryRequestSerializer, BespokeConsultationRequestSerializer
)
from .services import ClientChatbotService, VendorChatbotService

User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class BaseChatbotViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class ClientChatbotViewSet(viewsets.GenericViewSet):
    """
    API for client-facing chatbot services.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_chatbot_service(self):
        return ClientChatbotService(self.request.user)
    
    @extend_schema(
        summary="Start client chatbot session",
        description="Initialize or get active chatbot session for client",
        responses={200: StartSessionResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def start_session(self, request):
        try:
            chatbot_service = self.get_chatbot_service()
            session = chatbot_service.get_or_create_session()
            greeting_response = chatbot_service.ai_service.response_matcher.get_greeting_response()
            
            greeting_message = None
            if greeting_response:
                greeting_message = {
                    'content': greeting_response.response_text,
                    'message_type': 'text',
                    'response_data': greeting_response.response_data,
                    'ai_confidence': 1.0,
                    'processing_time': 0.0
                }
            
            quick_replies = chatbot_service.get_quick_replies()
            
            return Response({
                'session': ChatbotSessionSerializer(session).data,
                'greeting_message': greeting_message,
                'quick_replies': quick_replies
            })
        except Exception as e:
            return Response(
                {'error': f'Error starting session: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Send message to chatbot",
        description="Send client message and get chatbot response",
        request=SendMessageRequestSerializer,
        responses={200: SendMessageResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_message(self, request):
        serializer = SendMessageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            result = chatbot_service.process_message(
                message=serializer.validated_data['message'],
                context=serializer.validated_data.get('context')
            )
            return Response(result)
        except Exception as e:
            return Response(
                {'error': f'Error processing message: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Start style assessment",
        description="Initialize style assessment questionnaire for the client",
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def start_style_assessment(self, request):
        try:
            chatbot_service = self.get_chatbot_service()
            assessment = chatbot_service.start_style_assessment()
            return Response(assessment)
        except Exception as e:
            return Response(
                {'error': f'Error starting style assessment: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Submit style assessment responses",
        description="Submit style preferences and get outfits recommendations",
        request=StyleAssessmentRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def submit_style_assessment(self, request):
        serializer = StyleAssessmentRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            result = chatbot_service.process_style_response(serializer.validated_data)
            return Response(result)
        except Exception as e:
            return Response(
                {'error': f'Error submitting style assessment: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Request bespoke consultation",
        description="Initiate request for custom tailoring consultation",
        request=BespokeConsultationRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def request_appointment(self, request):
        serializer = BespokeConsultationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            result = chatbot_service.request_appointment(
                specialty=serializer.validated_data.get('tailoring_type'),
                preferred_time=serializer.validated_data.get('preferred_time')
            )
            return Response(result)
        except Exception as e:
            return Response(
                {'error': f'Error requesting consultation: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def end_session(self, request):
        try:
            chatbot_service = self.get_chatbot_service()
            chatbot_service.end_session()
            return Response({'status': 'Session completed successfully.'})
        except Exception as e:
            return Response(
                {'error': f'Error ending session: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VendorChatbotViewSet(viewsets.GenericViewSet):
    """
    API for vendor-facing chatbot services.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_chatbot_service(self):
        return VendorChatbotService(self.request.user)
    
    @extend_schema(
        summary="Start vendor chatbot session",
        description="Initialize or get active chatbot session for vendor",
        responses={200: StartSessionResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def start_session(self, request):
        try:
            chatbot_service = self.get_chatbot_service()
            session = chatbot_service.get_or_create_session()
            greeting_response = chatbot_service.ai_service.response_matcher.get_greeting_response()
            
            greeting_message = None
            if greeting_response:
                greeting_message = {
                    'content': greeting_response.response_text,
                    'message_type': 'text',
                    'response_data': greeting_response.response_data,
                    'ai_confidence': 1.0,
                    'processing_time': 0.0
                }
            
            quick_replies = chatbot_service.get_quick_replies()
            
            return Response({
                'session': ChatbotSessionSerializer(session).data,
                'greeting_message': greeting_message,
                'quick_replies': quick_replies
            })
        except Exception as e:
            return Response(
                {'error': f'Error starting session: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Send message to chatbot",
        description="Send vendor message and get chatbot response",
        request=SendMessageRequestSerializer,
        responses={200: SendMessageResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_message(self, request):
        serializer = SendMessageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            result = chatbot_service.process_message(
                message=serializer.validated_data['message'],
                context=serializer.validated_data.get('context')
            )
            return Response(result)
        except Exception as e:
            return Response(
                {'error': f'Error processing message: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Request product catalog support",
        description="Get recommendation and categorization for new products",
        request=SizeRecommendationRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def diagnosis_support(self, request):
        serializer = SizeRecommendationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            vendor_info = {
                'height_cm': serializer.validated_data.get('height_cm'),
                'gender': serializer.validated_data.get('gender'),
                'fit_preference': serializer.validated_data.get('fit_preference'),
                'prior_purchases': serializer.validated_data.get('prior_purchases', [])
            }
            
            support = chatbot_service.get_catalog_support(
                products=serializer.validated_data['measurements'],
                vendor_info=vendor_info
            )
            return Response(support)
        except Exception as e:
            return Response(
                {'error': f'Error generating catalog support: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Request product specifications",
        description="Get fabric, pricing and packaging details",
        request=ProductInquiryRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def medication_info(self, request):
        serializer = ProductInquiryRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            vendor_context = {
                'size': serializer.validated_data.get('client_size'),
                'height': serializer.validated_data.get('client_height'),
                'fabric_preferences': serializer.validated_data.get('fabric_preferences', []),
                'similar_products': serializer.validated_data.get('similar_products', [])
            }
            
            info = chatbot_service.get_product_info(
                product_sku=serializer.validated_data['product_sku'],
                vendor_context=vendor_context
            )
            return Response(info)
        except Exception as e:
            return Response(
                {'error': f'Error loading product specs: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Get tailoring guideline",
        description="Fetch custom tailoring assembly and pattern details",
        parameters=[
            OpenApiParameter('condition', OpenApiTypes.STR, description="Garment Type"),
            OpenApiParameter('severity', OpenApiTypes.STR, description="Complexity", default="moderate")
        ],
        responses={200: dict}
    )
    @action(detail=False, methods=['get'])
    def treatment_protocol(self, request):
        condition = request.query_params.get('condition')
        severity = request.query_params.get('severity', 'moderate')
        
        if not condition:
            return Response({'error': 'condition parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            protocol = chatbot_service.get_treatment_protocol(condition, severity)
            return Response(protocol)
        except Exception as e:
            return Response(
                {'error': f'Error fetching tailoring guidelines: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Search fashion references",
        description="Search design ideas, trends and fabric references",
        parameters=[
            OpenApiParameter('query', OpenApiTypes.STR, description="Search Query"),
            OpenApiParameter('specialty', OpenApiTypes.STR, description="Specialty Niche", required=False)
        ],
        responses={200: dict}
    )
    @action(detail=False, methods=['get'])
    def search_references(self, request):
        query = request.query_params.get('query')
        specialty = request.query_params.get('specialty')
        
        if not query:
            return Response({'error': 'query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            results = chatbot_service.search_medical_references(query, specialty)
            return Response(results)
        except Exception as e:
            return Response(
                {'error': f'Error searching fashion references: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ChatbotSessionViewSet(BaseChatbotViewSet):
    queryset = ChatbotSession.objects.all()
    serializer_class = ChatbotSessionSerializer


class ConversationViewSet(BaseChatbotViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        conversation = self.get_object()
        messages = conversation.messages.all().order_by('created_at')
        
        return Response({
            'conversation': ConversationListSerializer(conversation).data,
            'messages': MessageSerializer(messages, many=True).data,
            'total_messages': messages.count(),
            'has_more': False
        })


class MessageViewSet(BaseChatbotViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer