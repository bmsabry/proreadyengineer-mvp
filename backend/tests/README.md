# ProReadyEngineer Backend Test Suite

Comprehensive testing suite for the FastAPI backend with 20+ test files covering unit tests, integration tests, and manual testing scripts.

## Directory Structure

```
tests/
├── conftest.py                      # Main pytest configuration with fixtures
├── test_runner.py                   # Test runner script with coverage
├── README.md                        # This file
│
├── api/                             # API-specific test utilities
│   └── __init__.py
│
├── e2e/                             # End-to-end workflow tests (future)
│   └── __init__.py
│
├── fixtures/                        # Test data factories
│   ├── __init__.py
│   └── factories.py                 # Factory functions for test entities
│
├── integration/                     # API endpoint integration tests
│   ├── __init__.py
│   ├── test_api_auth.py             # Auth endpoints (register, login, refresh, etc.)
│   ├── test_api_search.py           # Search endpoints with quota enforcement
│   ├── test_api_providers.py        # Provider public info and claims
│   ├── test_api_rfqs.py             # RFQ creation and submission
│   ├── test_api_provider_rfqs.py    # Provider RFQ access and quotes
│   ├── test_api_quotes.py           # Quote acceptance and withdrawal
│   ├── test_api_payments.py         # Payment portal and webhooks
│   ├── test_api_ads.py              # Advertising endpoints
│   └── test_api_admin.py            # Admin-only endpoints
│
├── manual/                          # Manual testing scripts
│   ├── __init__.py
│   └── test_api_curl.sh             # Bash curl commands for API testing
│
└── unit/                            # Unit tests for services
    ├── __init__.py
    ├── test_auth_service.py         # Authentication service tests
    ├── test_search_service.py       # Search and embedding service tests
    ├── test_rfq_service.py          # RFQ lifecycle service tests
    ├── test_payment_service.py      # Payment and webhook service tests
    └── test_file_service.py         # S3 and file service tests
```

## Running Tests

### Using the Test Runner

```bash
# Check test environment
python test_runner.py --check

# Show test summary
python test_runner.py --summary

# Run all tests
python test_runner.py --all

# Run only unit tests
python test_runner.py --unit

# Run only integration tests
python test_runner.py --integration

# Run with coverage
python test_runner.py --all --coverage

# Generate HTML coverage report
python test_runner.py --all --coverage --html

# Run specific test file
python test_runner.py --unit --match test_auth_service

# Run with fail-fast
python test_runner.py --integration --fail-fast
```

### Using pytest Directly

```bash
# Run all tests
pytest

# Run specific test category
pytest -m unit
pytest -m integration

# Run specific test file
pytest tests/unit/test_auth_service.py -v

# Run with coverage
pytest --cov=app --cov-report=html

# Run async tests
pytest --asyncio-mode=auto
```

## Test Categories

### Unit Tests (tests/unit/)

Fast, isolated tests that don't require database or external services:

- **test_auth_service.py**: Password hashing, JWT creation/validation, token rotation
- **test_search_service.py**: OpenAI mocking, vector similarity, scoring
- **test_rfq_service.py**: RFQ creation, match generation, unlock with SELECT FOR UPDATE
- **test_payment_service.py**: Stripe/PayPal mocking, webhook handling, idempotency
- **test_file_service.py**: S3 presigned URLs, document text extraction

### Integration Tests (tests/integration/)

Tests that verify API endpoints with database:

- **test_api_auth.py**: Registration, login, refresh, logout, password reset
- **test_api_search.py**: Search queries, upload, quota enforcement
- **test_api_providers.py**: Public provider info, claims, profile management
- **test_api_rfqs.py**: RFQ creation, submission, NDA checkout
- **test_api_provider_rfqs.py**: Teaser viewing, unlock, quote submission
- **test_api_quotes.py**: Customer quote viewing, provider quote management
- **test_api_payments.py**: Billing portal, webhook handlers
- **test_api_ads.py**: Public ad pages, checkout, asset management
- **test_api_admin.py**: Admin claim reviews, RFQ override, user suspension

