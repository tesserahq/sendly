# API Router Patterns

This document defines the standard patterns for creating API routers in the Sendly application.

## Overview

API routers should follow consistent patterns for response formats, error handling, and resource organization. This ensures a uniform developer experience and maintainable codebase.

## Response Format

All list endpoints should return data in the following format:
```json
{
  "data": [...]
}
```

## Router Patterns

### 1. Standard Resource Pattern

For standalone resources that don't belong to a parent entity:

**File:** `app/routers/{model}_router.py`

```python
router = APIRouter(prefix="/{model_plural}", tags=["{Model}"])

# Endpoints:
# GET /                    - list all items
# GET /{id}                - get specific item
# POST /                   - create new item
# PUT /{id}                - update item
# DELETE /{id}             - delete item
```

**Example:** `/entries`, `/users`, `/workspaces`

### 2. Nested Resource Pattern

For resources that belong to a parent entity (e.g., workspace-scoped):

**File:** `app/routers/{model}_router.py`

```python
router = APIRouter(prefix="/{parent_plural}/{parent_id}/{model_plural}", tags=["{Model}"])

# Endpoints:
# GET /{parent_id}/                    - list items for parent
# GET /{parent_id}/{id}                - get specific item
# POST /{parent_id}/                   - create new item
# PUT /{parent_id}/{id}                - update item
# DELETE /{parent_id}/{id}             - delete item
```

**Example:** `/workspaces/{workspace_id}/projects`

### 3. Mixed Nested/Standalone Pattern

For child resources where collection operations are nested but individual operations are standalone:

**File:** `app/routers/{model}_router.py`

```python
# Nested router for collection operations
router = APIRouter(prefix="/{parent_plural}/{parent_id}/{model_plural}", tags=["{Model}"])

# Standalone router for individual operations
standalone_router = APIRouter(prefix="/{model_plural}", tags=["{Model}"])

# Nested endpoints:
# GET /{parent_id}/                    - list items for parent
# POST /{parent_id}/                   - create new item

# Standalone endpoints:
# GET /{id}                            - get specific item
# PUT /{id}                            - update item
# DELETE /{id}                         - delete item
```

**Example:** Entry Updates under entries
- `GET /entries/{entry_id}/entry-updates` - list entry updates for entry
- `POST /entries/{entry_id}/entry-updates` - create entry update for entry
- `GET /entry-updates/{entry_update_id}` - get specific entry update
- `PUT /entry-updates/{entry_update_id}` - update entry update
- `DELETE /entry-updates/{entry_update_id}` - delete entry update

## Implementation Guidelines

### Dependencies

Create dependency functions in `app/routers/utils/dependencies.py`:

```python
def get_{model}_by_id(
    {model}_id: UUID,
    db: Session = Depends(get_db),
) -> {Model}:
    """FastAPI dependency to get a {model} by ID."""
    {model} = {Model}Service(db).get_{model}({model}_id)
    if {model} is None:
        raise HTTPException(status_code=404, detail="{Model} not found")
    return {model}
```

For nested resources, create scoped dependencies:

```python
def get_{model}_by_id_scoped(
    {model}_id: UUID,
    parent: ParentModel = Depends(get_parent_by_id),
    db: Session = Depends(get_db),
) -> {Model}:
    """FastAPI dependency to get a {model} by ID, scoped to parent."""
    {model} = {Model}Service(db).get_{model}({model}_id)
    if {model} is None or {model}.parent_id != parent.id:
        raise HTTPException(status_code=404, detail="{Model} not found")
    return {model}
```

### Route Implementation

#### List Endpoints
```python
@router.get("", response_model=ListResponse[{Model}])
def list_{models}(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all {models} with pagination."""
    service = {Model}Service(db)
    {models} = service.get_{models}(skip, limit)
    return ListResponse(data={models})
```

#### Get Endpoint
```python
@router.get("/{id}", response_model={Model})
def get_{model}(
    {model}: {Model}Model = Depends(get_{model}_by_id),
    current_user=Depends(get_current_user),
):
    """Get a specific {model} by ID."""
    return {model}
```

#### Create Endpoint
```python
@router.post("", response_model={Model}, status_code=status.HTTP_201_CREATED)
def create_{model}(
    {model}: {Model}Create,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new {model}."""
    service = {Model}Service(db)
    return service.create_{model}({model})
```

For nested resources, auto-set parent_id:
```python
@router.post("", response_model={Model}, status_code=status.HTTP_201_CREATED)
def create_{model}(
    {model}: {Model}Create,
    parent: ParentModel = Depends(get_parent_by_id),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new {model} for a specific parent."""
    service = {Model}Service(db)
    {model}.parent_id = parent.id  # Auto-set from URL
    return service.create_{model}({model})
```

#### Update Endpoint
```python
@router.put("/{id}", response_model={Model})
def update_{model}(
    {model}_update: {Model}Update,
    {model}: {Model}Model = Depends(get_{model}_by_id),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update an existing {model}."""
    service = {Model}Service(db)
    updated = service.update_{model}({model}.id, {model}_update)
    if updated is None:
        raise HTTPException(status_code=404, detail="{Model} not found")
    return updated
```

#### Delete Endpoint
```python
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_{model}(
    {model}: {Model}Model = Depends(get_{model}_by_id),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a {model}."""
    service = {Model}Service(db)
    success = service.delete_{model}({model}.id)
    if not success:
        raise HTTPException(status_code=404, detail="{Model} not found")
    return {"message": "{Model} deleted successfully"}
```

### Router Registration

In `app/main.py`, register all routers:

```python
# For standard pattern
app.include_router({model}.router)

# For mixed pattern
app.include_router({model}.router)
app.include_router({model}.standalone_router)
```

## Testing Patterns

### Test File Structure
Create test files as `tests/app/routers/test_{model}.py`

### Test Coverage
- List endpoints (with pagination)
- Get endpoints (success and 404 cases)
- Create endpoints (success, validation errors, parent not found)
- Update endpoints (success, 404 cases)
- Delete endpoints (success, 404 cases)
- For nested resources: cross-parent access prevention
- For mixed patterns: both nested and standalone operations

### Example Test Structure
```python
def test_list_{models}(client, setup_{model}):
    """Test GET /{model_plural} endpoint."""
    {model} = setup_{model}
    response = client.get(f"/{model_plural}")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)

def test_get_{model}(client, setup_{model}):
    """Test GET /{model_plural}/{id} endpoint."""
    {model} = setup_{model}
    response = client.get(f"/{model_plural}/{model.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str({model}.id)

def test_get_{model}_not_found(client):
    """Test GET /{model_plural}/{id} with non-existent {model}."""
    fake_id = uuid4()
    response = client.get(f"/{model_plural}/{fake_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "{Model} not found"
```

## Error Handling

- Use appropriate HTTP status codes (200, 201, 204, 404, 422)
- Return consistent error message format: `{"detail": "Error message"}`
- Validate input data using Pydantic schemas
- Handle 404 cases for non-existent resources
- For nested resources, validate parent exists before child operations

## Security

- All endpoints require authentication (`current_user=Depends(get_current_user)`)
- Validate parent scope for nested resources
- Use dependency injection for resource validation
- Don't include parent_id in request body when it's in the URL path

## When to Use Each Pattern

- **Standard Pattern**: Use for top-level resources (users, workspaces, entries)
- **Nested Pattern**: Use for resources that are always scoped to a parent (workspace projects)
- **Mixed Pattern**: Use for child resources where individual operations are commonly accessed directly (entry_updates, attachments)

This pattern ensures consistency across the API while providing flexibility for different resource relationships.
