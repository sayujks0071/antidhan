"""Position management endpoints"""

from typing import List

from fastapi import APIRouter, Request
from pydantic import BaseModel

from packages.core.models import Position

router = APIRouter()


class PositionResponse(BaseModel):
    """Position response"""

    positions: List[Position]
    count: int
    total_pnl: float
    total_pnl_pct: float


@router.get("/positions", response_model=PositionResponse)
async def get_positions(request: Request) -> PositionResponse:
    """Get all open positions"""
    state = request.app.state.aitrapp
    positions = list(state.positions.values())
    
    total_pnl = sum(float(p.pnl) for p in positions)
    
    # Calculate total P&L %
    total_invested = sum(float(p.average_price) * p.quantity for p in positions)
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
    
    return PositionResponse(
        positions=positions,
        count=len(positions),
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
    )


@router.get("/positions/{instrument_token}")
async def get_position(request: Request, instrument_token: int) -> Position:
    """Get specific position"""
    state = request.app.state.aitrapp
    
    # Find position
    for position in state.positions.values():
        if position.instrument_token == instrument_token:
            return position
    
    from fastapi import HTTPException, status
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Position not found for instrument {instrument_token}",
    )


@router.post("/positions/close/{instrument_token}")
async def close_position(request: Request, instrument_token: int) -> dict:
    """Close a specific position"""
    state = request.app.state.aitrapp
    
    # Find position
    position = None
    for p in state.positions.values():
        if p.instrument_token == instrument_token:
            position = p
            break
    
    if not position:
        from fastapi import HTTPException, status
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position not found for instrument {instrument_token}",
        )
    
    # TODO: Place market order to close position
    
    return {
        "status": "SUCCESS",
        "message": f"Closing position for {position.tradingsymbol}",
    }


@router.post("/positions/close-all")
async def close_all_positions(request: Request) -> dict:
    """Close all positions"""
    state = request.app.state.aitrapp
    count = await state.close_all_positions(reason="MANUAL")
    
    return {
        "status": "SUCCESS",
        "closed_positions": count,
        "message": f"Closed {count} positions",
    }

