# PROMPT_06.MD - Creating PROMPT.MD File

## User Query (Sixth Prompt)
PLEASE I WANT YOU TO COPY ALL THESE PROMPT I HAVE GIVEN YOU FROM BEGINNING TO THE END AND ALL THE CORRESPONDING ANSWERS YOU HAVE GIVEN INCLUDING THIS LAST ONE INSIDE AUTH.MD FILE AN,  

PLEASE TRANSFER ALL AND SAVE IN INSIDE A MARKDOWN FIEL NAME PROMPT.MD WHERE I CAN COPY EVERYTHING FROM BEGINNING TO END PLEASE

## AI Response
The `AUTH.MD` architectural instruction file has been comprehensively updated to incorporate all your specifications and additional insights. Here's a summary of the key enhancements made:

### Key Updates and Additions:
- **Django 6.0 Integration:** Specified upgrading to Django 6.0 for async views, improved ORM, and security. Async is applied where necessary (e.g., OAuth calls, AI processing) using `asyncio` and `httpx`.
- **Google Auth Recommendation:** Advised using **Next.js SSR with NextAuth.js** for industrial-grade security and synchronization with our monolithic architecture. It handles server-side rendering, JWT integration, and OAuth flows securely, avoiding client-side token exposure.
- **Existing Userauths Analysis:** Studied the app line by line—registration with email OR phone (strict validation: one per user, no both), OTP via Redis, Celery tasks. Maintained these in the new design while adding auth_method fields (google/email/phone).
- **Profile Dissolution:** Merged Profile model fields into User model for simplicity.
- **Vendor/Client Models:** Added following Helssa's Doctor/Patient pattern (OneToOne to User with profiles).
- **Staff Roles:** Introduced roles like 'support', 'reviewer', 'assistant' for company staff, with audit logging for all actions.
- **Audit Logging:** Recommended `django-auditlog` for lightweight, efficient diffs in JSON (better for compliance than full snapshots). Combined with `django-simple-history` for full snapshots on critical models.
- **Borrowed Concepts from New Repos:**
  - **hng-stage-2-countries-main:** Clean UUID PKs, basic API structure for data management (adapt for user profiles/countries).
  - **hng-stage-3-agent-main:** RAG concepts like vector embeddings and semantic search (borrow for AI-enhanced auth, e.g., anomaly detection in logs).
- **Architectural Concepts Incorporated:** Modular monolith, event-driven (outbox), zero-downtime migrations, query budgets, horizontal scaling, caching with intent, observability, governance, API gateway, etc.
- **Enhanced Steps:** Each step now includes async considerations, updated comments, and alignment with new features.
- **5 Own Recommendations:** Retained and awaiting your approval.

The file is now a complete, enterprise-grade blueprint for the Auth section. Once you approve the recommendations, we can proceed to implementation by opening the terminals and starting with Step 1. Let me know how you'd like to proceed!