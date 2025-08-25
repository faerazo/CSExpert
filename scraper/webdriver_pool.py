#!/usr/bin/env python3
"""
WebDriver Pool Implementation

Provides shared WebDriver instances to avoid expensive browser startup costs.
Implements connection pooling pattern with context manager support.
"""

import queue
import threading
import time
import warnings
from contextlib import contextmanager
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import logging

logger = logging.getLogger(__name__)

class WebDriverPool:
    """Pool of WebDriver instances for efficient browser session reuse."""
    
    def __init__(self, pool_size=3, max_retries=3):
        """
        Initialize WebDriver pool.
        
        Args:
            pool_size: Number of WebDriver instances to maintain
            max_retries: Maximum retries for driver creation
        """
        self.pool_size = pool_size
        self.max_retries = max_retries
        self.drivers = queue.Queue(maxsize=pool_size)
        self.lock = threading.Lock()
        self.created_drivers = 0
        self._initialize_pool()
    
    def _create_driver(self):
        """Create a new WebDriver instance with optimized settings."""
        try:
            # Suppress deprecation warnings
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            
            # Configure Chrome options for headless operation
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-logging")
            options.add_argument("--disable-web-security")
            options.add_argument("--allow-running-insecure-content")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Initialize Chrome WebDriver with managed service
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            # Set timeouts
            driver.implicitly_wait(10)
            driver.set_page_load_timeout(30)
            
            logger.info("Created new WebDriver instance")
            return driver
            
        except Exception as e:
            logger.error(f"Failed to create WebDriver: {e}")
            raise
    
    def _initialize_pool(self):
        """Initialize the pool with WebDriver instances."""
        logger.info(f"Initializing WebDriver pool with {self.pool_size} instances")
        
        for i in range(self.pool_size):
            try:
                driver = self._create_driver()
                self.drivers.put(driver)
                self.created_drivers += 1
                logger.debug(f"Added driver {i+1}/{self.pool_size} to pool")
            except Exception as e:
                logger.error(f"Failed to create driver {i+1}: {e}")
                # Continue with fewer drivers if some fail
                break
        
        if self.created_drivers == 0:
            raise RuntimeError("Failed to create any WebDriver instances")
        
        logger.info(f"WebDriver pool initialized with {self.created_drivers} instances")
    
    @contextmanager
    def get_driver(self, timeout=30):
        """
        Get a WebDriver instance from the pool.
        
        Args:
            timeout: Maximum time to wait for available driver
            
        Yields:
            WebDriver instance
        """
        driver = None
        start_time = time.time()
        
        try:
            # Try to get driver from pool
            driver = self.drivers.get(timeout=timeout)
            
            # Verify driver is still functional
            if not self._is_driver_healthy(driver):
                logger.warning("Driver unhealthy, creating replacement")
                driver.quit()
                driver = self._create_driver()
            
            yield driver
            
        except queue.Empty:
            # No drivers available in time
            elapsed = time.time() - start_time
            raise TimeoutError(f"No WebDriver available after {elapsed:.1f} seconds")
            
        except Exception as e:
            logger.error(f"Error using WebDriver: {e}")
            # If driver is broken, create a new one
            if driver:
                try:
                    driver.quit()
                except:
                    pass  # Driver might already be dead
                driver = self._create_driver()
            raise
            
        finally:
            # Return driver to pool if it's still healthy
            if driver:
                if self._is_driver_healthy(driver):
                    try:
                        # Clear any leftover state
                        driver.delete_all_cookies()
                        self.drivers.put(driver)
                    except:
                        # If cleanup fails, create new driver
                        try:
                            driver.quit()
                        except:
                            pass
                        replacement = self._create_driver()
                        self.drivers.put(replacement)
                else:
                    # Driver is unhealthy, create replacement
                    try:
                        driver.quit()
                    except:
                        pass
                    replacement = self._create_driver()
                    self.drivers.put(replacement)
    
    def _is_driver_healthy(self, driver):
        """Check if WebDriver instance is still functional."""
        try:
            # Try to get current URL - this will fail if driver is dead
            _ = driver.current_url
            return True
        except Exception:
            return False
    
    def get_pool_status(self):
        """Get current status of the WebDriver pool."""
        return {
            'pool_size': self.pool_size,
            'available_drivers': self.drivers.qsize(),
            'created_drivers': self.created_drivers,
            'healthy': self.drivers.qsize() > 0
        }
    
    def close_all(self):
        """Close all WebDriver instances and cleanup."""
        logger.info("Closing all WebDriver instances")
        
        closed_count = 0
        while not self.drivers.empty():
            try:
                driver = self.drivers.get_nowait()
                driver.quit()
                closed_count += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error closing driver: {e}")
                closed_count += 1  # Count as closed even if error
        
        logger.info(f"Closed {closed_count} WebDriver instances")
        self.created_drivers = 0
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.close_all()


class WebDriverPoolSingleton:
    """Singleton wrapper for global WebDriver pool access."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, pool_size=3):
        if not hasattr(self, 'initialized'):
            self.pool = WebDriverPool(pool_size=pool_size)
            self.initialized = True
    
    def get_driver(self, timeout=30):
        """Get WebDriver from singleton pool."""
        return self.pool.get_driver(timeout=timeout)
    
    def get_status(self):
        """Get pool status."""
        return self.pool.get_pool_status()
    
    def close_all(self):
        """Close all drivers."""
        self.pool.close_all()


# Global pool instance for easy access
_global_pool = None

def get_global_pool(pool_size=3):
    """Get or create global WebDriver pool."""
    global _global_pool
    if _global_pool is None:
        _global_pool = WebDriverPool(pool_size=pool_size)
    return _global_pool

def get_driver(timeout=30):
    """Get WebDriver from global pool."""
    pool = get_global_pool()
    return pool.get_driver(timeout=timeout)

def close_global_pool():
    """Close global WebDriver pool."""
    global _global_pool
    if _global_pool:
        _global_pool.close_all()
        _global_pool = None


if __name__ == "__main__":
    # Test the WebDriver pool
    logging.basicConfig(level=logging.INFO)
    
    print("Testing WebDriver Pool...")
    
    # Test pool creation
    pool = WebDriverPool(pool_size=2)
    print(f"Pool status: {pool.get_pool_status()}")
    
    # Test driver usage
    with pool.get_driver() as driver:
        driver.get("https://example.com")
        title = driver.title
        print(f"Page title: {title}")
    
    # Test concurrent usage
    import concurrent.futures
    
    def test_concurrent_usage(pool, url):
        with pool.get_driver() as driver:
            driver.get(url)
            return driver.title
    
    urls = ["https://example.com", "https://httpbin.org", "https://google.com"]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(test_concurrent_usage, pool, url) for url in urls]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    
    print(f"Concurrent results: {results}")
    
    # Test cleanup
    pool.close_all()
    print("WebDriver pool test completed!")