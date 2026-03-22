from unittest.mock import MagicMock, patch

from app.infrastructure.patterns.chain_of_responsibility import (
    RequestContext,
    Handler,
    RateLimitHandler,
    AuthenticationHandler,
    AuthorizationHandler,
    ValidationHandler,
    LoggingHandler,
    CachingHandler,
    build_request_pipeline,
)

class TestRequestContext:
    def test_initial_state(self):
        data = {"key": "value"}
        ctx = RequestContext(data)
        assert ctx.data == data
        assert ctx.metadata == {}
        assert ctx.errors == []
        assert ctx.stopped is False

    def test_initial_state_no_data(self):
        ctx = RequestContext()
        assert ctx.data == {}
        assert ctx.metadata == {}
        assert ctx.errors == []
        assert ctx.stopped is False

    def test_stop_chain(self):
        ctx = RequestContext()
        ctx.stop_chain()
        assert ctx.stopped is True

    def test_add_error(self):
        ctx = RequestContext()
        ctx.add_error("Test error")
        assert ctx.errors == ["Test error"]
        assert ctx.has_errors() is True

    def test_has_errors_empty(self):
        ctx = RequestContext()
        assert ctx.has_errors() is False

class ConcreteHandler(Handler[RequestContext, RequestContext]):
    def __init__(self, return_val=None):
        super().__init__()
        self.return_val = return_val
        self.processed = False

    def _process(self, request: RequestContext) -> RequestContext | None:
        self.processed = True
        return self.return_val

class TestBaseHandler:
    def test_set_next(self):
        h1 = ConcreteHandler()
        h2 = ConcreteHandler()
        result = h1.set_next(h2)
        assert h1._next_handler == h2
        assert result == h2

    def test_handle_passes_to_next(self):
        h1 = ConcreteHandler(return_val=None)
        h2 = ConcreteHandler(return_val=None)
        h1.set_next(h2)

        ctx = RequestContext()
        h1.handle(ctx)

        assert h1.processed is True
        assert h2.processed is True

    def test_handle_stops_when_result_returned(self):
        ctx = RequestContext()
        h1 = ConcreteHandler(return_val=ctx)
        h2 = ConcreteHandler(return_val=None)
        h1.set_next(h2)

        result = h1.handle(ctx)

        assert h1.processed is True
        assert h2.processed is False
        assert result == ctx

    def test_handle_returns_none_at_end_of_chain(self):
        h1 = ConcreteHandler(return_val=None)
        ctx = RequestContext()
        result = h1.handle(ctx)
        assert result is None

class TestRateLimitHandler:
    def test_rate_limit_success(self):
        handler = RateLimitHandler(max_requests=2)
        ctx = RequestContext({"user_id": "user1"})

        # First request
        result = handler.handle(ctx)
        assert result is None
        assert ctx.metadata["rate_limit_remaining"] == 1
        assert ctx.has_errors() is False

        # Second request
        ctx2 = RequestContext({"user_id": "user1"})
        result2 = handler.handle(ctx2)
        assert result2 is None
        assert ctx2.metadata["rate_limit_remaining"] == 0
        assert ctx2.has_errors() is False

    def test_rate_limit_exceeded(self):
        handler = RateLimitHandler(max_requests=1)
        ctx1 = RequestContext({"user_id": "user1"})
        handler.handle(ctx1)

        ctx2 = RequestContext({"user_id": "user1"})
        result = handler.handle(ctx2)

        assert result == ctx2
        assert ctx2.stopped is True
        assert "Rate limit exceeded" in ctx2.errors

    def test_rate_limit_per_user(self):
        handler = RateLimitHandler(max_requests=1)

        # User 1
        ctx1 = RequestContext({"user_id": "user1"})
        handler.handle(ctx1)

        # User 2 should still be allowed
        ctx2 = RequestContext({"user_id": "user2"})
        result = handler.handle(ctx2)
        assert result is None
        assert ctx2.metadata["rate_limit_remaining"] == 0

    def test_rate_limit_anonymous(self):
        handler = RateLimitHandler(max_requests=1)
        ctx1 = RequestContext({}) # No user_id
        handler.handle(ctx1)

        ctx2 = RequestContext({})
        result = handler.handle(ctx2)
        assert result == ctx2
        assert ctx2.stopped is True
        assert "Rate limit exceeded" in ctx2.errors

