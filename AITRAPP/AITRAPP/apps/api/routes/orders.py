"""Order management endpoints"""

from typing import List

from fastapi import APIRouter, Request

from packages.core.models import Order

router = APIRouter()


@router.get("/orders", response_model=List[Order])
async def get_orders(request: Request) -> List[Order]:
    """Get all orders"""
    state = request.app.state.aitrapp
    
    # Get pending orders
    pending_orders = state.execution_engine.get_pending_orders()
    
    return pending_orders


@router.get("/orders/{client_order_id}")
async def get_order(request: Request, client_order_id: str) -> Order:
    """Get specific order"""
    state = request.app.state.aitrapp
    order = state.execution_engine.get_order_by_id(client_order_id)
    
    if not order:
        from fastapi import HTTPException, status
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order not found: {client_order_id}",
        )
    
    return order

