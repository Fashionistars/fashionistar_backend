"""
Vendor Chatbot Service for Fashionistar.
"""

from typing import Dict, List, Optional, Any
from django.utils import timezone
from .base_chatbot import BaseChatbotService
from .ai_integration import AIIntegrationService


class VendorChatbotService(BaseChatbotService):
    """
    Dedicated chatbot service for vendor users.
    """
    
    def __init__(self, user):
        super().__init__(user, 'vendor')
        self.ai_service = AIIntegrationService('vendor')
    
    def process_message(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        user_message = self.save_user_message(message)
        conversation_history = self.get_conversation_history(15)
        
        ai_response = self.ai_service.process_message(
            message=message,
            context=context,
            conversation_history=conversation_history
        )
        
        bot_message = self.save_bot_message(
            content=ai_response['content'],
            message_type=ai_response.get('message_type', 'text'),
            response_data=ai_response.get('response_data', {}),
            ai_confidence=ai_response.get('ai_confidence'),
            processing_time=ai_response.get('processing_time')
        )
        
        self._update_vendor_context(ai_response, context)
        
        return {
            'response': ai_response,
            'user_message_id': str(user_message.id),
            'bot_message_id': str(bot_message.id),
            'conversation_id': str(self.current_conversation.id),
            'session_id': str(self.current_session.id)
        }
    
    def get_quick_replies(self, context: Optional[Dict] = None) -> List[Dict]:
        base_replies = [
            {'title': 'Catalog Guide', 'payload': 'catalog_guide'},
            {'title': 'Tailoring Guidelines', 'payload': 'tailoring_guidelines'},
            {'title': 'Fabric Details', 'payload': 'fabric_details'},
            {'title': 'Fashion Trends', 'payload': 'fashion_trends'}
        ]
        
        if context:
            if context.get('vendor_case'):
                base_replies.extend([
                    {'title': 'Review Catalog Case', 'payload': 'case_review'},
                    {'title': 'Sizing Options', 'payload': 'sizing_options'}
                ])
            
            if context.get('product_query'):
                base_replies.extend([
                    {'title': 'Pricing Advice', 'payload': 'pricing_advice'},
                    {'title': 'Material Care', 'payload': 'material_care'}
                ])
        
        return base_replies
    
    def get_catalog_support(self, products: List[str], vendor_info: Dict = None) -> Dict[str, Any]:
        """
        Provide catalog and design analysis support for vendors.
        """
        if self.current_conversation:
            self.current_conversation.conversation_type = 'size_recommendation'
            self.current_conversation.save()
        
        self._update_session_context({
            'catalog_request': {
                'products': products,
                'vendor_info': vendor_info,
                'requested_at': str(timezone.now())
            }
        })
        
        catalog_analysis = self._analyze_products_for_catalog(products, vendor_info)
        
        return {
            'content': 'Based on the design details provided, here is our custom catalog analysis and pricing advisory:',
            'message_type': 'text',
            'response_data': {
                'differential_diagnoses': catalog_analysis['categories'],
                'recommended_tests': catalog_analysis['pricing_tiers'],
                'treatment_options': catalog_analysis['materials'],
                'guidelines': catalog_analysis['guidelines'],
                'quick_replies': [
                    {'title': 'Fabric Incompatibilities', 'payload': 'fabric_incompatibilities'},
                    {'title': 'Sizing Chart Check', 'payload': 'sizing_chart_check'},
                    {'title': 'Generate Style Mockup', 'payload': 'generate_style_mockup'}
                ]
            }
        }
    
    def get_product_info(self, product_sku: str, vendor_context: Dict = None) -> Dict[str, Any]:
        """
        Get product details and specs for the vendor.
        """
        self._update_session_context({
            'product_query': {
                'product_sku': product_sku,
                'vendor_context': vendor_context,
                'queried_at': str(timezone.now())
            }
        })
        
        product_details = self._get_product_spec_details(product_sku, vendor_context)
        
        return {
            'content': f'Product specifications for SKU {product_sku}:',
            'message_type': 'text',
            'response_data': {
                'medication_details': product_details,
                'quick_replies': [
                    {'title': 'Fabric Incompatibilities', 'payload': f'interactions_{product_sku}'},
                    {'title': 'Standard Pricing', 'payload': f'pricing_{product_sku}'},
                    {'title': 'Care Instructions', 'payload': f'care_{product_sku}'},
                    {'title': 'Packaging Guidelines', 'payload': f'packaging_{product_sku}'}
                ]
            }
        }
    
    def get_treatment_protocol(self, garment_type: str, complexity: str = 'moderate') -> Dict[str, Any]:
        """
        Get tailoring/garment assembly protocols.
        """
        self._update_session_context({
            'treatment_protocol_request': {
                'condition': garment_type,
                'severity': complexity,
                'requested_at': str(timezone.now())
            }
        })
        
        protocol = self._get_tailoring_protocol_details(garment_type, complexity)
        
        return {
            'content': f'Tailoring instructions for {garment_type} (Complexity: {complexity}):',
            'message_type': 'text',
            'response_data': {
                'protocol': protocol,
                'quick_replies': [
                    {'title': 'Next Assembly Step', 'payload': 'next_step'},
                    {'title': 'Stitching Risks', 'payload': 'potential_complications'},
                    {'title': 'Quality Audit Check', 'payload': 'treatment_followup'}
                ]
            }
        }
    
    def search_medical_references(self, query: str, specialty: str = None) -> Dict[str, Any]:
        """
        Search design guides, fabric catalogs, and fashion trends.
        """
        self._update_session_context({
            'medical_search': {
                'query': query,
                'specialty': specialty,
                'searched_at': str(timezone.now())
            }
        })
        
        search_results = self._search_fashion_trends(query, specialty)
        
        return {
            'content': f'Search results for "{query}":',
            'message_type': 'text',
            'response_data': {
                'search_results': search_results,
                'total_results': len(search_results),
                'quick_replies': [
                    {'title': 'Refine Search', 'payload': 'refine_search'},
                    {'title': 'Related Fabrics', 'payload': 'related_references'},
                    {'title': 'Styling Rules', 'payload': 'clinical_guidelines'}
                ]
            }
        }
    
    def _analyze_products_for_catalog(self, products: List[str], vendor_info: Dict = None) -> Dict[str, Any]:
        common_categories = [
            {
                'name': 'Premium Outerwear',
                'probability': 0.8,
                'symptoms_match': ['Coats', 'Jackets'],
                'severity': 'High Quality'
            },
            {
                'name': 'Bespoke Evening Wear',
                'probability': 0.6,
                'symptoms_match': ['Gowns', 'Suits'],
                'severity': 'Custom Tailored'
            }
        ]
        
        recommended_tiers = [
            'Basic Tier ($50 - $100)',
            'Standard Premium Tier ($100 - $250)',
            'Bespoke Tailoring Tier (>$250)'
        ]
        
        materials = [
            'Premium Wool Blend',
            'Organic Cotton Canvas',
            'Silk Crepe lining'
        ]
        
        guidelines = [
            'Ensure fabric weights match seasonal collection targets',
            'Audit size charts to maintain consistent garment tolerance',
            'Provide high-resolution flat sketches for buyer transparency'
        ]
        
        return {
            'categories': common_categories,
            'pricing_tiers': recommended_tiers,
            'materials': materials,
            'guidelines': guidelines
        }
    
    def _get_product_spec_details(self, product_sku: str, vendor_context: Dict = None) -> Dict[str, Any]:
        return {
            'generic_name': product_sku,
            'brand_names': ['Brand Signature', 'Collection Line'],
            'dosage_forms': ['Regular Fit', 'Slim Fit', 'Oversized'],
            'standard_dosage': {
                'adult': '$150.00 Standard retail',
                'pediatric': '$250.00 Custom tailored bespoke'
            },
            'contraindications': ['Do not machine wash', 'Do not tumble dry'],
            'side_effects': ['Iron at low temp only', 'Store in dry breathable bag'],
            'interactions': ['Delicate fabrics', 'Wool blends'],
            'pregnancy_category': 'A',
            'monitoring_required': ['Material QC test', 'Sizing audit']
        }
    
    def _get_tailoring_protocol_details(self, garment_type: str, complexity: str) -> Dict[str, Any]:
        return {
            'first_line_treatment': ['Wool Tweed', 'Silk Lining'],
            'second_line_treatment': ['Cotton Canvas interfacing', 'Polyester thread'],
            'duration': '7-10 Days assembly',
            'monitoring': ['Sleeve length alignment', 'Stitch density audit'],
            'follow_up': 'Final fit test review after 48h',
            'complications_to_watch': ['Seam puckering', 'Hem misalignment'],
            'patient_education': ['Care tags instruction', 'Customer measurements confirmation']
        }
    
    def _search_fashion_trends(self, query: str, specialty: str = None) -> List[Dict]:
        return [
            {
                'title': f'Trend analysis for {query}',
                'authors': ['Fashion Institute', 'Vogue Trends'],
                'journal': 'Global Fashion Quarterly',
                'year': 2023,
                'abstract': 'Detailed report on color trends and pattern popularity...',
                'link': 'https://example.com/trends1'
            },
            {
                'title': f'Fabric Resource Guide: {query}',
                'organization': 'Textile Producers Association',
                'year': 2023,
                'summary': 'Technical guide for sourcing premium materials...',
                'link': 'https://example.com/fabrics1'
            }
        ]
    
    def _update_vendor_context(self, ai_response: Dict, context: Optional[Dict]):
        updates = {
            'last_interaction': str(timezone.now()),
            'last_category': ai_response.get('category'),
            'confidence_score': ai_response.get('ai_confidence'),
            'consultation_type': context.get('consultation_type') if context else None
        }
        
        if context:
            updates.update(context)
        
        self._update_session_context(updates)
