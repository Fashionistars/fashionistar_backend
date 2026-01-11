# PROMPT_04.MD - Creating AUTH.MD Architectural File

## User Query (Fourth Prompt)
LET ALL THESE I HAVE LISTED BELOW BE FIRST OF ALL WRITTEN IN AN INSTRUCTION ARCHITECTURAL MARKDOWN FILE, WHERE WE WILL BE ACCESSING IT ONE BY ONE FIRST FOR ONLY THIS AUTH SECTION.

WE ARE GOING TO WRITE ANOTHER INSTRUCTION FOR EACH OF THE NEXT SECTION WE WILL BE HANDLING AFTER THIS AUTH SECTION IS DONE PLEASE 

SO WHAT WE ARE GOING TO DO NOW IS OPENING FASHIONISTAR BACKEND AND FRONTEND ON DIFFERNT TERMINALS NOW, THEN WE WILL SELECT THE AUTHENTICATION AND AOTHORIZATION, I WILL EQUALLY SEND YOU THE FIGMA DESIGN PROFILE FOR AUTH,

YOU WILL FIRST OF ALL READ AND STUDY THE BEST PATTERN AND BEST APPROACH IN WHICH WE WILL APPLY TO GET THE BEST DESIRED RESULTS TODAY PLEASE.

YOU WIIL FRIST OF ALL WRITE AN "AUTH.MD" ARCHITECTURAL FILE, GIVING AI AGENTS INSTRUCTIONS ONE BY ONE, ONE AFTER THE OTHER ON WHAT TO IMPLEMENT AND WHAT NOT TO IMPLEMENT, BUT WE WILL GRADUALLY HANDLE THIS PROJECT APPLYING BEST INDUSTRIAL PRACTICES TO ACCERTAIN A CERTAIN LEVEL OF PROFESSIONAL 10 YEARS FULLSTACK EXPERIENCE LEVEL RESULTS.

REMEMBER, THE FILES SRESTRUCTURE FOR EACH APP AS WE DISCUSSED
REMEMBER THE HUMAN READABLE ERROR AND SUCCESS "MESSAGES " IN EACH AND EVERY RESPONSE
REMEMBER THE STRICT TYPE SETTINGS TO APPLY, UNDERLAYING EACH AND EVERY OF OUR BUSINESS MODELS IN A SERVICE.PY FILES/LAYERS WITH STRICT PYTHON TYPE FILE IN ADDITION TO STRICT SERIALIZER OPTIMIZED MODELS HANLING,
REMEMBER TO APPLY PYTHON PYDANTIC AND SHEMA MODELS WHERE NECESSARY.
REMEMBER WE ARE PROCEEDING WITH DJANGO RESTFRAMEWORK, BUT THERE MUST BE STRICK OPTIMIZATION AND SPEED PERFORMANCE, WITH MAINTAINABILITY IN EACH AND EVERY ASPECT OF THE CODE BASE.
REMEMBER TO APPLY INDUSTRIAL BEST PROJECT RESTRUCTURING FOR EACH AND EVERY FRONTEND AND BACKEND CODE WE ARE WORKING ON.
REMEMBER THAT WE ARE GOING TO USE A WELL DEFINED DN EXPLAINED ROBUST "COMMENTS" IN EACH AND EVERY FILE /FOLDER, IN EACH AND EVERY SPECIFIC / SECTION OF LINES OF CODES,
REMEMBER THAT IT MUST BE INDUSTRIAL. PROFESSIONAL AND ENTERPRISE STANDARD IN EACH AND EVERYTHING
REMEMBER WE ARE GOING TO USE A ROBUST " TRY AND EXCEPT" BLOCK HANDLING FOR BOTH THE BACKEND AND FRONTEND COMPONENTS, IN EACH AND EVERY LINE OF CODE IN ORDER TO AVOID BREAKAGES OF OUR CODE IN PRODUCTION, SINCE WE ARE GOING TO START WITH MONOLITH FIRST, AND THEN TRANSITIONING INTO FULL FLEDGE MICRO-SERVICE ARCHITECTURE IN THE FUTURE.
REMEMBER THAT WE ARE GOING TO APPLY REBOST SUCCESS AND ERROR LOGGING USING AND EXTERNAL LIBRARY IN DJANGO RESTFRAME WORK FOR EASE OF ACCESS AND MAKING SURE WE DON;T MAKE MISTAKES OR HAVE LOOP HOLES IN OUR PRODUCTION DEPLOYMENT PLEASE ( https://tgoddessana.github.io/django-logbox/

https://pypi.org/project/drf-api-logger/
)
REMEMBER WE ARE GRADULLY GOING TO RESTRUCTURE EACH AND EVERY DJANGO APP TO SUIT THIS OUR NEW API STANDARD PLEASE

REMEMBER THAT YOU ARE GOING TO ADD 5 OF YOUR OWN RECOMMENDATION FOR EACH SECTION WE ARE WORKING WITH, BUT YOUR OWN RECOMMENDATIONS MUST WAIT FOR AN APPROVAL FROM ME BEFORE WE PROCEED TO IMPLEMENTATION PHASE PLEASE 

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

