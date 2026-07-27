# app/auth/rbac.py

from typing import Awaitable, Callable, Optional
from fastapi import Request
from tessera_sdk.server.dependencies.authorization import authorize

ProjectResolver = Callable[[Request], Awaitable[Optional[str]]]

PREFIX = "sendly"


class RBACActions:
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


def fixed_domain_resolver(value: str) -> ProjectResolver:
    """A project_resolver that always returns `value`, regardless of the
    request — for authorizing against a resource's actual project_id
    (fetched from the DB) rather than a caller-supplied one.

    Use this after loading a resource by a globally-unique id (not scoped
    by project in the query itself): authorize against the resource's real
    project_id, not whatever the caller happened to pass in. Otherwise a
    caller could read another project's resource by passing their own
    (valid, authorized) project_id in the query string/body — an IDOR.
    """

    async def resolver(_request: Request) -> str:
        return value

    return resolver


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
