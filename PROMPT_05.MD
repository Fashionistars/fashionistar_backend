# PROMPT_05.MD - Updating AUTH.MD with New Repositories

## User Query (Fifth Prompt)
REMEMBER TO IMPLEMENT ASYNCE WHERE EVER NECESSARY PLEASE AND ANOTHER THING IS THAT WE ARE GOING TO USE DJANGO 6.0 FOR EVERYTHING WE ARE CURRENTLY DOING FROM NOW PLEASE, AND STILL REASON AND CONSIDER IF WE ARE GOING TO IMPLEMENT THIS DJANGO VERSION 6.0 TASK FRAMEWORK INTO THIS OUR PROJECT PLEASE

NOW I HAVE ADDED TWO OF MY OWN LATEST PERSONAL REPOSITORIES FOR AI AGENT RAG SYSTEM IMPLEMENTATIONA AND THE COUNTRIES DATA.

YOU ARE EQALLY GOING TO SCAN THROUGH ALL OF THEM, ONE BY ONE, ONE AFTER THE OTHER LINE BY LINE IN ORDER TO MAKE SURE THAT YOU UNDERSTAND AND GET THE CONCEPTS WE NEED TO BORROW FROM THERE IN ORDER TO AUGUMENT THIS ONE " AUTH.MD" FILE TO BE PERFECTLY SET FOR THE TAK AHEAD OF US PLEASE

IF THERE IS ANY RECOMMENDATION / ADVICE YOU CAN STILL GO AHEAD AND MAKE THEM PLEASE 

NOW I AM STILL GOING TO ADD SOME RECOMMENDATIONS FROM THIS PROMPT CONCEPT BELOW IN WHICH YOU ARE ALSO GOING TO STUDY TO PICK AND SELECT THE MOST PERFECT ARCHITECTURES IN WHICH WE SHALL ADD IN OUR IMPLEMENTATION PROCESS TO ACHIEVE THIS AIM AND GOAL TOGETHER PLEASE.

AGAIN, FOR THIS AUTH PROCESS, WE ARE GOING TO USE THIS FOR OUR GOOGLE AUTH, THEN YOU WILL EQAULLY GIVE ME AN ADVICE / RECOMMENDATIONS ON HOW TO PERFECTLY IMPLEMENT IT TO THE INDUSTRIAL GRADE STANDARD WITH THE NEXT JS FRONTEND, WHETHER WE ARE GOING TO USE THE NEXT JS SERVER SIDE RENDERING TO HANDLE IT WITH NEXT JS AUTH FRAME WORK FROM ONE GOOGLE AUTH LIBRARY OR WE ARE GOING TO USE IT WITH THE NEXT JS CLIENT SIDE RENDERING. ( WHICH ONE IS THE BEST AND PERFECT FOR US TO SYNCHRONISE WITH OUR FRAMEWORK AND INDUSTRIAL GRADE PURSUIT WHILE STILL MAINTAINING THIS MONOLITH INDUSTRIAL PERFECT FIT ARCHITECTURE PLEASE)

AGAIN, I WILL EQUALLY WANT YOU TO THOUROUGHLY STUDY THE USERAUTH APP IN THE FASHIONISTAR BACKEND PROJECT TO UNDERSTAND THE WAY WE ALREADY IMPLEMENTED OUR AUTH SYSTEM ALLOWING FOR REGISTRATION USING EITHER "EMAIL" OR "PHONE" NUMBER. AND MAKING SURE WE THAT YOU CAN ONLY USE ONE FOR EACH USER, 

I KNOW WE ARE STILL GOING TO TOUCH AND RESTRUCTURE THE USER MODEL TO ALLOW AND ACCEPT THIS GOOGLE AUTH SETTING, AND NEWER FIELDS WILL BE ADDED IN ORDER TO SAVE WHETHER THE USER REGISTERED WITH GOOGLE, EMAIL, OR PHONE NUMBER. BUT YOU MUST PERFECTLY MAKE SURE THAT THIS STRICT VALIDATIONS ON BUT THE SERIALIZERS AND THE USER MODEL ARE BEEING MAINTAINED AND IMPLEMENTED STRICKLY TO THIS OUR NEW ARCHITECTURE PLEASE.

