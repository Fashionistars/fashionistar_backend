import os
import re

path = r'c:\Users\FASHIONISTAR\OneDrive\Documenti\FASHIONISTAR_ANTAGRAVITY\fashionistar_backend\apps\authentication\apis\auth_views\sync_views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix MeView
me_view_broken = '    @extend_schema(\n        responses={200: MeSerializer}'
me_view_fixed = 'class MeView(generics.RetrieveAPIView):\n    """\n    GET /api/v1/auth/me/\n\n    Returns the authenticated user\'s full profile.\n    Used by the frontend useAuthHydration() hook to rehydrate Zustand\n    user state on page refresh — without requiring a full re-login.\n    """\n    permission_classes = [IsAuthenticated]\n    serializer_class = MeSerializer\n\n    @extend_schema(\n        responses={200: MeSerializer}'

if me_view_broken in content:
    content = content.replace(me_view_broken, me_view_fixed)
    print('Fixed MeView')
else:
    # Try with slightly different indentation if first attempt fails
    print('Could not find exact MeView broken block, trying regex...')
    content = re.sub(r'\n\s*@extend_schema\(\s*responses=\{200: MeSerializer\}', me_view_fixed, content)

# Fix Response(exc.detail, ...) calls
content = content.replace('return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)', 
    'return error_response(\n                message="Validation failed",\n                errors=exc.detail,\n                status=status.HTTP_400_BAD_REQUEST\n            )')

# Fix the 403 blocks in LoginView
login_403_pattern = re.compile(r'return Response\(\s*{\s*"success": False, "message": str\(exc\.detail\), "code": exc\.default_code\s*}\s*,\s*status=status\.HTTP_403_FORBIDDEN\s*,?\s*\)')
content = login_403_pattern.sub(r'return error_response(\n                message=str(exc.detail),\n                code=exc.default_code,\n                status=status.HTTP_403_FORBIDDEN\n            )', content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done.')
