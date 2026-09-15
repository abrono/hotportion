"""
AWS Location Service wrapper.

Geocoding and reverse geocoding via a Place Index, using boto3.
"""

import asyncio
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from app.config import settings
from app.api.utils.logging_setup import logger


# =============================================
# AWS LOCATION SERVICE
# =============================================
class AWSLocationService:
    """Thin async wrapper around boto3's location client."""

    def __init__(self):
        self.place_index = settings.AWS_LOCATION_PLACE_INDEX
        self.route_calc = settings.AWS_LOCATION_ROUTE_CALCULATOR
        self.country_filter = settings.AWS_LOCATION_COUNTRY_FILTER
        self._client = None

    @property
    def client(self):
        if self._client is None:
            # Explicit creds if provided; else boto3 falls back to
            # env vars / ~/.aws/credentials / IAM role
            kwargs = {"region_name": settings.AWS_REGION}
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
            self._client = boto3.client("location", **kwargs)
        return self._client

    async def geocode(self, address: str) -> Optional[Dict[str, Any]]:
        """Returns {'lat', 'lng', 'label'} or None."""
        filters = [self.country_filter] if self.country_filter else []

        def _call():
            return self.client.search_place_index_for_text(
                IndexName=self.place_index,
                Text=address,
                MaxResults=1,
                FilterCountries=filters,
            )

        try:
            resp = await asyncio.get_running_loop().run_in_executor(None, _call)
        except (ClientError, BotoCoreError) as e:
            logger.error(f"AWS geocode error: {e}")
            return None

        results = resp.get("Results", [])
        if not results:
            return None

        top = results[0]
        # AWS returns GeoJSON: coordinates are [lng, lat]
        lng, lat = top["Place"]["Geometry"]["Point"]
        return {
            "lat": float(lat),
            "lng": float(lng),
            "label": top["Place"].get("Label", address),
        }

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[str]:
        def _call():
            return self.client.search_place_index_for_position(
                IndexName=self.place_index,
                Position=[lng, lat],   # AWS expects [lng, lat]
                MaxResults=1,
            )

        try:
            resp = await asyncio.get_running_loop().run_in_executor(None, _call)
        except (ClientError, BotoCoreError) as e:
            logger.error(f"AWS reverse geocode error: {e}")
            return None

        results = resp.get("Results", [])
        return results[0]["Place"].get("Label") if results else None


_aws_location: Optional[AWSLocationService] = None


def get_aws_location() -> AWSLocationService:
    global _aws_location
    if _aws_location is None:
        _aws_location = AWSLocationService()
    return _aws_location
