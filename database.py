import asyncpg
from config import DATABASE_URL

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id          SERIAL PRIMARY KEY,
                tg_id      BIGINT NOT NULL UNIQUE,
                phone      TEXT,
                name       TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id            SERIAL PRIMARY KEY,
                title         TEXT NOT NULL,
                tasting_date  TEXT NOT NULL,
                is_active     BOOLEAN DEFAULT TRUE,
                is_blind      BOOLEAN DEFAULT FALSE,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS wines (
                id          SERIAL PRIMARY KEY,
                session_id  INT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                position    INT NOT NULL
            );
        """)


def _row_to_dict(record) -> dict:
    if record is None:
        return None
    return dict(record)


def _rows_to_dicts(records) -> list[dict]:
    return [dict(r) for r in records]


# ============ PARTICIPANTS ============

async def get_or_create_participant(tg_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM participants WHERE tg_id = $1", tg_id
        )
        if row:
            return _row_to_dict(row)
        row = await conn.fetchrow(
            "INSERT INTO participants (tg_id) VALUES ($1) RETURNING *", tg_id
        )
        return _row_to_dict(row)


async def update_participant(tg_id: int, phone: str | None = None, name: str | None = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if phone is not None:
            await conn.execute(
                "UPDATE participants SET phone = $1 WHERE tg_id = $2", phone, tg_id
            )
        if name is not None:
            await conn.execute(
                "UPDATE participants SET name = $1 WHERE tg_id = $2", name, tg_id
            )


async def is_participant_registered(tg_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT phone, name FROM participants WHERE tg_id = $1", tg_id
        )
        return row is not None and row["phone"] and row["name"]


# ============ SESSIONS ============

async def create_session(title: str, tasting_date: str, is_blind: bool = False) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO sessions (title, tasting_date, is_blind) VALUES ($1, $2, $3) RETURNING id",
            title, tasting_date, is_blind,
        )
        return row["id"]


async def add_wine(session_id: int, name: str, position: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO wines (session_id, name, position) VALUES ($1, $2, $3)",
            session_id, name, position,
        )


async def get_active_sessions() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM sessions WHERE is_active = TRUE ORDER BY tasting_date DESC"
        )
        return _rows_to_dicts(rows)


async def get_all_sessions() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM sessions ORDER BY tasting_date DESC"
        )
        return _rows_to_dicts(rows)


async def get_session_by_id(session_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
        return _row_to_dict(row)


async def close_session(session_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE sessions SET is_active = FALSE WHERE id = $1", session_id)


async def reopen_session(session_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE sessions SET is_active = TRUE WHERE id = $1", session_id)


async def get_upcoming_sessions() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM sessions WHERE is_active = TRUE"
            " AND TO_DATE(tasting_date, 'DD.MM.YYYY') >= CURRENT_DATE"
            " ORDER BY tasting_date"
        )
        return _rows_to_dicts(rows)


# ============ WINES ============

async def get_wines_by_session(session_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM wines WHERE session_id = $1 ORDER BY position", session_id
        )
        return _rows_to_dicts(rows)


async def get_wine_id_by_position(session_id: int, position: int) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM wines WHERE session_id = $1 AND position = $2",
            session_id, position,
        )
        return row["id"] if row else None


async def get_all_registered_participants() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, tg_id, name, phone, created_at FROM participants WHERE name != '' AND phone != '' ORDER BY name"
        )
        return _rows_to_dicts(rows)
