import ast
from pathlib import Path

APP_ROOT = Path(__file__).parents[2] / "app"
SCANNED_DIRS = ("repositories", "commands", "routers", "tasks", "services")
EARLY_COMMIT_ALLOWLIST = {
    ("commands/send_email_command.py", "execute"),
    ("tasks/send_broadcast_chunk_task.py", "_send_chunk"),
}


def iter_python_files():
    for directory in SCANNED_DIRS:
        yield from (APP_ROOT / directory).rglob("*.py")


def enclosing_function(node, parents):
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(current)
    return "<module>"


def test_transaction_lifecycle_calls_stay_at_execution_boundaries():
    violations = []
    for path in iter_python_files():
        tree = ast.parse(path.read_text())
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        relative_path = str(path.relative_to(APP_ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            method = node.func.attr
            function = enclosing_function(node, parents)
            if (
                method == "commit"
                and (relative_path, function) in EARLY_COMMIT_ALLOWLIST
            ):
                continue
            if method in {"commit", "rollback", "close", "begin"}:
                violations.append(
                    f"{relative_path}:{node.lineno} {function} calls {method}()"
                )

    assert violations == []


def test_application_sessions_are_created_only_by_database_infrastructure():
    violations = []
    forbidden_calls = {"SessionLocal", "sessionmaker"}
    forbidden_manager_methods = {"create_session", "get_db", "db_session"}
    for path in APP_ROOT.rglob("*.py"):
        if path.name == "db.py":
            continue
        tree = ast.parse(path.read_text())
        relative_path = str(path.relative_to(APP_ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                violations.append(
                    f"{relative_path}:{node.lineno} calls {node.func.id}()"
                )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden_manager_methods
            ):
                violations.append(
                    f"{relative_path}:{node.lineno} calls db_manager.{node.func.attr}()"
                )

    assert violations == []


def test_bulk_mutations_keep_the_identity_map_synchronized():
    violations = []
    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        relative_path = str(path.relative_to(APP_ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "expire_all":
                violations.append(f"{relative_path}:{node.lineno} calls expire_all()")
            for keyword in node.keywords:
                if (
                    keyword.arg == "synchronize_session"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    violations.append(
                        f"{relative_path}:{node.lineno} disables session synchronization"
                    )
                if keyword.arg != "execution_options" or not isinstance(
                    keyword.value, ast.Dict
                ):
                    continue
                options = zip(keyword.value.keys, keyword.value.values)
                for key, value in options:
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "synchronize_session"
                        and isinstance(value, ast.Constant)
                        and value.value is False
                    ):
                        violations.append(
                            f"{relative_path}:{node.lineno} disables session synchronization"
                        )

    assert violations == []
