from rest_framework import generics
from userauths.serializer import *


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny






class USERSPROFILELISTVIEW(generics.ListAPIView):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = ()

    def get_queryset(self):
        try:
            return super().get_queryset()
        except Exception as e:
            print(f"Error retrieving ALL USERS: {e}")
            return Profile.objects.none()







