from unittest.mock import MagicMock, patch

import pytest

from packages.core.models import Instrument, InstrumentType
from packages.core.orchestrator import TradingOrchestrator
from packages.storage.models import Position as DBPosition
from packages.storage.models import PositionStatusEnum
from packages.storage.models import SideEnum as DBSideEnum


@pytest.mark.asyncio
async def test_recover_open_positions_populates_orchestrator_state():
    # 1. Setup Mocks
    mock_kite = MagicMock()
    mock_strategies = []

    mock_instrument_manager = MagicMock()
    # Mock get_instrument to return a valid Instrument object
    mock_instrument = Instrument(
        token=123456,
        symbol="INFY",
        tradingsymbol="INFY",
        exchange="NSE",
        instrument_type=InstrumentType.EQ
    )
    mock_instrument_manager.get_instrument.return_value = mock_instrument

    mock_market_data = MagicMock()
    mock_risk_manager = MagicMock()
    mock_execution_engine = MagicMock()
    mock_exit_manager = MagicMock()
    mock_ranker = MagicMock()

    orchestrator = TradingOrchestrator(
        kite=mock_kite,
        strategies=mock_strategies,
        instrument_manager=mock_instrument_manager,
        market_data_stream=mock_market_data,
        risk_manager=mock_risk_manager,
        execution_engine=mock_execution_engine,
        exit_manager=mock_exit_manager,
        ranker=mock_ranker
    )

    # 2. Setup DB Mock Data
    db_position = DBPosition(
        id=1,
        position_id="POS_1",
        symbol="INFY",
        instrument_token=123456,
        side=DBSideEnum.LONG,
        qty=10,
        avg_price=100.0,
        current_price=105.0,
        unrealized=50.0,
        stop_loss=90.0,
        status=PositionStatusEnum.OPEN,
        risk_amount=100.0,
        strategy_name="TEST_STRAT"
    )

    mock_db_session = MagicMock()
    mock_db_session.__enter__.return_value = mock_db_session
    mock_db_session.__exit__.return_value = None

    mock_query = MagicMock()
    mock_db_session.query.return_value = mock_query
    mock_query.filter_by.return_value = mock_query
    mock_query.all.return_value = [db_position]

    # Mock Order queries (for OCO check)
    def query_side_effect(model_cls):
        m = MagicMock()
        if model_cls.__name__ == 'Position':
            m.filter_by.return_value.all.return_value = [db_position]
        else:
            m.filter_by.return_value.all.return_value = []
        return m

    mock_db_session.query.side_effect = query_side_effect

    # 3. Execute recovery
    with patch("packages.storage.database.get_db_session", return_value=mock_db_session):
        await orchestrator._recover_open_positions()

    # 4. Verify
    # The orchestrator should have 1 position in memory
    assert len(orchestrator.positions) == 1, "Orchestrator failed to load position from DB"

    # Verify position details
    pos = orchestrator.positions[0]
    assert pos.position_id == "POS_1"
    assert pos.instrument.token == 123456
    assert pos.entry_price == 100.0
    assert pos.quantity == 10
    assert pos.strategy_name == "TEST_STRAT"
