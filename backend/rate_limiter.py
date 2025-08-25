"""
Rate limiting implementation for the RAG system.
Protects against API abuse and ensures fair usage.
"""
import time
import logging
from typing import Dict, Optional
from collections import defaultdict, deque
from threading import Lock
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RateLimitInfo:
    """Information about rate limit status."""
    allowed: bool
    remaining_requests: int
    reset_time: float
    retry_after: Optional[float] = None


class RateLimiter:
    """
    Thread-safe rate limiter using sliding window algorithm.
    Supports multiple clients and different rate limits.
    """
    
    def __init__(self, requests_per_minute: int = 10, window_seconds: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests allowed per minute
            window_seconds: Time window for rate limiting (seconds)
        """
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.max_requests = requests_per_minute
        
        # Track requests per client (IP address or user ID)
        self.client_requests: Dict[str, deque] = defaultdict(lambda: deque())
        self.lock = Lock()
        
        logger.info(f"🚦 Rate limiter initialized: {requests_per_minute} requests per {window_seconds}s")
    
    def is_allowed(self, client_id: str) -> RateLimitInfo:
        """
        Check if a request from client is allowed.
        
        Args:
            client_id: Unique identifier for the client (IP, user ID, etc.)
            
        Returns:
            RateLimitInfo with rate limit status
        """
        with self.lock:
            current_time = time.time()
            client_queue = self.client_requests[client_id]
            
            # Remove old requests outside the window
            cutoff_time = current_time - self.window_seconds
            while client_queue and client_queue[0] <= cutoff_time:
                client_queue.popleft()
            
            # Check if under limit
            remaining_requests = max(0, self.max_requests - len(client_queue))
            allowed = len(client_queue) < self.max_requests
            
            if allowed:
                # Add current request timestamp
                client_queue.append(current_time)
                remaining_requests -= 1
            
            # Calculate reset time (when oldest request will expire)
            reset_time = current_time + self.window_seconds
            if client_queue:
                reset_time = client_queue[0] + self.window_seconds
            
            # Calculate retry after time if rate limited
            retry_after = None
            if not allowed and client_queue:
                retry_after = client_queue[0] + self.window_seconds - current_time
                retry_after = max(1, retry_after)  # At least 1 second
            
            return RateLimitInfo(
                allowed=allowed,
                remaining_requests=remaining_requests,
                reset_time=reset_time,
                retry_after=retry_after
            )
    
    def get_client_stats(self, client_id: str) -> Dict:
        """Get statistics for a specific client."""
        with self.lock:
            current_time = time.time()
            client_queue = self.client_requests[client_id]
            
            # Clean old requests
            cutoff_time = current_time - self.window_seconds
            while client_queue and client_queue[0] <= cutoff_time:
                client_queue.popleft()
            
            return {
                "client_id": client_id,
                "current_requests": len(client_queue),
                "max_requests": self.max_requests,
                "remaining_requests": max(0, self.max_requests - len(client_queue)),
                "window_seconds": self.window_seconds,
                "oldest_request_age": current_time - client_queue[0] if client_queue else 0
            }
    
    def get_global_stats(self) -> Dict:
        """Get global rate limiter statistics."""
        with self.lock:
            current_time = time.time()
            total_active_clients = 0
            total_active_requests = 0
            
            # Clean all client queues and count active requests
            for client_id, client_queue in list(self.client_requests.items()):
                cutoff_time = current_time - self.window_seconds
                while client_queue and client_queue[0] <= cutoff_time:
                    client_queue.popleft()
                
                if client_queue:
                    total_active_clients += 1
                    total_active_requests += len(client_queue)
                else:
                    # Clean up empty queues
                    del self.client_requests[client_id]
            
            return {
                "total_active_clients": total_active_clients,
                "total_active_requests": total_active_requests,
                "max_requests_per_client": self.max_requests,
                "window_seconds": self.window_seconds,
                "timestamp": current_time
            }
    
    def reset_client(self, client_id: str) -> bool:
        """
        Reset rate limit for a specific client.
        Useful for admin operations or testing.
        
        Returns:
            True if client existed and was reset, False otherwise
        """
        with self.lock:
            if client_id in self.client_requests:
                del self.client_requests[client_id]
                logger.info(f"🔄 Rate limit reset for client: {client_id}")
                return True
            return False
    
    def cleanup_expired(self) -> int:
        """
        Cleanup expired client entries.
        
        Returns:
            Number of clients cleaned up
        """
        with self.lock:
            current_time = time.time()
            clients_to_remove = []
            
            for client_id, client_queue in self.client_requests.items():
                cutoff_time = current_time - self.window_seconds
                while client_queue and client_queue[0] <= cutoff_time:
                    client_queue.popleft()
                
                if not client_queue:
                    clients_to_remove.append(client_id)
            
            for client_id in clients_to_remove:
                del self.client_requests[client_id]
            
            logger.debug(f"🧹 Cleaned up {len(clients_to_remove)} expired clients")
            return len(clients_to_remove)


class AdaptiveRateLimiter(RateLimiter):
    """
    Advanced rate limiter that adapts based on system load.
    Reduces limits during high load periods.
    """
    
    def __init__(self, base_requests_per_minute: int = 10, 
                 window_seconds: int = 60, 
                 load_threshold: float = 0.8):
        """
        Initialize adaptive rate limiter.
        
        Args:
            base_requests_per_minute: Base rate limit
            window_seconds: Time window
            load_threshold: System load threshold (0.0-1.0) to reduce limits
        """
        super().__init__(base_requests_per_minute, window_seconds)
        self.base_requests_per_minute = base_requests_per_minute
        self.load_threshold = load_threshold
        self.current_load = 0.0
        
    def update_system_load(self, load: float):
        """Update current system load (0.0-1.0)."""
        self.current_load = max(0.0, min(1.0, load))
        
        # Adapt rate limit based on load
        if self.current_load > self.load_threshold:
            # Reduce rate limit during high load
            reduction_factor = 1.0 - ((self.current_load - self.load_threshold) / (1.0 - self.load_threshold))
            self.max_requests = max(1, int(self.base_requests_per_minute * reduction_factor))
        else:
            self.max_requests = self.base_requests_per_minute
        
        logger.debug(f"📊 System load: {self.current_load:.2f}, Rate limit: {self.max_requests}/min")


# Global rate limiter instance
_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(requests_per_minute: int = 10, window_seconds: int = 60) -> RateLimiter:
    """Get or create global rate limiter instance."""
    global _global_rate_limiter
    
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter(requests_per_minute, window_seconds)
    
    return _global_rate_limiter


def rate_limit_decorator(requests_per_minute: int = 10, window_seconds: int = 60):
    """
    Decorator for rate limiting function calls.
    
    Usage:
        @rate_limit_decorator(requests_per_minute=5)
        def my_function(client_id: str, ...):
            # Function implementation
    """
    def decorator(func):
        limiter = RateLimiter(requests_per_minute, window_seconds)
        
        def wrapper(*args, **kwargs):
            # Try to extract client_id from arguments
            client_id = kwargs.get('client_id', 'default')
            if not client_id and args:
                client_id = str(args[0]) if args else 'default'
            
            rate_info = limiter.is_allowed(client_id)
            
            if not rate_info.allowed:
                raise ValueError(f"Rate limit exceeded. Retry after {rate_info.retry_after:.1f} seconds")
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator 