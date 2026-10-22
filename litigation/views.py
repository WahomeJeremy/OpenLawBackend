from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import ManualReviewRequest


class ReviewRequestThrottle(AnonRateThrottle):
    # Public, unauthenticated write -- keep it from being used to flood the table.
    rate = "10/hour"


class ReviewRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualReviewRequest
        fields = ["parcel_id", "certificate_reference", "contact_email", "notes"]
        extra_kwargs = {"notes": {"max_length": 2000}}


class ReviewRequestView(APIView):
    """POST a parcel the ELC search couldn't confirm -> logs a manual-review request."""

    throttle_classes = [ReviewRequestThrottle]

    def post(self, request):
        serializer = ReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = serializer.save()
        return Response({"id": req.id, "status": req.status}, status=status.HTTP_201_CREATED)
