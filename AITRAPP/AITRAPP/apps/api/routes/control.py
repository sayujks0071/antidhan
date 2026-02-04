"""Control plane endpoints"""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from packages.core.config import AppMode
from packages.core.models import SystemState
from packages.core.strategies import OptionsRankerStrategy, ORBStrategy, TrendPullbackStrategy

router = APIRouter()
logger = logging.getLogger(__name__)


class ModeChangeRequest(BaseModel):
    """Mode change request"""

    mode: str
    confirmation: str | None = None


class ModeChangeResponse(BaseModel):
    """Mode change response"""

    previous_mode: str
    new_mode: str
    message: str


@router.get("/state", response_model=SystemState)
async def get_system_state(request: Request) -> SystemState:
    """Get current system state"""
    state = request.app.state.aitrapp
    return state.get_system_state()


@router.post("/mode", response_model=ModeChangeResponse)
async def change_mode(request: Request, mode_request: ModeChangeRequest) -> ModeChangeResponse:
    """
    Change trading mode (PAPER or LIVE)
    
    LIVE mode requires confirmation: "CONFIRM LIVE TRADING"
    """
    state = request.app.state.aitrapp
    previous_mode = state.mode.value
    new_mode = mode_request.mode.upper()

    # Validate mode
    if new_mode not in [AppMode.PAPER.value, AppMode.LIVE.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mode: {new_mode}. Must be PAPER or LIVE",
        )

    # Check if switching to LIVE
    if new_mode == AppMode.LIVE.value:
        if mode_request.confirmation != "CONFIRM LIVE TRADING":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="LIVE mode requires confirmation: 'CONFIRM LIVE TRADING'",
            )

        logger.critical("🔴 Switching to LIVE mode - real money at risk!")

    # Change mode
    state.mode = AppMode(new_mode)
    state.execution_engine.mode = AppMode(new_mode)

    logger.warning(f"Mode changed: {previous_mode} → {new_mode}")

    return ModeChangeResponse(
        previous_mode=previous_mode,
        new_mode=new_mode,
        message=f"Mode changed to {new_mode}",
    )


@router.post("/pause")
async def pause_trading(request: Request) -> Dict:
    """Pause all trading activity"""
    state = request.app.state.aitrapp
    await state.pause_trading()

    return {
        "status": "PAUSED",
        "message": "All trading activity paused",
    }


@router.post("/resume")
async def resume_trading(request: Request) -> Dict:
    """Resume trading activity"""
    state = request.app.state.aitrapp
    await state.resume_trading()

    return {
        "status": "ACTIVE",
        "message": "Trading activity resumed",
    }


@router.post("/kill-switch")
async def activate_kill_switch(request: Request) -> Dict:
    """
    🚨 EMERGENCY KILL SWITCH 🚨
    
    Immediately:
    1. Pause trading
    2. Cancel all pending orders
    3. Close all positions
    """
    state = request.app.state.aitrapp
    result = await state.kill_switch()

    logger.critical(f"Kill switch result: {result}")

    return result


@router.post("/universe/reload")
async def reload_universe(request: Request) -> Dict:
    """Reload trading universe"""
    state = request.app.state.aitrapp

    # Rebuild universe
    count = await state.universe_builder.build_universe(
        indices=state.config.universe.indices,
        include_fo_stocks=True,
        top_n_stocks=state.config.universe.fo_stocks_liquidity_rank_top_n,
        exclude_fo_ban=state.config.universe.exclude_fo_ban,
    )

    # Resubscribe to WebSocket
    if state.websocket_manager:
        universe_tokens = list(state.universe_builder.get_universe_tokens())
        state.websocket_manager.subscribe(universe_tokens, mode="full")

    return {
        "status": "SUCCESS",
        "instruments_count": len(count),
        "message": "Universe reloaded successfully",
    }


@router.post("/strategies/reload")
async def reload_strategies(request: Request) -> Dict:
    """Reload strategy configurations"""
    state = request.app.state.aitrapp

    try:
        # Reload configuration
        state.config.reload()

        # Clear existing strategies
        state.strategies.clear()

        # Re-instantiate strategies from new config
        for strategy_config in state.config.get_enabled_strategies():
            if strategy_config.name == "ORB":
                state.strategies.append(ORBStrategy(
                    strategy_config.name,
                    strategy_config.params
                ))
            elif strategy_config.name == "TrendPullback":
                state.strategies.append(TrendPullbackStrategy(
                    strategy_config.name,
                    strategy_config.params
                ))
            elif strategy_config.name == "OptionsRanker":
                state.strategies.append(OptionsRankerStrategy(
                    strategy_config.name,
                    strategy_config.params
                ))

        # Update strategies in orchestrator if it exists (for main.py structure)
        if hasattr(state, "orchestrator") and state.orchestrator:
            state.orchestrator.strategies = state.strategies

        # Update strategy_list if it exists (for main.py structure)
        if hasattr(state, "strategy_list"):
             state.strategy_list = state.strategies

        logger.info(f"Reloaded {len(state.strategies)} strategies")

        return {
            "status": "SUCCESS",
            "strategies_count": len(state.strategies),
            "message": "Strategies reloaded successfully",
        }
    except Exception as e:
        logger.error(f"Failed to reload strategies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload strategies: {str(e)}"
        )

