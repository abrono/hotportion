"""Order models."""

from typing import List, Optional

from pydantic import BaseModel


class OrderItem(BaseModel):
    name: str
    qty: int
    price: int
    product_id: int


class OrderCreate(BaseModel):
    payment_reference: str
    customer_name: str
    customer_email: str
    customer_phone: str
    total: int
    status: Optional[str] = "pending"
    delivery_method: Optional[str] = "pickup"
    delivery_address: Optional[str] = None
    preferred_time: Optional[str] = None
    order_notes: Optional[str] = None
    items: List[OrderItem]
    monnify_transaction_ref: Optional[str] = None
    delivery_fee: Optional[int] = 0
    table_number: Optional[int] = None   # for future QR ordering


class OrderStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None
