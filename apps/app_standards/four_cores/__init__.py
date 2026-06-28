"""
چهار هسته‌ی اصلی معماری هلسا
Four Core Architecture Components
"""

from .api_ingress import APIIngressCore, with_api_ingress
from .text_processor import TextProcessorCore, TextProcessingResult
from .speech_processor import SpeechProcessorCore, AudioTranscriptionResult, AudioGenerationResult
from .orchestrator import CentralOrchestrator, WorkflowStatus, WorkflowStep, WorkflowResult

__all__ = [
    # API Ingress
    'APIIngressCore',
    'with_api_ingress',
    
    # Text Processing
    'TextProcessorCore',
    'TextProcessingResult',
    
    # Speech Processing
    'SpeechProcessorCore',
    'AudioTranscriptionResult',
    'AudioGenerationResult',
    
    # Orchestration
    'CentralOrchestrator',
    'WorkflowStatus',
    'WorkflowStep',
    'WorkflowResult',
]

# Version info
__version__ = '1.0.0'
__author__ = 'HELSSA Development Team'