#!/usr/bin/env python3
"""
Memory Cleanup Script for OpenAlgo Strategies
Cleans up old log files and monitors memory usage
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone('Asia/Kolkata')

def cleanup_old_logs(log_dir, max_age_days=7, max_size_mb=10):
    """Clean up old or large log files"""
    log_path = Path(log_dir)
    if not log_path.exists():
        print(f"Log directory not found: {log_dir}")
        return
    
    cleaned = 0
    total_freed = 0
    
    for log_file in log_path.glob("*.log"):
        try:
            # Check file age
            file_age = datetime.now(IST) - datetime.fromtimestamp(log_file.stat().st_mtime, IST)
            file_size_mb = log_file.stat().st_size / (1024 * 1024)
            
            should_delete = False
            
            # Delete if older than max_age_days
            if file_age.days > max_age_days:
                should_delete = True
                reason = f"older than {max_age_days} days"
            
            # Delete if larger than max_size_mb
            elif file_size_mb > max_size_mb:
                should_delete = True
                reason = f"larger than {max_size_mb}MB ({file_size_mb:.1f}MB)"
            
            if should_delete:
                size_mb = file_size_mb
                log_file.unlink()
                cleaned += 1
                total_freed += size_mb
                print(f"Deleted: {log_file.name} ({reason})")
        
        except Exception as e:
            print(f"Error processing {log_file.name}: {e}")
    
    if cleaned > 0:
        print(f"\n✅ Cleaned {cleaned} log files, freed {total_freed:.1f} MB")
    else:
        print("✅ No log files to clean")

def get_memory_stats():
    """Get memory statistics for running strategies"""
    import subprocess
    
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True
        )
        
        total_mem = 0
        strategy_count = 0
        
        for line in result.stdout.split('\n'):
            if 'strategies/scripts' in line and 'grep' not in line:
                parts = line.split()
                if len(parts) > 5:
                    mem_mb = float(parts[5]) / 1024
                    total_mem += mem_mb
                    strategy_count += 1
        
        return {
            'strategy_count': strategy_count,
            'total_memory_mb': total_mem,
            'avg_memory_mb': total_mem / strategy_count if strategy_count > 0 else 0
        }
    except Exception as e:
        print(f"Error getting memory stats: {e}")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("OpenAlgo Memory Cleanup Script")
    print("=" * 60)
    print()
    
    # Get script directory
    script_dir = Path(__file__).parent
    openalgo_root = script_dir.parent
    log_dir = openalgo_root / "log" / "strategies"
    
    print(f"Log directory: {log_dir}")
    print()
    
    # Clean up old logs
    print("Cleaning up old log files...")
    cleanup_old_logs(log_dir, max_age_days=7, max_size_mb=10)
    print()
    
    # Get memory stats
    print("Memory Statistics:")
    stats = get_memory_stats()
    if stats:
        print(f"  Running strategies: {stats['strategy_count']}")
        print(f"  Total memory: {stats['total_memory_mb']:.1f} MB")
        print(f"  Average per strategy: {stats['avg_memory_mb']:.1f} MB")
    print()
    
    print("✅ Memory cleanup completed")
