from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.views_base import OrgScopedViewMixin
from common.exceptions import ApiError

from .analytics import RANGES, summary
from .serializers import AnalyticsSummarySerializer


class AnalyticsSummaryView(OrgScopedViewMixin, generics.GenericAPIView):
    """Runs, success rate, hours saved, heals and AI spend for the workspace."""

    serializer_class = AnalyticsSummarySerializer

    def get_queryset(self):  # nothing to list; required by GenericAPIView
        return None

    @extend_schema(
        parameters=[OpenApiParameter("range", enum=list(RANGES), default="7d")],
        responses={200: AnalyticsSummarySerializer},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        key = request.query_params.get("range", "7d")
        if key not in RANGES:
            raise ApiError(
                "invalid_range", f"range must be one of {', '.join(RANGES)}.", status_code=400
            )
        return Response(AnalyticsSummarySerializer(summary(self.org, RANGES[key])).data)
