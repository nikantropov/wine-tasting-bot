"""БД-логика для карточек дегустации."""

import asyncpg
from database import get_pool


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tasting_cards (
    id              SERIAL PRIMARY KEY,
    participant_id  INT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    wine_id         INT NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    color           TEXT DEFAULT '',
    aroma           TEXT DEFAULT '',
    taste           TEXT DEFAULT '',
    aftertaste      TEXT DEFAULT '',
    impression      TEXT DEFAULT '',
    score           INT CHECK(score BETWEEN 1 AND 10),
    comment         TEXT DEFAULT '',
    defects         TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(participant_id, wine_id)
);
"""


async def init_cards_table():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLE)


async def upsert_card(
    participant_id: int, wine_id: int,
    color: str = "", aroma: str = "", taste: str = "",
    aftertaste: str = "", impression: str = "",
    score: int | None = None, comment: str = "", defects: str = "",
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO tasting_cards
                (participant_id, wine_id, color, aroma, taste,
                 aftertaste, impression, score, comment, defects)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (participant_id, wine_id)
            DO UPDATE SET
                color      = EXCLUDED.color,
                aroma      = EXCLUDED.aroma,
                taste      = EXCLUDED.taste,
                aftertaste = EXCLUDED.aftertaste,
                impression = EXCLUDED.impression,
                score      = EXCLUDED.score,
                comment    = EXCLUDED.comment,
                defects    = EXCLUDED.defects,
                updated_at = NOW()
            RETURNING id
        """, participant_id, wine_id, color, aroma, taste,
             aftertaste, impression, score, comment, defects)
        return row["id"]


async def update_card_field(participant_id: int, wine_id: int, field_name: str, value: str | int | None):
    allowed = {"color", "aroma", "taste", "aftertaste", "impression", "score", "comment", "defects"}
    if field_name not in allowed:
        raise ValueError(f"Unknown field: {field_name}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(f"""
            INSERT INTO tasting_cards (participant_id, wine_id)
            VALUES ($1, $2)
            ON CONFLICT (participant_id, wine_id) DO NOTHING
        """, participant_id, wine_id)
        await conn.execute(f"""
            UPDATE tasting_cards
            SET {field_name} = $1, updated_at = NOW()
            WHERE participant_id = $2 AND wine_id = $3
        """, value, participant_id, wine_id)


async def get_card(participant_id: int, wine_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM tasting_cards WHERE participant_id = $1 AND wine_id = $2
        """, participant_id, wine_id)
        return dict(row) if row else None


async def get_cards_by_session(session_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                c.id AS card_id,
                c.color, c.aroma, c.taste, c.aftertaste,
                c.impression, c.score, c.comment, c.defects,
                c.created_at, c.updated_at,
                p.name      AS participant_name,
                p.phone     AS participant_phone,
                w.name      AS wine_name,
                w.position  AS wine_position
            FROM tasting_cards c
            JOIN participants p ON p.id = c.participant_id
            JOIN wines w       ON w.id = c.wine_id
            WHERE w.session_id = $1
            ORDER BY w.position, p.name
        """, session_id)
        return [dict(r) for r in rows]


async def get_participant_cards(participant_id: int, session_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.*, w.name AS wine_name, w.position AS wine_position
            FROM tasting_cards c
            JOIN wines w ON w.id = c.wine_id
            WHERE c.participant_id = $1 AND w.session_id = $2
            ORDER BY w.position
        """, participant_id, session_id)
        return [dict(r) for r in rows]


async def get_session_cards_summary(session_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                w.id AS wine_id, w.name AS wine_name, w.position,
                COUNT(c.id) AS card_count,
                ROUND(AVG(c.score)::numeric, 2) AS avg_score
            FROM wines w
            LEFT JOIN tasting_cards c ON c.wine_id = w.id
            WHERE w.session_id = $1
            GROUP BY w.id, w.name, w.position
            ORDER BY w.position
        """, session_id)
        return [dict(r) for r in rows]


async def get_card_participants(session_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT
                p.id AS participant_id, p.name, p.phone, p.tg_id
            FROM participants p
            JOIN tasting_cards c ON c.participant_id = p.id
            JOIN wines w ON w.id = c.wine_id AND w.session_id = $1
            ORDER BY p.name
        """, session_id)
        return [dict(r) for r in rows]
