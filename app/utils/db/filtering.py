from typing import Any, Dict, Callable
from sqlalchemy.orm import Query
from sqlalchemy.sql import ColumnElement


# Supported operators
OPERATORS: Dict[str, Callable[[ColumnElement, Any], ColumnElement]] = {
    "==": lambda col, val: col == val,
    "=": lambda col, val: col == val,
    "!=": lambda col, val: col != val,
    ">": lambda col, val: col > val,
    "<": lambda col, val: col < val,
    ">=": lambda col, val: col >= val,
    "<=": lambda col, val: col <= val,
    "ilike": lambda col, val: col.ilike(val),
    "like": lambda col, val: col.like(val),
    "in": lambda col, val: col.in_(val if isinstance(val, list) else [val]),
    "not_in": lambda col, val: ~col.in_(val if isinstance(val, list) else [val]),
}


def apply_filters(query: Query, model: Any, filters: Dict[str, Any]) -> Query:
    """
    Dynamically applies SQLAlchemy filters to a query based on a dictionary input.

    This function allows flexible field-level filtering with support for various SQL operators.
    It can be reused across services to consistently apply filter logic to SQLAlchemy models.

    Args:
        query (Query): The initial SQLAlchemy query object.
        model (Any): The SQLAlchemy model class used for field reference.
        filters (Dict[str, Any]): A dictionary where keys are model field names and values are:
            - A direct value (implying equality, e.g. {"status": "active"})
            - A dict with an 'operator' and a 'value', e.g. {"status": {"operator": "!=", "value": "inactive"}}

    Supported Operators:
        "==", "=", "!=", ">", "<", ">=", "<=", "ilike", "like", "in", "not_in"

    Returns:
        Query: The SQLAlchemy query with the applied filters.

    Example:
        filters = {
            "name": {"operator": "ilike", "value": "%john%"},
            "email": {"operator": "!=", "value": "spam@example.com"},
            "is_active": True,
            "role": {"operator": "in", "value": ["admin", "user"]}
        }

        query = session.query(User)
        filtered_query = apply_filters(query, User, filters)
        users = filtered_query.all()
    """
    for field, condition in filters.items():
        column = getattr(model, field, None)
        if column is None:
            continue  # Skip invalid fields silently; or raise ValueError for stricter behavior

        # Operator-based filtering
        if isinstance(condition, dict) and "operator" in condition:
            operator = condition["operator"]
            value = condition.get("value")
            op_func = OPERATORS.get(operator)
            if op_func:
                query = query.filter(op_func(column, value))
            else:
                # Fall back to equality if unknown operator
                query = query.filter(column == value)
        else:
            # Simple equality
            query = query.filter(column == condition)

    return query
