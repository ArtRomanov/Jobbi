from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(
    db: AsyncSession,
    query: Select[Any],
    page: int,
    per_page: int,
    *,
    scalars: bool = True,
) -> tuple[list[Any], int]:
    """Execute a query with pagination, returning (items, total_count).

    When scalars=True (default), returns ORM model instances via result.scalars().
    When scalars=False, returns raw rows from join projections via result.all().
    """
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    paginated = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(paginated)

    if scalars:
        return list(result.scalars().all()), total
    return list(result.all()), total