REMEMBER THAT WE ARE DISSOLVING THE PROFILE MODEL, EVERYTHING ABOUT EVERY USER WILL BE ON THE USER MODEL., BUT YOU WILL FOLLOW THAT SAME ARCHTECTURAL PATTERN THAT WAS IMPLEMENT @helssa-big-back-main BACKEND FOR THE ( DOCTORS & PATIENTS MODEL) TO EQUALLY APPLY TO BUILDING OUR VENDOR MODEL WITH IS ALREADY IN EXISTENCE, AND CREATING A NEW BUYER OR CLIENT MODEL FOR EACH USER THAT IS NOT A " VENDOR"

REMEMBER THAT WE ARE BUILDING A MULTI- PURPOSE PLATFORM, SO WE ARE CURRENTLY GOING TO HAVE OTHER USERS WHO ARE NOT EITHER VENDOR OR CLIENT, BUT PART OF THE COMPANY STAFFS AND NOT THE SUPER-ADMIN, SO YOU WILL CAREFULLY CRAFT OUT ( SUPPORT, ASSISTANCE, PRODUCT REVIEWERS/ANHANCERS AND OTHER USERS THAT WILL BE WORKING WITH THE FASHIONISTAR COMPANY) BECAUSE WE ARE ALSO GOING TO LOG / SAVE AND AUDIT EVERY ACTION PERFORMED BY EVERY STAFF MAYBE USING ANY DJANGO LIBRARY THAT CAN HANDLE THAT EXCELLENTLY WITHOUT ANY BOTTLE NECK SUCH AS THESE BELOW: OR IF THERE ARE ANY OTHER BETTER ALTERNATIVE, YOU CAN EQUALLY OUTLIST THEM FOR ADVANCED PERFECTIONG PLEASE
(
   https://pypi.org/project/django-auditlog/
    https://pypi.org/project/django-easy-audit/
    https://django-simple-history.readthedocs.io/en/stable/
    https://django-reversion.readthedocs.io/en/latest/

from auditlog.registry import auditlog
from auditlog.models import AuditlogHistoryField

class Vendor(models.Model):
    history = AuditlogHistoryField()
    # ... existing fields ...

# Register for auditing
auditlog.register(Vendor)
auditlog.register(BankAccountDetails)
)

REMEMBER WE ARE NOT YET STARTED IMPLEMENTATION, WE ARE ONLY CRAFTING OUT OUR ARCHITECTURAL DESIGN PATTERN IN WHICH WE WILL USE TO ACCURATELY IMPLEMENT THIS INDUSTRIAL STANDARD ENTERPRISE GRADE EXCELLENT MODERN FASHION AI ECOMMERCE PROJECT IN 2026

[Followed by the long prompt with architectural concepts breakdown]

## AI Response
# AUTH.MD - Authentication & Authorization Architectural Instructions

## Overview
This document provides detailed, step-by-step instructions for implementing a robust, industrial-grade Authentication and Authorization system for Fashionistar. As a senior fullstack developer with 10+ years of experience, these instructions ensure enterprise-level security, performance, and maintainability. We will restructure the existing `userauths` app to follow the new standards: modular apps with `services/`, `cores/`, `tests/`, strict typing, Pydantic schemas, optimized DRF, and comprehensive error handling.

**Key Principles:**
- **Security First:** Multi-factor authentication (MFA), JWT with refresh tokens, rate limiting, and audit logging.
- **Performance:** Optimized DRF with caching, async tasks where needed, and minimal database hits.
- **Maintainability:** Strict typing, service layers, robust comments, and try-except blocks.
- **Scalability:** Monolithic start, microservice-ready structure.
- **Compliance:** GDPR/CCPA-ready with encrypted fields and detailed logs.
- **Django Version:** Upgrading to Django 6.0 for latest features (async views, improved ORM, better security). Use async where necessary (e.g., external API calls for OAuth).
- **Audit Logging:** Implement `django-auditlog` for lightweight, efficient tracking of staff actions (create, update, delete) without full snapshots, suitable for compliance and security.

