from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from userauths.models import Profile
from measurements.models import MeasurementVideo, Measurement
from measurements.serializers import MeasurementVideoSerializer
import requests




# API credentials
MIRRORSIZE_API_KEY = 'J0fTMvAKJPJuubNjNN0ShN33WSqAFmDtxpYG7RztM0hFOH41uorrk4BJyXWLK9Pz'
MERCHANT_ID = 'fashionistarclothings@outlook.com'

class GenerateAndRedirectView(APIView):
    """
    View to generate access code from Mirrorsize API and redirect to the measurement page.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
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

class FetchMeasurementView(APIView):
    """
    View to fetch the user's measurements from Mirrorsize API.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        profile = get_object_or_404(Profile, user=request.user)
        access_code = profile.mirrorsize_access_token
        data = {
            "apiKey": MIRRORSIZE_API_KEY,
            "merchantId": MERCHANT_ID,
            "accessCode": access_code
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
                Measurement.objects.create(
                    user=request.user,
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





# ========================   FOR CREATING AND VIEWING THE MEASUREMENT VIDEOS   ======================

class MeasurementVideoListView(APIView):
    """
    View to retrieve all measurement videos.
    """
    permission_classes = (AllowAny,)

    def get(self, request):
        try:
            measurement_videos = MeasurementVideo.objects.all()
            serializer = MeasurementVideoSerializer(measurement_videos, many=True)
            return Response({"message": "Measurement videos retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MeasurementVideoDetailView(APIView):
    """
    View to retrieve a specific measurement video by its ID.
    """
    permission_classes = (AllowAny,)

    def get(self, request, pk):
        try:
            measurement_video = get_object_or_404(MeasurementVideo, pk=pk)
            serializer = MeasurementVideoSerializer(measurement_video)
            return Response({"message": "Measurement video retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MeasurementVideoCreateView(APIView):
    """
    View to handle POST requests for MeasurementVideo.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            serializer = MeasurementVideoSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(user=request.user)
                return Response({"message": "Measurement video created successfully.", "data": serializer.data}, status=status.HTTP_201_CREATED)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MeasurementVideoUpdateView(APIView):
    """
    View to handle PUT requests for MeasurementVideo.
    """
    permission_classes = (IsAuthenticated,)

    def put(self, request, pk):
        try:
            measurement_video = get_object_or_404(MeasurementVideo, pk=pk, user=request.user)
            serializer = MeasurementVideoSerializer(measurement_video, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({"message": "Measurement video updated successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MeasurementVideoDeleteView(APIView):
    """
    View to handle DELETE requests for MeasurementVideo.
    """
    permission_classes = (IsAuthenticated,)

    def delete(self, request, pk):
        try:
            measurement_video = get_object_or_404(MeasurementVideo, pk=pk, user=request.user)
            measurement_video.delete()
            return Response({"message": "Measurement video deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