**Tools & Libraries:**
- Django REST Framework (DRF) for APIs.
- Pydantic for schema validation.
- `drf-api-logger` for request/response logging.
- `django-encrypted-model-fields` for sensitive data.
- JWT via `djangorestframework-simplejwt`.
- Custom validators and type hints.

**File Structure for `userauths` App:**
```
userauths/
├── models.py          # Enhanced User model with MFA, profiles
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

## Step-by-Step Implementation Instructions

### Step 1: Restructure the App Folder
- **Action:** Create the `services/`, `cores/`, and `tests/` directories in `userauths/`.
- **Why:** Ensures separation of concerns; `services/` for business logic, `cores/` for AI/security processing, `tests/` for coverage.
- **Comments:** Add `# Business logic layer` in services files.
- **Try-Except:** N/A (file creation).
- **Logging:** N/A.

### Step 2: Enhance Models with Strict Typing and Encryption
- **Action:** Update `models.py` to use TimeStampedModel (from common), add MFA fields, encrypted email/phone. Use Pydantic for validation schemas.
- **Why:** Security and type safety; encrypted fields prevent breaches.
- **Comments:** `# Enhanced User model with MFA support` above class.
- **Try-Except:** Wrap model saves in try-except for integrity errors.
- **Logging:** Log model creation/updates via signals to audit logs.

### Step 3: Implement Service Layer with Types
- **Action:** Create `services/auth_service.py` with typed functions (e.g., `def authenticate_user(user_data: UserLoginSchema) -> AuthResult`). Use Pydantic schemas for input/output.
- **Why:** Decouples logic from views; enables testing and reuse.
- **Comments:** `# Authenticate user with MFA check` for each function.
- **Try-Except:** Catch authentication failures, raise custom exceptions.
- **Logging:** Use `drf-api-logger` decorators on service methods.

### Step 4: Optimize Serializers with Pydantic
- **Action:** Refactor `serializers.py` to integrate Pydantic models for validation. Add custom validators for email/phone.
- **Why:** Faster validation than DRF alone; type safety.
- **Comments:** `# Pydantic-backed serializer for login` .
- **Try-Except:** Validate inputs in try blocks, return error messages.
- **Logging:** Log serialization errors.

### Step 5: Build Views with Error Handling and Messages
- **Action:** Rewrite `views.py` to use service layer, add human-readable messages (e.g., "Login successful" or "Invalid credentials"). Implement MFA endpoints.
- **Why:** User-friendly responses; prevents silent failures.
- **Comments:** `# Handle user login with comprehensive error handling` .
- **Try-Except:** Wrap all logic in try-except, return 500 on unexpected errors.
- **Logging:** Decorate views with `drf-api-logger` for full request logs.

### Step 6: Add Cores for Advanced Processing
- **Action:** Implement `cores/api_ingress.py` for input sanitization, `cores/text_processor.py` for OTP generation, `cores/orchestrator.py` for auth workflows.
- **Why:** Handles complex auth flows like MFA verification.
- **Comments:** `# Orchestrate MFA workflow` .
- **Try-Except:** Handle external API calls (e.g., SMS) with retries.
- **Logging:** Log core operations.

### Step 7: Update URLs and Admin
- **Action:** Clean `urls.py` with named patterns. Enhance `admin.py` with encrypted field handling.
- **Why:** Maintainability and security.
- **Comments:** `# Auth URL patterns` .
- **Try-Except:** N/A.
- **Logging:** N/A.

### Step 8: Comprehensive Testing
- **Action:** Write tests in `tests/` for models, services, views with 95%+ coverage.
- **Why:** Ensures reliability.
- **Comments:** `# Test auth service` .
- **Try-Except:** In test assertions.
- **Logging:** N/A.

### Step 9: Integrate Logging Library
- **Action:** Install and configure `drf-api-logger` in settings, add to middleware.
- **Why:** Tracks all API interactions for debugging/production.
- **Comments:** `# API logging middleware` .
- **Try-Except:** N/A.
- **Logging:** Self-explanatory.

### Step 10: Frontend Alignment (Brief)
- **Action:** Update frontend auth components with typed interfaces, error handling.
- **Why:** Consistency.
- **Comments:** `# Auth component with error states` .
- **Try-Except:** In API calls.
- **Logging:** Console logs for dev.

## 5 Own Recommendations (Awaiting Approval)
1. **Implement OAuth2 Integration:** Add Google/Facebook login for better UX, using django-allauth, with typed schemas.
2. **Add Biometric Auth:** Integrate WebAuthn for fingerprint/face ID, enhancing security for mobile users.
3. **Rate Limiting per User:** Beyond IP, limit login attempts per user to prevent brute force.
4. **Session Management:** Use Redis for session storage with automatic expiration.
5. **Audit Trail Expansion:** Log device fingerprints and geolocation for compliance.

**Next:** After approval, proceed to implementation. Then move to next section (e.g., Products).