# db/optimizer.py - ENHANCED VERSION
import asyncio
import logging
import time
from typing import Dict, Any
from sqlalchemy import text
from .session import engine, check_pool_health

class DatabaseOptimizer:
    def __init__(self, check_interval: int = 60, optimize_threshold: int = 1000):
        self.check_interval = check_interval
        self.optimize_threshold = optimize_threshold
        self.running = False
        self.connection_stats = []
        self.max_stats_history = 100

    async def start_monitoring(self):
        """Start comprehensive database monitoring"""
        self.running = True
        logging.info("📊 Starting database performance monitor with connection pooling...")

        while self.running:
            try:
                await self._check_performance()
                await self._monitor_pool_health()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logging.error(f"Database monitor error: {e}")
                await asyncio.sleep(10)

    async def _check_performance(self):
        """Run performance checks and optimizations"""
        try:
            # 1. Check pool health
            pool_health = await check_pool_health()

            # 2. Check for table bloat and vacuum if needed
            await self._check_table_bloat()

            # 3. Analyze tables for query optimization
            await self._analyze_tables()

            logging.debug(f"✅ Database performance check complete. Pool: {pool_health}")

        except Exception as e:
            logging.error(f"❌ Performance check failed: {e}")

    async def _monitor_pool_health(self):
        """Monitor connection pool health"""
        try:
            async with engine.connect() as conn:
                # Get current pool stats
                result = await conn.execute(text("""
                    SELECT 
                        count(*) as total_connections,
                        count(*) FILTER (WHERE state = 'active') as active_connections,
                        count(*) FILTER (WHERE state = 'idle') as idle_connections,
                        count(*) FILTER (WHERE wait_event IS NOT NULL) as waiting_connections
                    FROM pg_stat_activity 
                    WHERE datname = current_database()
                """))

                stats = result.fetchone()
                if stats:
                    self.connection_stats.append({
                        "timestamp": time.time(),
                        "total": stats[0],
                        "active": stats[1],
                        "idle": stats[2],
                        "waiting": stats[3]
                    })

                    # Keep only recent history
                    if len(self.connection_stats) > self.max_stats_history:
                        self.connection_stats.pop(0)

                    # Log warning if too many waiting connections
                    if stats[3] > 5:
                        logging.warning(f"High waiting connections: {stats[3]}")

        except Exception as e:
            logging.debug(f"Pool monitoring error: {e}")

    async def _check_table_bloat(self):
        """Check for table bloat and recommend vacuum"""
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("""
                    SELECT 
                        schemaname,
                        tablename,
                        n_dead_tup as dead_tuples,
                        n_live_tup as live_tuples,
                        round(n_dead_tup::numeric * 100 / (n_live_tup + n_dead_tup), 2) as dead_percentage
                    FROM pg_stat_user_tables
                    WHERE n_live_tup > 0
                    ORDER BY dead_tuples DESC
                    LIMIT 5
                """))

                bloat_info = await result.fetchall()
                for row in bloat_info:
                    if row.dead_percentage > 20:  # 20% dead tuples threshold
                        logging.info(f"Table {row.schemaname}.{row.tablename} has {row.dead_percentage}% dead tuples "
                                     f"({row.dead_tuples} dead, {row.live_tuples} live)")

        except Exception as e:
            # This might fail on SQLite, ignore
            pass

    async def _analyze_tables(self):
        """Run ANALYZE on tables for better query planning"""
        try:
            async with engine.connect() as conn:
                # Get list of tables that haven't been analyzed recently
                result = await conn.execute(text("""
                    SELECT schemaname, tablename, last_analyze, last_autoanalyze
                    FROM pg_stat_user_tables
                    WHERE (last_analyze IS NULL OR last_analyze < now() - interval '1 day')
                       OR (last_autoanalyze IS NULL OR last_autoanalyze < now() - interval '1 day')
                    ORDER BY greatest(last_analyze, last_autoanalyze) NULLS FIRST
                    LIMIT 3
                """))

                tables_to_analyze = await result.fetchall()
                for table in tables_to_analyze:
                    logging.info(f"Running ANALYZE on {table.schemaname}.{table.tablename}")
                    await conn.execute(text(f'ANALYZE {table.schemaname}."{table.tablename}"'))
                    await conn.commit()

        except Exception as e:
            # This might fail on SQLite, ignore
            pass