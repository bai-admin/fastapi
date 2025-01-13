# FastAPI Project Refactoring Plan

## Current Issues
- Unnecessary complexity in O365 authentication
- Token storage needs better security in production
- Service layer needs better abstraction
- Configuration management needs standardization
- Inconsistent project structure

## Proposed Directory Structure
```
fastapi/src/
├── o365/
│   ├── api/             # API route handlers
│   │   ├── __init__.py
│   │   ├── auth.py     # O365 auth endpoints
│   │   ├── mail.py     # Mail-related endpoints
│   │   └── router.py   # Router aggregation and configuration
│   ├── service.py      # Core O365 service
│   ├── config.py       # O365-specific settings
│   ├── schemas/        # O365 data models
│   │   ├── __init__.py
│   │   ├── auth.py    # Auth-related schemas
│   │   └── mail.py    # Mail-related schemas
│   ├── exceptions.py   # O365-specific exceptions
│   ├── token_backends/ # O365 token storage implementations
│   │   ├── __init__.py
│   │   ├── railway.py # Railway token backend
│   │   └── file.py    # Local filesystem backend
│   └── dependencies.py # O365 dependency injection
├── core/
│   ├── config.py      # Global app configuration
│   ├── exceptions.py  # Base exception classes
│   └── schemas.py     # Base Pydantic models
└── main.py           # FastAPI app initialization and router registration

tests/
├── o365/
│   ├── test_token_backends/
│   └── test_service.py
└── conftest.py
```

## Key Changes

### 1. O365 Authentication
- Remove custom PKCE implementation
- Use python-o365's built-in authorization code flow
- Implement proper token storage with Railway sealed variables
- Keep FileSystemTokenBackend for local development
- Ensure offline_access scope for long-term token refresh

### 2. Token Storage Security
- Use Railway sealed variables for tokens in production
- Implement proper token refresh handling
- Ensure environment-specific token isolation
- Add token backend factory based on environment

### 3. Project Structure
- Move from `app/` to `src/` following FastAPI best practices
- Organize by domain instead of technical function
- Consolidate O365 components into single domain directory
- Create `core/` module for shared components

### 4. FastAPI Integration
- Move auth endpoints to dedicated router
- Use FastAPI dependency injection for service management
- Implement proper request lifecycle scoping
- Add comprehensive error handling

## Implementation Plan

### Phase 1: O365 Authentication
1. Remove custom PKCE implementation
2. Update O365Service to use library's auth flow
3. Implement token backend factory
4. Add sealed variable support for production

### Phase 2: Project Restructure
1. Create new directory structure
2. Move and consolidate O365 components
3. Update imports and dependencies
4. Clean up old structure

### Phase 3: FastAPI Integration
1. Create dedicated O365 router
2. Implement proper dependency injection
3. Add error handling
4. Update endpoint implementations

### Phase 4: Testing & Documentation
1. Set up testing infrastructure
2. Write unit tests
3. Add API documentation
4. Update README

## Code Examples

### O365 Service Setup
```python
# src/o365/service.py
from O365 import Account
from .token_backends import get_token_backend

class O365Service:
    def __init__(self, config: O365Config):
        self.config = config
        self.token_backend = get_token_backend()
        self._account = None
        
    @property
    def account(self) -> Account:
        if not self._account:
            self._account = Account(
                credentials=(self.config.client_id, self.config.client_secret),
                token_backend=self.token_backend,
                tenant_id=self.config.tenant_id,
                scopes=['offline_access', 'Mail.Read']
            )
        return self._account
```

### Token Backend Factory
```python
# src/o365/token_backends/__init__.py
import os
from O365.utils.token import FileSystemTokenBackend
from .railway import RailwayTokenBackend

def get_token_backend():
    """Get appropriate token backend based on environment."""
    if os.getenv('RAILWAY_ENVIRONMENT_ID'):
        return RailwayTokenBackend()
    
    # Local development uses FileSystemTokenBackend
    token_dir = Path('tokens')
    token_dir.mkdir(parents=True, exist_ok=True)
    env = os.getenv('ENVIRONMENT', 'local')
    return FileSystemTokenBackend(
        token_path=str(token_dir / f"o365_token_{env}.txt")
    )
```

### O365 Router
```python
# src/o365/api/auth.py
from fastapi import APIRouter, Depends, HTTPException
from ..service import O365Service
from ..dependencies import get_o365_service
from ..schemas.auth import AuthResponse

router = APIRouter()

@router.get("/url")
def get_auth_url(
    service: O365Service = Depends(get_o365_service)
):
    """Get O365 authentication URL."""
    if not service.account.is_authenticated:
        return service.account.get_authorization_url()
    return {"message": "Already authenticated"}

# src/o365/api/mail.py
from fastapi import APIRouter, Depends
from ..service import O365Service
from ..dependencies import get_o365_service
from ..schemas.mail import MessageList

router = APIRouter()

@router.get("/recent", response_model=MessageList)
def get_recent_messages(
    service: O365Service = Depends(get_o365_service)
):
    """Get recent messages."""
    return {"messages": service.get_recent_messages()}

# src/o365/api/router.py
from fastapi import APIRouter
from . import auth, mail

router = APIRouter(prefix="/o365", tags=["O365"])
router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(mail.router, prefix="/mail", tags=["Mail"])
```

## Migration Steps
1. Remove custom PKCE implementation
2. Implement token backend factory
3. Update O365Service implementation
4. Create new directory structure
5. Move and update files
6. Update imports
7. Add tests
8. Verify functionality

## Security Considerations
- Use Railway sealed variables for tokens in production
- Ensure tokens are environment-specific
- Implement proper token refresh handling
- Keep local development tokens in .gitignore
- Use offline_access scope for long-term access

## Future Considerations
- Add rate limiting
- Implement proper monitoring
- Add health checks
- Consider caching layer 