class TestAuthenticationHandler:
    def test_auth_success(self):
        handler = AuthenticationHandler()
        ctx = RequestContext({"auth_token": "valid_token"})
        result = handler.handle(ctx)
        assert result is None
        assert ctx.metadata["authenticated"] is True

    def test_auth_missing_token(self):
        handler = AuthenticationHandler()
        ctx = RequestContext({})
        result = handler.handle(ctx)
        assert result == ctx
        assert ctx.stopped is True
        assert "Missing authentication token" in ctx.errors

    def test_auth_invalid_token(self):
        handler = AuthenticationHandler()
        # Mock _validate_token to return False even for a provided token
        with patch.object(AuthenticationHandler, '_validate_token', return_value=False):
            ctx = RequestContext({"auth_token": "some_token"})
            result = handler.handle(ctx)
            assert result == ctx
            assert ctx.stopped is True
            assert "Invalid authentication token" in ctx.errors

class TestAuthorizationHandler:
    def test_authz_success(self):
        handler = AuthorizationHandler()
        ctx = RequestContext({
            "required_permission": "read",
            "user_permissions": ["read", "write"]
        })
        ctx.metadata["authenticated"] = True
        result = handler.handle(ctx)
        assert result is None
        assert ctx.metadata["authorized"] is True

    def test_authz_not_authenticated(self):
        handler = AuthorizationHandler()
        ctx = RequestContext({"required_permission": "read"})
        # No authenticated metadata
        result = handler.handle(ctx)
        assert result == ctx
        assert ctx.stopped is True
        assert "Not authenticated" in ctx.errors

    def test_authz_missing_permission(self):
        handler = AuthorizationHandler()
        ctx = RequestContext({
            "required_permission": "admin",
            "user_permissions": ["read"]
        })
        ctx.metadata["authenticated"] = True
        result = handler.handle(ctx)
        assert result == ctx
        assert ctx.stopped is True
        assert "Missing permission: admin" in ctx.errors

class TestValidationHandler:
    def test_validation_success(self):
        handler = ValidationHandler(required_fields=["field1", "field2"])
        ctx = RequestContext({"field1": "v1", "field2": "v2"})
        result = handler.handle(ctx)
        assert result is None
        assert ctx.metadata["validated"] is True

    def test_validation_failure(self):
        handler = ValidationHandler(required_fields=["field1", "field2"])
        ctx = RequestContext({"field1": "v1"})
        result = handler.handle(ctx)
        assert result == ctx
        assert ctx.stopped is True
        assert "Missing required field: field2" in ctx.errors

class TestLoggingHandler:
    @patch("logging.getLogger")
    def test_logging_handler(self, mock_get_logger):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        handler = LoggingHandler()
        ctx = RequestContext({"request_id": "123"})
        result = handler.handle(ctx)

        assert result is None
        mock_logger.info.assert_called_with("Processing request: 123")

class TestCachingHandler:
    def test_cache_miss(self):
        handler = CachingHandler()
        ctx = RequestContext({"cache_key": "miss"})
        result = handler.handle(ctx)
        assert result is None
        assert "from_cache" not in ctx.metadata

    def test_cache_hit(self):
        handler = CachingHandler()
        handler.cache_response("hit", {"data": "cached"})
        ctx = RequestContext({"cache_key": "hit"})
        result = handler.handle(ctx)
        assert result == ctx
        assert ctx.data["cached_response"] == {"data": "cached"}
        assert ctx.metadata["from_cache"] is True

def test_full_pipeline_success():
    pipeline = build_request_pipeline()
    ctx = RequestContext({
        "auth_token": "token",
        "user_id": "user1",
        "user_permissions": ["read"],
        "required_permission": "read",
        "request_id": "req1"
    })
    # ValidationHandler doesn't have required_fields by default in build_request_pipeline

    result = pipeline.handle(ctx)

    # LoggingHandler is the last one, it returns None
    assert result is None
    assert ctx.metadata["authenticated"] is True
    assert ctx.metadata["authorized"] is True
    assert "rate_limit_remaining" in ctx.metadata
    assert ctx.metadata["validated"] is True
    assert ctx.has_errors() is False
    assert ctx.stopped is False
