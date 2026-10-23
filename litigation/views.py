from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import ManualReviewRequest
from .services import notify_support_of_request, review_payload


class ReviewRequestThrottle(AnonRateThrottle):
    # Public, unauthenticated write -- keep it from being used to flood the table.
    rate = "10/hour"


class ReviewRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualReviewRequest
        fields = ["parcel_id", "certificate_reference", "contact_email", "contact_phone", "notes"]
        extra_kwargs = {"notes": {"max_length": 2000}}

    def validate(self, attrs):
        # We can only tell the user their review is ready if we can reach them.
        if not (attrs.get("contact_email") or attrs.get("contact_phone")):
            raise serializers.ValidationError(
                "Provide an email address or phone number so we can tell you when your review is ready."
            )
        return attrs


class ReviewRequestView(APIView):
    """POST a parcel the ELC search couldn't confirm -> logs a manual-review request."""

    throttle_classes = [ReviewRequestThrottle]

    def post(self, request):
        serializer = ReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = serializer.save()
        notify_support_of_request(req)
        return Response({"id": req.id, "status": req.status}, status=status.HTTP_201_CREATED)


class ReviewStatusView(APIView):
    """The page an emailed link opens: the review's status and outcome. The
    unguessable token in the URL is the only credential."""

    def get(self, request, token):
        req = ManualReviewRequest.objects.filter(access_token=token).first()
        if req is None:
            return Response({"detail": "Review not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(review_payload(req))
