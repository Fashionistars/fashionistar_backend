from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import  Measurement
from userauths.models import Profile
from .serializers import GenerateAccessCodeSerializer, FetchMeasurementSerializer
import requests

# API credentials
MIRRORSIZE_API_KEY = 'J0fTMvAKJPJuubNjNN0ShN33WSqAFmDtxpYG7RztM0hFOH41uorrk4BJyXWLK9Pz'
MERCHANT_ID = 'fashionistarclothings@outlook.com'

class GenerateAndRedirectView(APIView):
    """
    View to generate access code from Mirrorsize API and redirect to the measurement page.
    """
    def post(self, request):
        serializer = GenerateAccessCodeSerializer(data=request.data)
        if serializer.is_valid():
            profile = get_object_or_404(Profile, user=request.user)
            data = {
                "apiKey": MIRRORSIZE_API_KEY,
                "merchantID": MERCHANT_ID,
                "productname": "GET_MEASURED",
                "emailId": profile.user.email,
                "name": profile.full_name,
                "mobileNo": profile.user.phone,
                "gender": profile.gender,
            }
            try:
                response = requests.post(
                    'https://api.user.mirrorsize.com/api/webBrowser/generateAccessCode/',
                    json=data
                )
                response_data = response.json()
                print(response_data)
                if response.status_code == 200 and response_data.get('code') == 1:
                    access_code = response_data['data']['accessCode']
                    measurement_url = f"https://user.mirrorsize.com/home/{access_code}"
                    profile.mirrorsize_access_token = access_code
                    profile.qr_code = response_data['data']['qrCode']
                    profile.save()
                    return Response({"qr_code": response_data['data']['qrCode'], "measurement_url": measurement_url}, status=status.HTTP_200_OK)
                else:
                    return Response({"error": response_data.get('message', 'Failed to generate access code.')}, status=status.HTTP_400_BAD_REQUEST)
            except requests.exceptions.RequestException as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FetchMeasurementView(APIView):
    """
    View to fetch the user's measurements from Mirrorsize API.
    """
    def post(self, request):
        profile = get_object_or_404(Profile, user=request.user)
        mirrorsize_access_token = profile.mirrorsize_access_token
        qr_code = profile.qr_code
        print(f"Access Token: {mirrorsize_access_token}, QR Code: {qr_code}")

        serializer = FetchMeasurementSerializer(data=request.data)
        if serializer.is_valid():
            data = {
                "apiKey": MIRRORSIZE_API_KEY,
                "merchantId": MERCHANT_ID,
                "accessCode": mirrorsize_access_token
            }
            try:
                response = requests.post(
                    'https://api.user.mirrorsize.com/api/webBrowser/getmeasurement',
                    json=data
                )
                response_data = response.json()
                print(response_data)
                if response.status_code == 200 and response_data.get('code') == 1:
                    measurement_data = response_data['data']
                    user = request.user
                    Measurement.objects.create(
                        user=user,
                        gender=measurement_data['gender'],
                        name=measurement_data['name'],
                        weight=measurement_data['weight'],
                        height=measurement_data['height'],
                        age=measurement_data['age'],
                        measurements=measurement_data['measurement']
                    )
                    return Response({"message": "Measurement data saved successfully."}, status=status.HTTP_200_OK)
                else:
                    return Response({"error": response_data.get('message', 'Failed to fetch measurement data.')}, status=status.HTTP_400_BAD_REQUEST)
            except requests.exceptions.RequestException as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
