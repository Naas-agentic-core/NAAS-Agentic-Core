#!/usr/bin/env python
"""
Automated SQL Check to verify that no duplicate writes exist in the database.
Part of the System Immunity Mode against dual-write regressions.
"""

import asyncio
import sys
import logging
from sqlalchemy import text

# Import the database factory from the monolithic app
from app.core.database import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("duplicate_check")

async def main() -> None:
    async with async_session_factory() as db:
        query = text('''
            SELECT conversation_id, content, role, COUNT(*) as cnt
            FROM customer_messages
            GROUP BY conversation_id, content, role
            HAVING COUNT(*) > 1
        ''')
        try:
            result = await db.execute(query)
            duplicates = result.fetchall()
            
            if duplicates:
                logger.critical("[CRITICAL FAILURE] Duplicate messages detected in the database!")
                for row in duplicates:
                    logger.error(f"Duplicate found: conversation_id={row.conversation_id}, role={row.role}, count={row.cnt}")
                sys.exit(1)
            else:
                logger.info("[SUCCESS] No duplicate writes found. System Immunity is intact.")
                sys.exit(0)
        except Exception as e:
            logger.error(f"Failed to execute check: {e}")
            sys.exit(2)

if __name__ == "__main__":
    asyncio.run(main())
