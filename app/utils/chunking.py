from typing import Iterator, List, Sequence, TypeVar

T = TypeVar("T")


def chunked(items: Sequence[T], size: int) -> Iterator[List[T]]:
    """Yield successive chunks of at most `size` items from `items`."""
    for i in range(0, len(items), size):
        yield list(items[i : i + size])