**Tools & Libraries:**
- Django 6.0 + DRF for APIs.
- Pydantic for schema validation.
- `drf-api-logger` for request/response logging.
- `django-encrypted-model-fields` for sensitive data.
- JWT via `djangorestframework-simplejwt`.
- `django-auditlog` for audit trails.
- Custom validators and type hints.
- Async support with `asyncio` and `httpx` for OAuth.

**File Structure for `userauths` App:**
```
userauths/
├── models.py          # Enhanced User model with MFA, profiles, Vendor/Client/Staff models
├── serializers.py     # Pydantic-integrated serializers with validation
├── views.py           # Optimized views with try-except and logging
├── urls.py            # Clean URL patterns
├── admin.py           # Admin interface
├── services/
│   ├── __init__.py
│   ├── auth_service.py  # Business logic layer with types
│   └── helpers.py       # Utility functions
├── cores/
│   ├── __init__.py
│   ├── api_ingress.py   # Input validation and preprocessing
│   ├── text_processor.py # Email/SMS processing
│   └── orchestrator.py   # Workflow coordination
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_views.py
│   └── test_services.py
└── types.py            # Python type definitions
```

**Borrowed Concepts from New Repositories:**
- **From hng-stage-2-countries-main:** Simple, clean Django setup with UUID PKs and basic API structure for data management (adapt for user profiles/countries in auth).
- **From hng-stage-3-agent-main:** RAG-inspired vector embeddings and semantic search (borrow for advanced auth features like AI-powered anomaly detection in logs). Async processing for AI tasks.

**Architectural Concepts Incorporated:**
- **Modular Monolith:** Hard boundaries between apps, no cross-app FKs, event-driven via outbox pattern.
- **Event-Driven:** Use outbox table for auth events (e.g., login success).
- **Zero-Downtime Migrations:** Expand-contract strategy for schema changes.
- **Query Performance:** Budgets, explain(), pg_stat_statements.
- **Horizontal Scaling:** Partitioning, read replicas, PgBouncer.
- **Caching:** Intent-based with versioned keys, dogpile protection.
- **Observability:** OpenTelemetry, Jaeger, Sentry for N+1 detection.
- **Governance:** Contract tests, migration tests, CODEOWNERS.
- **API Gateway:** Kong/Hasura for routing.
- **Audit Libraries:** `django-auditlog` for lightweight diffs in JSON (better for compliance than full snapshots). Combined with `django-simple-history` for full snapshots on critical models.

**Google Auth Recommendation:**
For industrial-grade synchronization with our monolithic architecture, use **Next.js SSR with NextAuth.js**. It provides server-side session management, integrates seamlessly with JWT, handles OAuth flows securely on the server, and maintains consistency with our backend. Client-side would expose tokens, risking security; SSR ensures server-rendered auth pages with proper hydration.

**Existing Userauths Analysis:**
- Registration allows email OR phone (strict validation: one per user, no both).
- OTP via email/SMS, Redis storage.
- Maintain these validations in new User model; add fields for auth method (google/email/phone).
- Dissolve Profile model: Merge fields into User (image, bio, etc.).
- Add Vendor/Client models following Helssa's Doctor/Patient pattern (OneToOne to User, with profiles).
- Staff roles: Add choices like 'support', 'reviewer', 'assistant'; audit all actions with `django-auditlog`.

## Step-by-Step Implementation Instructions

### Step 1: Restructure the App Folder
- **Action:** Create the `services/`, `cores/`, and `tests/` directories in `userauths/`.
- **Why:** Ensures separation of concerns; `services/` for business logic, `cores/` for AI/security processing, `tests/` for coverage.
- **Comments:** Add `# Business logic layer` in services files.
- **Try-Except:** N/A (file creation).
- **Logging:** N/A.
- **Async:** N/A.

### Step 2: Enhance Models with Strict Typing and Encryption
- **Action:** Update `models.py` to use TimeStampedModel (from common), add MFA fields, encrypted email/phone, auth_method (google/email/phone). Dissolve Profile into User. Add Vendor/Client models with OneToOne to User. Add staff roles with auditlog.
- **Why:** Security and type safety; encrypted fields prevent breaches; role separation.
- **Comments:** `# Enhanced User model with MFA support and merged Profile` above class.
- **Try-Except:** Wrap model saves in try-except for integrity errors.
- **Logging:** Log model creation/updates via signals to audit logs.
- **Async:** Use async signals if needed.

