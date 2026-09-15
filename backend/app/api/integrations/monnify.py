"""
Monnify payment gateway integration.

Includes HMAC-SHA512 webhook signature verification over the RAW request body.
"""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.api.utils.logging_setup import logger


# ---------- MONNIFY ----------
class MonnifyIntegration:
    def __init__(self):
        self.api_key = settings.MONNIFY_API_KEY
        self.secret_key = settings.MONNIFY_SECRET_KEY
        self.contract_code = settings.MONNIFY_CONTRACT_CODE
        self.base_url = settings.MONNIFY_BASE_URL
        self._token = None
        self._token_expiry = None
        self._session = None
        self.healthy = False

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def initialize(self):
        await self._get_access_token()
        self.healthy = True
        logger.info("Monnify ready")

    async def _get_access_token(self) -> str:
        if self._token and self._token_expiry and datetime.now() < self._token_expiry:
            return self._token
        auth = base64.b64encode(
            f"{self.api_key}:{self.secret_key}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }
        sess = await self._get_session()
        async with sess.post(
            f"{self.base_url}/api/v1/auth/login", headers=headers
        ) as resp:
            data = await resp.json()
            if resp.status == 200:
                self._token = data["responseBody"]["accessToken"]
                self._token_expiry = datetime.now() + timedelta(hours=1)
                return self._token
            raise RuntimeError(f"Monnify auth failed: {data}")

    async def initialize_transaction(
        self, amount, customer_name, customer_email, customer_phone,
        payment_reference, payment_description="Hot Portion Grill Order",
    ) -> Dict[str, Any]:
        if not self.healthy:
            try:
                await self.initialize()
            except Exception as e:
                return {"success": False, "error": f"Monnify not healthy: {e}"}

        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "amount": amount,
            "customerName": customer_name,
            "customerEmail": customer_email,
            "customerPhone": customer_phone,
            "paymentReference": payment_reference,
            "paymentDescription": payment_description,
            "contractCode": self.contract_code,
            "currencyCode": "NGN",
            "paymentMethods": ["CARD", "ACCOUNT_TRANSFER"],
            "redirectUrl": "https://hotportion.netlify.app/?status=success",
            "webhookUrl": "https://hotportion.onrender.com/api/v1/webhooks/monnify",
        }
        sess = await self._get_session()
        try:
            async with sess.post(
                f"{self.base_url}/api/v1/merchant/transactions/init-transaction",
                json=payload, headers=headers,
            ) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("requestSuccessful"):
                    body = data.get("responseBody", {})
                    return {
                        "success": True,
                        "transaction_reference": body.get("transactionReference"),
                        "checkout_url": body.get("checkoutUrl"),
                    }
                return {
                    "success": False,
                    "error": data.get("responseMessage", "Unknown Monnify error"),
                }
        except Exception as e:
            logger.exception("Monnify init exception")
            return {"success": False, "error": str(e)}

    @staticmethod
    def verify_signature(raw_body: bytes, signature: Optional[str]) -> bool:
        """Monnify signs the RAW body bytes with HMAC-SHA512(secret_key)."""
        if not signature:
            return False
        computed = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode(),
            raw_body,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(computed, signature)


_monnify = None


def get_monnify() -> MonnifyIntegration:
    global _monnify
    if _monnify is None:
        _monnify = MonnifyIntegration()
    return _monnify
