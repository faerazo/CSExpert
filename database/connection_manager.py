#!/usr/bin/env python3
"""
Database Connection Manager

Handles SQLite database connections with pooling, transaction management,
and schema initialization for the CSExpert system.
"""

import sqlite3
import logging
import threading
import time
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Generator, Dict, Any, List
from queue import Queue, Empty
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """Connection pool for SQLite database with thread safety."""
    
    def __init__(self, database_path: str, pool_size: int = 5, timeout: int = 30):
        """
        Initialize connection pool.
        
        Args:
            database_path: Path to SQLite database file
            pool_size: Maximum number of connections in pool
            timeout: Connection timeout in seconds
        """
        self.database_path = Path(database_path)
        self.pool_size = pool_size
        self.timeout = timeout
        self.pool = Queue(maxsize=pool_size)
        self.lock = threading.Lock()
        self._active_connections = 0
        self._total_connections_created = 0
        
        # Ensure database directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Database connection pool initialized: {database_path} (pool size: {pool_size})")
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with optimal settings."""
        conn = sqlite3.connect(
            self.database_path,
            check_same_thread=False,  # Allow sharing between threads
            timeout=self.timeout
        )
        
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Optimize SQLite settings for performance
        conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
        conn.execute("PRAGMA synchronous = NORMAL")  # Balanced performance/safety
        conn.execute("PRAGMA cache_size = 10000")  # 10MB cache
        conn.execute("PRAGMA temp_store = MEMORY")  # Use memory for temp tables
        conn.execute("PRAGMA mmap_size = 268435456")  # 256MB memory-mapped I/O
        
        # Use row factory for dictionary-like access
        conn.row_factory = sqlite3.Row
        
        self._total_connections_created += 1
        logger.debug(f"Created new database connection (total: {self._total_connections_created})")
        
        return conn
    
    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Get a connection from the pool with context manager support.
        
        Yields:
            SQLite connection from pool
        """
        conn = None
        try:
            # Try to get connection from pool
            try:
                conn = self.pool.get_nowait()
                logger.debug("Retrieved connection from pool")
            except Empty:
                # Pool is empty, create new connection if under limit
                with self.lock:
                    if self._active_connections < self.pool_size:
                        conn = self._create_connection()
                        self._active_connections += 1
                        logger.debug(f"Created new connection (active: {self._active_connections})")
                    else:
                        # Wait for connection to become available
                        logger.debug("Pool full, waiting for connection...")
                        conn = self.pool.get(timeout=self.timeout)
            
            yield conn
            
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            if conn:
                # Rollback any pending transaction on error
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            # Return connection to pool
            if conn:
                try:
                    # Ensure no pending transaction
                    conn.commit()
                    self.pool.put(conn)
                    logger.debug("Returned connection to pool")
                except Exception as e:
                    logger.error(f"Error returning connection to pool: {e}")
                    # Don't return damaged connection to pool
                    with self.lock:
                        self._active_connections -= 1
    
    def close_all(self):
        """Close all connections in the pool."""
        logger.info("Closing all database connections...")
        
        closed_count = 0
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
                closed_count += 1
            except Empty:
                break
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        
        logger.info(f"Closed {closed_count} database connections")
        
        with self.lock:
            self._active_connections = 0
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return {
            'pool_size': self.pool_size,
            'active_connections': self._active_connections,
            'available_connections': self.pool.qsize(),
            'total_connections_created': self._total_connections_created,
            'database_path': str(self.database_path)
        }


