from sqlalchemy.ext.asyncio import create_async_engine
import pytest
import asyncio
from unittest.mock import MagicMock, patch

# Mock settings to avoid needing real env vars
with patch("app.core.config.settings") as mock_settings:
    mock_settings.database_url = "postgresql+asyncpg://user:password@localhost:5432/testdb"
    from app.database.core import engine, get_db

@pytest.mark.asyncio
async def test_connection_pooling_configuration():
    """
    Verify that the engine is configured with the expected pool size.
    """
    # Since we can't easily check internal pool state without a real DB connection
    # (which we may not have in this CI/sandbox environment), we inspect the engine settings.
    
    # Check if engine was initialized (it requires DATABASE_URL)
    # In this test environment, we might need to manually ensure it's set if the import happened before patch
    # But for the sake of unit testing the *code logic*, let's assume valid URL was passed.
    
    if engine:
        assert engine.pool.size() == 20
        assert engine.pool.timeout() == 30
    else:
        pytest.skip("Engine not initialized (missing DATABASE_URL)")

@pytest.mark.asyncio
async def test_concurrent_session_acquisition():
    """
    Simulate high concurrency to ensure sessions can be acquired without error.
    This mocks the actual DB connection to avoid needing a running Postgres.
    """
    
    # Mock the session maker and session
    mock_session = MagicMock()
    mock_session.close = MagicMock(return_value=asyncio.Future())
    mock_session.close.return_value.set_result(None)
    mock_session.rollback = MagicMock(return_value=asyncio.Future())
    mock_session.rollback.return_value.set_result(None)
    
    # We need to mock the async context manager behavior of the session
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with patch("app.database.core.async_session_maker", return_value=mock_session) as mock_maker:
        async def task():
            async for session in get_db():
                # Simulate some work
                await asyncio.sleep(0.01)
                return True
        
        # Run 50 concurrent tasks
        results = await asyncio.gather(*[task() for _ in range(50)])
        
        assert all(results)
        assert mock_maker.call_count == 50
        # Check that sessions were closed (requires digging into the generator, 
        # but the logic in get_db guarantees close in finally block)
        # Verify close was called on the mock session
        # Since we yielded the same mock_session 50 times, close should be called 50 times
        assert mock_session.close.call_count == 50

@pytest.mark.asyncio
async def test_session_rollback_on_error():
    """
    Ensure rollback is called if an exception occurs during session usage.
    """
    mock_session = MagicMock()
    mock_session.close = MagicMock(return_value=asyncio.Future())
    mock_session.close.return_value.set_result(None)
    mock_session.rollback = MagicMock(return_value=asyncio.Future())
    mock_session.rollback.return_value.set_result(None)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with patch("app.database.core.async_session_maker", return_value=mock_session):
        with pytest.raises(ValueError):
            async for session in get_db():
                raise ValueError("Simulated Error")
        
        # Verify rollback was called
        assert mock_session.rollback.call_count == 1
        # Verify close was always called
        assert mock_session.close.call_count == 1
