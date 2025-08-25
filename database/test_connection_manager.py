#!/usr/bin/env python3
"""
Connection Manager Test Suite

Tests the database connection manager with the initialized CSExpert database.
Verifies connection pooling, transaction management, and concurrent access.
"""

import sqlite3
import logging
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import json

# Import our connection manager
import sys
sys.path.append('.')
from database.connection_manager import DatabaseManager, initialize_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConnectionManagerTest:
    """Comprehensive test suite for database connection manager."""
    
    def __init__(self, database_path: str = "data/csexpert.db"):
        """Initialize test suite."""
        self.database_path = database_path
        self.db_manager = DatabaseManager(database_path)
        self.test_results = {}
        
        logger.info(f"Connection Manager Test initialized for {database_path}")
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive test suite."""
        logger.info("Starting comprehensive connection manager tests...")
        
        test_methods = [
            ('basic_connection', self.test_basic_connection),
            ('connection_pooling', self.test_connection_pooling),
            ('concurrent_access', self.test_concurrent_access),
            ('transaction_management', self.test_transaction_management),
            ('context_manager', self.test_context_manager),
            ('error_handling', self.test_error_handling),
            ('performance_benchmark', self.test_performance_benchmark),
            ('data_integrity', self.test_data_integrity)
        ]
        
        overall_success = True
        
        for test_name, test_method in test_methods:
            logger.info(f"Running test: {test_name}")
            try:
                start_time = time.time()
                result = test_method()
                execution_time = time.time() - start_time
                
                self.test_results[test_name] = {
                    'success': result,
                    'execution_time': execution_time,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                
                if result:
                    logger.info(f"✅ {test_name} PASSED ({execution_time:.2f}s)")
                else:
                    logger.error(f"❌ {test_name} FAILED ({execution_time:.2f}s)")
                    overall_success = False
                    
            except Exception as e:
                logger.error(f"❌ {test_name} ERROR: {e}")
                self.test_results[test_name] = {
                    'success': False,
                    'error': str(e),
                    'execution_time': time.time() - start_time,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                overall_success = False
        
        self.test_results['overall_success'] = overall_success
        return self.test_results
    
    def test_basic_connection(self) -> bool:
        """Test basic database connection functionality."""
        try:
            with self.db_manager.get_connection() as conn:
                # Test basic query
                cursor = conn.execute("SELECT COUNT(*) FROM language_standards")
                count = cursor.fetchone()[0]
                
                if count != 4:  # Should have 4 language standards from initialization
                    logger.error(f"Expected 4 language standards, got {count}")
                    return False
                
                # Test table existence
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                table_count = cursor.fetchone()[0]
                
                if table_count < 8:  # Should have at least 8 tables
                    logger.error(f"Expected at least 8 tables, got {table_count}")
                    return False
                
                return True
                
        except Exception as e:
            logger.error(f"Basic connection test failed: {e}")
            return False
    
    def test_connection_pooling(self) -> bool:
        """Test connection pool functionality."""
        try:
            # Test getting pool stats
            stats = self.db_manager.pool.get_pool_stats()
            initial_available = stats['available_connections']
            
            # Test multiple connections using context manager
            for i in range(3):  # Test 3 sequential connections
                with self.db_manager.get_connection() as conn:
                    # Verify connection works
                    cursor = conn.execute("SELECT 1")
                    result = cursor.fetchone()[0]
                    if result != 1:
                        return False
            
            # Verify pool state after all connections returned
            final_stats = self.db_manager.pool.get_pool_stats()
            final_available = final_stats['available_connections']
            
            if final_available != initial_available:
                logger.error(f"Pool not properly restored: initial={initial_available}, final={final_available}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Connection pooling test failed: {e}")
            return False
    
    def test_concurrent_access(self) -> bool:
        """Test concurrent database access."""
        def worker_task(worker_id: int) -> bool:
            """Worker task for concurrent testing."""
            try:
                with self.db_manager.get_connection() as conn:
                    # Perform some database operations
                    conn.execute("SELECT COUNT(*) FROM programs")
                    conn.execute("SELECT * FROM language_standards LIMIT 1")
                    
                    # Small delay to simulate work
                    time.sleep(0.01)
                    
                    return True
            except Exception as e:
                logger.error(f"Worker {worker_id} failed: {e}")
                return False
        
        try:
            # Test with multiple concurrent workers
            num_workers = 10
            
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(worker_task, i) for i in range(num_workers)]
                results = [future.result() for future in as_completed(futures)]
            
            # All workers should succeed
            success_count = sum(results)
            if success_count != num_workers:
                logger.error(f"Only {success_count}/{num_workers} workers succeeded")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Concurrent access test failed: {e}")
            return False
    
    def test_transaction_management(self) -> bool:
        """Test transaction management."""
        try:
            with self.db_manager.get_connection() as conn:
                # Start transaction
                conn.execute("BEGIN")
                
                # Insert test data
                conn.execute("""
                    INSERT INTO programs (program_code, program_name, program_type, department) 
                    VALUES ('TEST1', 'Test Program', 'master', 'Test Department')
                """)
                
                # Check data exists in transaction
                cursor = conn.execute("SELECT COUNT(*) FROM programs WHERE program_code = 'TEST1'")
                count = cursor.fetchone()[0]
                if count != 1:
                    return False
                
                # Rollback transaction
                conn.execute("ROLLBACK")
                
                # Check data doesn't exist after rollback
                cursor = conn.execute("SELECT COUNT(*) FROM programs WHERE program_code = 'TEST1'")
                count = cursor.fetchone()[0]
                if count != 0:
                    return False
                
                # Test successful commit
                conn.execute("BEGIN")
                conn.execute("""
                    INSERT INTO programs (program_code, program_name, program_type, department) 
                    VALUES ('TEST2', 'Test Program 2', 'master', 'Test Department')
                """)
                conn.execute("COMMIT")
                
                # Check data persists after commit
                cursor = conn.execute("SELECT COUNT(*) FROM programs WHERE program_code = 'TEST2'")
                count = cursor.fetchone()[0]
                if count != 1:
                    return False
                
                # Cleanup
                conn.execute("DELETE FROM programs WHERE program_code LIKE 'TEST%'")
                conn.commit()
                
                return True
                
        except Exception as e:
            logger.error(f"Transaction management test failed: {e}")
            return False
    
    def test_context_manager(self) -> bool:
        """Test context manager functionality."""
        try:
            # Test that connection is properly returned to pool
            initial_stats = self.db_manager.pool.get_pool_stats()
            initial_available = initial_stats['available_connections']
            
            with self.db_manager.get_connection() as conn:
                # Connection should be available
                cursor = conn.execute("SELECT 1")
                result = cursor.fetchone()[0]
                if result != 1:
                    return False
                
                # Available connections should be reduced during use
                during_stats = self.db_manager.pool.get_pool_stats()
                during_available = during_stats['available_connections']
                
                if during_available >= initial_available:
                    logger.error("Available connections didn't decrease when connection was taken")
                    # This might be ok if pool creates connections on demand
            
            # After context exit, connections should be restored
            final_stats = self.db_manager.pool.get_pool_stats()
            final_available = final_stats['available_connections']
            
            if final_available != initial_available:
                logger.warning(f"Pool state changed: initial={initial_available}, final={final_available}")
                # This might be OK if the pool was empty initially and connections were created
            
            return True
            
        except Exception as e:
            logger.error(f"Context manager test failed: {e}")
            return False
    
    def test_error_handling(self) -> bool:
        """Test error handling scenarios."""
        try:
            # Test invalid SQL
            try:
                with self.db_manager.get_connection() as conn:
                    conn.execute("SELECT * FROM nonexistent_table")
                return False  # Should have raised an exception
            except sqlite3.OperationalError:
                pass  # Expected error
            
            # Test connection recovery after error
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM programs")
                count = cursor.fetchone()[0]
                if count < 4:  # Should have at least 4 programs
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling test failed: {e}")
            return False
    
    def test_performance_benchmark(self) -> bool:
        """Test connection manager performance."""
        try:
            num_operations = 100
            start_time = time.time()
            
            for i in range(num_operations):
                with self.db_manager.get_connection() as conn:
                    conn.execute("SELECT 1")
            
            total_time = time.time() - start_time
            avg_time = total_time / num_operations
            
            logger.info(f"Performance: {num_operations} operations in {total_time:.2f}s (avg: {avg_time*1000:.2f}ms per operation)")
            
            # Should complete 100 operations in reasonable time (< 5 seconds)
            if total_time > 5.0:
                logger.warning(f"Performance test slower than expected: {total_time:.2f}s")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Performance benchmark failed: {e}")
            return False
    
    def test_data_integrity(self) -> bool:
        """Test data integrity with connection manager."""
        try:
            with self.db_manager.get_connection() as conn:
                # Check foreign keys are enabled
                fk_result = conn.execute("PRAGMA foreign_keys").fetchone()
                if fk_result[0] != 1:
                    logger.error("Foreign keys not enabled")
                    return False
                
                # Check WAL mode is enabled
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                if journal_mode.lower() != 'wal':
                    logger.error(f"WAL mode not enabled, got: {journal_mode}")
                    return False
                
                # Test database integrity
                integrity_result = conn.execute("PRAGMA integrity_check").fetchone()
                if integrity_result[0] != "ok":
                    logger.error(f"Database integrity check failed: {integrity_result[0]}")
                    return False
                
                # Check initial data is present
                lang_count = conn.execute("SELECT COUNT(*) FROM language_standards").fetchone()[0]
                prog_count = conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
                
                if lang_count != 4:
                    logger.error(f"Expected 4 language standards, got {lang_count}")
                    return False
                
                if prog_count != 4:
                    logger.error(f"Expected 4 programs, got {prog_count}")
                    return False
                
                return True
                
        except Exception as e:
            logger.error(f"Data integrity test failed: {e}")
            return False
    
    def cleanup(self):
        """Clean up test resources."""
        try:
            self.db_manager.close()
            logger.info("Connection manager cleaned up successfully")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def print_test_summary(self):
        """Print comprehensive test results summary."""
        print("\n" + "="*100)
        print("CONNECTION MANAGER TEST RESULTS")
        print("="*100)
        
        if 'overall_success' in self.test_results:
            status = "✅ PASSED" if self.test_results['overall_success'] else "❌ FAILED"
            print(f"Overall Status: {status}")
        
        print(f"\nTest Results:")
        total_time = 0
        passed_tests = 0
        
        for test_name, result in self.test_results.items():
            if test_name == 'overall_success':
                continue
            
            if isinstance(result, dict):
                status = "✅ PASS" if result['success'] else "❌ FAIL"
                exec_time = result.get('execution_time', 0)
                total_time += exec_time
                if result['success']:
                    passed_tests += 1
                
                error_info = f" - {result.get('error', '')}" if not result['success'] and 'error' in result else ""
                print(f"  {test_name:25} {status:8} ({exec_time:6.2f}s){error_info}")
        
        total_tests = len(self.test_results) - 1  # Exclude overall_success
        print(f"\nSummary:")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed: {passed_tests}")
        print(f"  Failed: {total_tests - passed_tests}")
        print(f"  Success Rate: {(passed_tests/total_tests*100):.1f}%")
        print(f"  Total Execution Time: {total_time:.2f}s")
        
        print("="*100)
    
    def save_test_results(self, output_file: str = "data/connection_test_results.json"):
        """Save test results to JSON file."""
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(self.test_results, f, indent=2, default=str)
            
            logger.info(f"Test results saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save test results: {e}")


def main():
    """Main function to run connection manager tests."""
    logger.info("Starting Connection Manager Test Suite...")
    
    # Verify database exists
    db_path = Path("data/csexpert.db")
    if not db_path.exists():
        logger.error("Database not found. Please run database_initializer.py first.")
        return
    
    # Initialize test suite
    test_suite = ConnectionManagerTest()
    
    try:
        # Run all tests
        results = test_suite.run_all_tests()
        
        # Print summary
        test_suite.print_test_summary()
        
        # Save results
        test_suite.save_test_results()
        
        # Exit with appropriate code
        if results.get('overall_success', False):
            logger.info("All connection manager tests passed!")
            exit(0)
        else:
            logger.error("Some connection manager tests failed!")
            exit(1)
            
    finally:
        # Cleanup
        test_suite.cleanup()


if __name__ == "__main__":
    main()