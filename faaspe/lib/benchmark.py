import bench_util

import time
import logging
import random
from typing import Callable

# General Benchmarking Class to measure latency and throughput
class Benchmark:
    def __init__(self, client, name, num_operations: int, strategy, access='hot'):
        self.num_operations = num_operations
        self.success = 0
        self.name = name
        self.client = client
        self.strategy = strategy
        self.results = {'name': name, 'num_op': num_operations, 'strategy': strategy, 'access': access}
        self.placement_counts = {'native': 0, 'func': 0, 'pushback': 0}
        self.arbiter_overheads = []
        self.profiler_overheads = []
        self.init_kvs()
        if access == 'cold':
            self.client.clear()

    # ping-pong loop, we should only get latency, not tput
    def measure(self):
        """Measure latency and throughput for the given workload."""
        # Start time to measure the overall benchmark duration
        start_time = time.time()

        # Containers for latencies and results
        latencies = []

        # Perform the operations (GET/PUT, or any custom workload)
        for i in range(self.num_operations):
            # Prepare input for i-th op
            op_input = self.prepare_input(i)
            placement = bench_util.strategy_placement(
                self.strategy, self.name, self.arbiter_params(op_input)
            )
            if placement in self.placement_counts:
                self.placement_counts[placement] += 1
            if self.strategy == 'faaspe':
                self.arbiter_overheads.append(bench_util.arbiter_overhead_us())
                self.profiler_overheads.append(bench_util.profiler_overhead_us())
            
            op_start_time = time.time()
            res = self.perform(op_input, placement)  # Perform operation and capture latency
            op_end_time = time.time()
            
            latency = op_end_time - op_start_time
            latencies.append(latency)
            bench_util.record_profile(self.strategy, self.name, placement, latency * 1e6)
            
            if res:
                self.success += 1

        # End time after all operations
        end_time = time.time()
        total_time = end_time - start_time
        
        self.results['total_time']=total_time
        self.results.update({f'{k}_count': v for k, v in self.placement_counts.items()})
        if self.arbiter_overheads:
            self.results['arbiter_mean_us'] = sum(self.arbiter_overheads) / len(self.arbiter_overheads)
            self.results['arbiter_max_us'] = max(self.arbiter_overheads)
        else:
            self.results['arbiter_mean_us'] = 0.0
            self.results['arbiter_max_us'] = 0.0
        if self.profiler_overheads:
            self.results['profiler_mean_us'] = sum(self.profiler_overheads) / len(self.profiler_overheads)
            self.results['profiler_max_us'] = max(self.profiler_overheads)
        else:
            self.results['profiler_mean_us'] = 0.0
            self.results['profiler_max_us'] = 0.0
        self.results.update(bench_util.profiler_snapshot(self.strategy, self.name))
        self.print_stats(total_time, latencies)
        if self.name and 'trace' in self.name:
            bench_util.save_detailed_latency(latencies, f"./results/temp_detailed.csv")

    # Helper function to print stats
    def print_stats(self, total_time, latencies):
        bench_util.print_latency_stats(self.results, latencies, self.name)
        bench_util.print_tput(self.results, self.success / total_time, "success ")
        bench_util.print_tput(self.results, (self.num_operations - self.success) / total_time, "abort ")
        bench_util.save_benchmark_to_csv(self.results, f"./results/temp.csv")
        
    def perform(self, op_input, placement):
        """Perform a single workload operation and return the latency for it."""
        return True

    def prepare_input(self, idx):
        """Prepare input for idx-th operation."""
        return None

    def arbiter_params(self, op_input):
        """Return low-cost invocation parameters used to solve registered RPN."""
        return {}
    
    def init_kvs(self):
        return None