### Manual Tests (tests/manual/)

- **test_api_curl.sh**: Bash script with curl commands for manual API testing

## Test Fixtures

### Database Fixtures (conftest.py)

- `db_session`: Async database session with automatic rollback
- `client`: FastAPI TestClient for API testing
- `event_loop`: Async event loop for pytest-asyncio

### Mock Fixtures

- `mock_openai`: Mocked OpenAI client
- `mock_stripe`: Mocked Stripe client
- `mock_s3_client`: Mocked boto3 S3 client
- `mock_signrequest`: Mocked SignRequest client

### User Fixtures

- `customer_user`: Pre-created customer user
- `provider_user`: Pre-created provider user
- `admin_user`: Pre-created admin user
- `advertiser_user`: Pre-created advertiser user

### Entity Fixtures

- `test_provider`: Pre-created provider with membership
- `test_provider_membership`: Provider membership record
- `test_provider_claim`: Provider claim request

### Factory Functions (fixtures/factories.py)

- `create_test_user(db, email, password, roles)`
- `create_test_provider(db, **kwargs)`
- `create_test_rfq(db, customer_id, **kwargs)`
- `create_test_quote(db, rfq_id, provider_id, **kwargs)`
- `create_test_payment_attempt(db, **kwargs)`
- `create_test_subscription(db, user_id, **kwargs)`

## Configuration

Tests use SQLite in-memory database for speed:

```python
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
```

All external APIs are mocked to prevent real API calls during tests.

## Environment Variables

Tests can be configured via environment variables:

```bash
export PYTEST_CURRENT_TEST=1
export TESTING=true
export DATABASE_URL_TEST=sqlite+aiosqlite:///:memory:
```

## Writing New Tests

### Unit Test Example

```python
import pytest
from app.services.auth_service import hash_password, verify_password

@pytest.mark.unit
class TestPasswordHashing:
    def test_password_hashing(self):
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed)
```

### Integration Test Example

```python
import pytest

@pytest.mark.integration
class TestAuthEndpoints:
    def test_login_success(self, client, customer_user):
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "customer@test.com",
                "password": "testpassword123",
            },
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
```

## CI/CD Integration

The test runner returns appropriate exit codes for CI/CD:

```bash
# CI mode
python test_runner.py --all --ci

# With XML coverage for CI tools
python test_runner.py --all --coverage --xml
```

## Coverage Requirements

Target coverage:

- Services: 80%+
- API endpoints: 70%+
- Models: 60%+

Generate and view coverage:

```bash
python test_runner.py --all --coverage --html
open tests/coverage_html/index.html
```

## Troubleshooting

### Tests failing with database errors

Ensure the database schema is created:

```python
# In conftest.py, ensure Base.metadata.create_all is called
```

### Import errors

Make sure all `__init__.py` files exist in test directories.

### Async test failures

Ensure `pytest-asyncio` is installed and configured:

```bash
pip install pytest-asyncio
```

### Mock not working

Check that mocks are properly patched at the right level:

```python
# Patch where it's used, not where it's defined
@patch("app.api.endpoints.auth.search_providers")
```

## Best Practices

1. **Use fixtures**: Don't create test data manually
2. **Mock external APIs**: Never call real Stripe/OpenAI/S3 in tests
3. **Clean up**: Use `db_session` fixture for automatic rollback
4. **Test both success and failure**: Cover error cases
5. **Use descriptive names**: Test names should describe behavior
6. **Keep tests fast**: Avoid unnecessary database queries
7. **Test state changes**: Verify database state after operations

## Contributing

When adding new tests:

1. Follow existing naming conventions (`test_*.py`)
2. Use appropriate markers (`@pytest.mark.unit`, `@pytest.mark.integration`)
3. Add fixtures to `conftest.py` if reusable
4. Update this README with new test categories

## License

Part of the ProReadyEngineer MVP.
