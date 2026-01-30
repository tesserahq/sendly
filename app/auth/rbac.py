# app/auth/rbac.py

from typing import Awaitable, Callable, Optional
from fastapi import Request
from tessera_sdk.utils.authorization_dependency import authorize

ProjectResolver = Callable[[Request], Awaitable[Optional[str]]]

PREFIX = "sendly"


class RBACActions:
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


def build_rbac_dependencies(
    *,
    resource: str,
    project_resolver: ProjectResolver,
):
    return {
        "create": authorize(
            resource=f"{PREFIX}.{resource}",
            action=RBACActions.CREATE,
            domain_resolver=project_resolver,
        ),
        "read": authorize(
            resource=f"{PREFIX}.{resource}",
            action=RBACActions.READ,
            domain_resolver=project_resolver,
        ),
        "update": authorize(
            resource=f"{PREFIX}.{resource}",
            action=RBACActions.UPDATE,
            domain_resolver=project_resolver,
        ),
        "delete": authorize(
            resource=f"{PREFIX}.{resource}",
            action=RBACActions.DELETE,
            domain_resolver=project_resolver,
        ),
    }