### Step 3: Implement Service Layer with Types
- **Action:** Create `services/auth_service.py` with typed functions (e.g., `def authenticate_user(user_data: UserLoginSchema) -> AuthResult`). Use Pydantic schemas for input/output. Add OAuth service for Google.
- **Why:** Decouples logic from views; enables testing and reuse.
- **Comments:** `# Authenticate user with MFA check` for each function.
- **Try-Except:** Catch authentication failures, raise custom exceptions.
- **Logging:** Use `drf-api-logger` decorators on service methods.
- **Async:** Make OAuth calls async with httpx.

### Step 4: Optimize Serializers with Pydantic
- **Action:** Refactor `serializers.py` to integrate Pydantic models for validation. Add custom validators for email/phone/auth_method.
- **Why:** Faster validation than DRF alone; type safety.
- **Comments:** `# Pydantic-backed serializer for login` .
- **Try-Except:** Validate inputs in try blocks, return error messages.
- **Logging:** Log serialization errors.
- **Async:** N/A.

### Step 5: Build Views with Error Handling and Messages
- **Action:** Rewrite `views.py` to use service layer, add human-readable messages (e.g., "Login successful" or "Invalid credentials"). Implement MFA and Google OAuth endpoints.
- **Why:** User-friendly responses; prevents silent failures.
- **Comments:** `# Handle user login with comprehensive error handling` .
- **Try-Except:** Wrap all logic in try-except, return 500 on unexpected errors.
- **Logging:** Decorate views with `drf-api-logger` for full request logs.
- **Async:** Use async views for OAuth.

### Step 6: Add Cores for Advanced Processing
- **Action:** Implement `cores/api_ingress.py` for input sanitization, `cores/text_processor.py` for OTP generation, `cores/orchestrator.py` for auth workflows. Add AI core for anomaly detection using RAG concepts.
- **Why:** Handles complex auth flows like MFA verification.
- **Comments:** `# Orchestrate MFA workflow` .
- **Try-Except:** Handle external API calls (e.g., SMS) with retries.
- **Logging:** Log core operations.
- **Async:** Async for AI processing.

### Step 7: Update URLs and Admin
- **Action:** Clean `urls.py` with named patterns. Enhance `admin.py` with encrypted field handling and auditlog integration.
- **Why:** Maintainability and security.
- **Comments:** `# Auth URL patterns` .
- **Try-Except:** N/A.
- **Logging:** N/A.
- **Async:** N/A.

### Step 8: Comprehensive Testing
- **Action:** Write tests in `tests/` for models, services, views with 95%+ coverage.
- **Why:** Ensures reliability.
- **Comments:** `# Test auth service` .
- **Try-Except:** In test assertions.
- **Logging:** N/A.
- **Async:** Async tests for views.

### Step 9: Integrate Logging Library
- **Action:** Install and configure `drf-api-logger` and `django-auditlog` in settings, add to middleware.
- **Why:** Tracks all API interactions for debugging/production.
- **Comments:** `# API logging middleware` .
- **Try-Except:** N/A.
- **Logging:** Self-explanatory.
- **Async:** N/A.

### Step 10: Frontend Alignment (Brief)
- **Action:** Update frontend auth components with typed interfaces, error handling. Use Next.js SSR with NextAuth for Google OAuth.
- **Why:** Consistency.
- **Comments:** `# Auth component with error states` .
- **Try-Except:** In API calls.
- **Logging:** Console logs for dev.
- **Async:** Async fetches.

## 5 Own Recommendations (Awaiting Approval)
1. **Implement OAuth2 Integration:** Add Google/Facebook login for better UX, using django-allauth, with typed schemas.
2. **Add Biometric Auth:** Integrate WebAuthn for fingerprint/face ID, enhancing security for mobile users.
3. **Rate Limiting per User:** Beyond IP, limit login attempts per user to prevent brute force.
4. **Session Management:** Use Redis for session storage with automatic expiration.
5. **Audit Trail Expansion:** Log device fingerprints and geolocation for compliance.

**Next:** After approval, proceed to implementation. Then move to next section (e.g., Products).