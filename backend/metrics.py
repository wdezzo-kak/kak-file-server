"""
Prometheus metrics for kak file server.

Provides:
- Request count and duration
- Upload/download bytes
- Active connections
- Error rates
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import threading


@dataclass
class Counter:
    """Simple counter metric."""
    value: int = 0
    
    def inc(self, n: int = 1):
        self.value += n
    
    def get(self) -> int:
        return self.value


@dataclass
class Gauge:
    """Simple gauge metric."""
    value: float = 0.0
    
    def set(self, value: float):
        self.value = value
    
    def inc(self, n: float = 1):
        self.value += n
    
    def dec(self, n: float = 1):
        self.value -= n
    
    def get(self) -> float:
        return self.value


@dataclass
class Histogram:
    """Simple histogram metric with buckets."""
    buckets: Dict[float, int] = field(default_factory=dict)
    sum: float = 0.0
    count: int = 0
    
    def __post_init__(self):
        # Standard Prometheus buckets
        self.buckets = {
            0.005: 0, 0.01: 0, 0.025: 0, 0.05: 0, 0.1: 0,
            0.25: 0, 0.5: 0, 1.0: 0, 2.5: 0, 5.0: 0, 10.0: 0,
            float('inf'): 0
        }
    
    def observe(self, value: float):
        """Record an observation."""
        self.count += 1
        self.sum += value
        for bucket in self.buckets:
            if value <= bucket:
                self.buckets[bucket] += 1


class Metrics:
    """Prometheus-style metrics collector."""
    
    def __init__(self):
        # Counters
        self.requests_total = Counter()
        self.requests_by_method: Dict[str, Counter] = defaultdict(Counter)
        self.requests_by_status: Dict[int, Counter] = defaultdict(Counter)
        self.errors_total = Counter()
        
        # Upload/Download metrics
        self.bytes_uploaded = Counter()
        self.bytes_downloaded = Counter()
        self.uploads_total = Counter()
        self.downloads_total = Counter()
        
        # Active connections
        self.active_connections = Gauge()
        
        # Request duration
        self.request_duration = Histogram()
        
        # Per-path metrics
        self.path_requests: Dict[str, Counter] = defaultdict(Counter)
        
        # Start time
        self.start_time = time.time()
        
        # Thread lock for thread safety
        self._lock = threading.Lock()
    
    def record_request(self, method: str, path: str, status: int, duration: float):
        """Record a request."""
        with self._lock:
            self.requests_total.inc()
            self.requests_by_method[method].inc()
            self.requests_by_status[status].inc()
            self.request_duration.observe(duration)
            self.path_requests[path].inc()
            
            if status >= 400:
                self.errors_total.inc()
    
    def record_upload(self, bytes_count: int):
        """Record an upload."""
        with self._lock:
            self.bytes_uploaded.inc(bytes_count)
            self.uploads_total.inc()
    
    def record_download(self, bytes_count: int):
        """Record a download."""
        with self._lock:
            self.bytes_downloaded.inc(bytes_count)
            self.downloads_total.inc()
    
    def inc_connections(self):
        """Increment active connections."""
        with self._lock:
            self.active_connections.inc()
    
    def dec_connections(self):
        """Decrement active connections."""
        with self._lock:
            self.active_connections.dec()
    
    def get_prometheus_metrics(self) -> str:
        """Generate Prometheus exposition format."""
        lines = []
        uptime = time.time() - self.start_time
        
        # Helper to format metric
        def format_counter(name: str, counter: Counter, labels: str = ""):
            if labels:
                labels = "{" + labels + "}"
            lines.append(f"{name}{labels} {counter.get()}")
        
        def format_gauge(name: str, gauge: Gauge, labels: str = ""):
            if labels:
                labels = "{" + labels + "}"
            lines.append(f"{name}{labels} {gauge.get()}")
        
        def format_histogram(name: str, hist: Histogram, labels: str = ""):
            if labels:
                labels = "{" + labels + "}"
            
            # Bucket
            for bucket, count in sorted(hist.buckets.items()):
                if bucket == float('inf'):
                    bucket_label = "+Inf"
                else:
                    bucket_label = str(bucket)
                lines.append(f"{name}_bucket{{{labels},le=\"{bucket_label}\"}} {count}")
            
            # Sum and count
            lines.append(f"{name}_sum{{{labels}}} {hist.sum}")
            lines.append(f"{name}_count{{{labels}}} {hist.count}")
        
        # Uptime
        lines.append(f"kak_uptime_seconds {uptime}")
        
        # Request counters
        format_counter("kak_requests_total", self.requests_total)
        for method, counter in sorted(self.requests_by_method.items()):
            format_counter("kak_requests_total", counter, f'method="{method}"')
        for status, counter in sorted(self.requests_by_status.items()):
            format_counter("kak_requests_total", counter, f'status="{status}"')
        
        # Error counter
        format_counter("kak_errors_total", self.errors_total)
        
        # Upload/Download
        format_counter("kak_bytes_uploaded_total", self.bytes_uploaded)
        format_counter("kak_bytes_downloaded_total", self.bytes_downloaded)
        format_counter("kak_uploads_total", self.uploads_total)
        format_counter("kak_downloads_total", self.downloads_total)
        
        # Active connections
        format_gauge("kak_active_connections", self.active_connections)
        
        # Request duration
        format_histogram("kak_request_duration_seconds", self.request_duration)
        
        return "\n".join(lines) + "\n"


# Global metrics instance
_metrics: Optional[Metrics] = None


def get_metrics() -> Metrics:
    """Get the global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics


def init_metrics():
    """Initialize metrics (call on startup)."""
    global _metrics
    _metrics = Metrics()