class DatabaseManager:
    """High-level database manager with schema management and utilities."""
    
    def __init__(self, database_path: str = "data/csexpert.db", pool_size: int = 5):
        """
        Initialize database manager.
        
        Args:
            database_path: Path to SQLite database file
            pool_size: Connection pool size
        """
        self.database_path = Path(database_path)
        self.pool = DatabaseConnectionPool(database_path, pool_size)
        self.schema_initialized = False
        
        logger.info(f"Database manager initialized: {database_path}")
    
    def initialize_database(self, schema_file: str = "database/schema.sql") -> bool:
        """
        Initialize database with schema from SQL file.
        
        Args:
            schema_file: Path to SQL schema file
            
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            schema_path = Path(schema_file)
            if not schema_path.exists():
                logger.error(f"Schema file not found: {schema_file}")
                return False
            
            with schema_path.open('r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            with self.pool.get_connection() as conn:
                # Check if schema already exists
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='courses'"
                )
                if cursor.fetchone():
                    logger.info("Database schema already exists")
                    self.schema_initialized = True
                    return True
                
                # Execute schema
                logger.info("Initializing database schema...")
                conn.executescript(schema_sql)
                conn.commit()
                
                logger.info("Database schema initialized successfully")
                self.schema_initialized = True
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}")
            return False
    
    def check_schema_version(self) -> Optional[str]:
        """Check current database schema version."""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
                )
                row = cursor.fetchone()
                return row['version'] if row else None
        except Exception as e:
            logger.error(f"Failed to check schema version: {e}")
            return None
    
    def execute_query(self, query: str, parameters: tuple = None) -> List[sqlite3.Row]:
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL query string
            parameters: Query parameters
            
        Returns:
            List of result rows
        """
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(query, parameters or ())
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def execute_update(self, query: str, parameters: tuple = None) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query.
        
        Args:
            query: SQL query string
            parameters: Query parameters
            
        Returns:
            Number of affected rows
        """
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(query, parameters or ())
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Update execution failed: {e}")
            raise
    
    def execute_batch(self, queries: List[tuple]) -> List[int]:
        """
        Execute multiple queries in a single transaction.
        
        Args:
            queries: List of (query, parameters) tuples
            
        Returns:
            List of affected row counts
        """
        results = []
        try:
            with self.pool.get_connection() as conn:
                for query, parameters in queries:
                    cursor = conn.execute(query, parameters or ())
                    results.append(cursor.rowcount)
                conn.commit()
                return results
        except Exception as e:
            logger.error(f"Batch execution failed: {e}")
            raise
    
    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for database transactions.
        
        Yields:
            Database connection with transaction support
        """
        with self.pool.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table structure."""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get table info for {table_name}: {e}")
            return []
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics and health information."""
        try:
            with self.pool.get_connection() as conn:
                stats = {}
                
                # Table counts
                cursor = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                tables = [row['name'] for row in cursor.fetchall()]
                
                stats['tables'] = {}
                for table in tables:
                    try:
                        cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table}")
                        count = cursor.fetchone()['count']
                        stats['tables'][table] = count
                    except:
                        stats['tables'][table] = 'error'
                
                # Database size
                cursor = conn.execute("PRAGMA page_count")
                page_count = cursor.fetchone()[0]
                cursor = conn.execute("PRAGMA page_size")
                page_size = cursor.fetchone()[0]
                stats['database_size_bytes'] = page_count * page_size
                
                # Connection pool stats
                stats['connection_pool'] = self.pool.get_pool_stats()
                
                # Schema version
                stats['schema_version'] = self.check_schema_version()
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {'error': str(e)}
    
    def backup_database(self, backup_path: str) -> bool:
        """Create a backup of the database."""
        try:
            backup_path = Path(backup_path)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            with self.pool.get_connection() as conn:
                # Use SQLite backup API for consistent backup
                backup = sqlite3.connect(backup_path)
                conn.backup(backup)
                backup.close()
                
            logger.info(f"Database backed up to: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return False
    
    def vacuum_database(self) -> bool:
        """Optimize database by running VACUUM."""
        try:
            with self.pool.get_connection() as conn:
                conn.execute("VACUUM")
                conn.commit()
            
            logger.info("Database VACUUM completed")
            return True
            
        except Exception as e:
            logger.error(f"Database VACUUM failed: {e}")
            return False
    
    def get_connection(self):
        """Get a database connection (delegate to pool)."""
        return self.pool.get_connection()
    
    def close(self):
        """Close the database manager and all connections."""
        logger.info("Closing database manager...")
        self.pool.close_all()
        self.schema_initialized = False


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager(database_path: str = "data/csexpert.db", pool_size: int = 5) -> DatabaseManager:
    """Get the global database manager instance (singleton pattern)."""
    global _db_manager
    
    if _db_manager is None or str(_db_manager.database_path) != database_path:
        if _db_manager:
            _db_manager.close()
        _db_manager = DatabaseManager(database_path, pool_size)
    
    return _db_manager


def initialize_database(schema_file: str = "database/schema.sql", database_path: str = "data/csexpert.db") -> bool:
    """Initialize the database with schema (convenience function)."""
    db_manager = get_database_manager(database_path)
    return db_manager.initialize_database(schema_file)


def close_database():
    """Close the global database manager (convenience function)."""
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None


if __name__ == "__main__":
    # Test the database connection manager
    logger.info("Testing Database Connection Manager...")
    
    # Initialize database
    db_manager = get_database_manager("data/test_csexpert.db")
    
    if db_manager.initialize_database():
        logger.info("Database initialization successful")
        
        # Test basic operations
        stats = db_manager.get_database_stats()
        logger.info(f"Database stats: {json.dumps(stats, indent=2, default=str)}")
        
        # Test connection pooling
        logger.info("Testing connection pool...")
        with db_manager.pool.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM programs")
            count = cursor.fetchone()[0]
            logger.info(f"Programs table count: {count}")
        
        logger.info("Database manager test completed successfully")
    else:
        logger.error("Database initialization failed")
    
    # Clean up
    close_database()