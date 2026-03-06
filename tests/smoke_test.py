"""
Smoke Test for Reality Kernel and Overmind Assembly.
This test verifies that the core components can be instantiated without runtime errors.
"""

import pytest

from app.kernel import RealityKernel


@pytest.mark.asyncio
async def test_kernel_initialization():
    """Verify RealityKernel initializes with valid settings."""
    settings = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "SECRET_KEY": "x" * 32,
        "ENVIRONMENT": "testing",
    }
    # Fix: RealityKernel requires keyword-only arguments (*)
    kernel = RealityKernel(settings=settings)
    app = kernel.get_app()
    # Adjust expectation based on testing environment override
    assert "CogniForge" in app.title


@pytest.mark.asyncio
async def test_overmind_client_access():
    """Verify Overmind client can be imported (Factory test removed as deprecated)."""
    # Previously tested create_overmind factory which is now removed.
    # Instead, we verify we can import the client entrypoint.
    try:
        from microservices.orchestrator_service.src.services.overmind.entrypoint import start_mission

        assert start_mission is not None
    except ImportError as e:
        pytest.fail(f"Overmind entrypoint import failed: {e}")
