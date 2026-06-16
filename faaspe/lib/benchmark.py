import bench_util

import os
import time
import logging
import random
from typing import Callable
from types import SimpleNamespace
from access_meta import (
    clear_invocation_access_meta,
    reset_invocation_access_meta,
    snapshot_invocation_access_meta,
)
from invocation_log import get_invocation_logger

# General Benchmarking Class to measure latency and throughput
class Benchmark:
    def __init__(self, client, name, num_operations: int, strategy, access='hot'):
        self.seed_random()
        self.num_operations = num_operations
        self.success = 0
        self.name = name
        self.client = client
        self.strategy = strategy
        self.results = {'name': name, 'num_op': num_operations, 'strategy': strategy, 'access': access}
        self.result_dir = os.getenv("FAASPE_RESULT_DIR", "./results")
        self.placement_counts = {'native': 0, 'func': 0, 'pushback': 0}
        self.arbiter_overheads = []
        self.profiler_choose_overheads = []
        self.profiler_update_overheads = []
        self.invocation_logger = get_invocation_logger()
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
            invocation_start_ns = time.perf_counter_ns()
            if bench_util.profile_sample_selected():
                reset_invocation_access_meta()
            else:
                clear_invocation_access_meta()
            # Prepare input for i-th op
            op_input = self.prepare_input(i)
            placement_params = self.arbiter_params(op_input)
            placement = bench_util.strategy_placement(self.strategy, self.name, placement_params)
            if placement in self.placement_counts:
                self.placement_counts[placement] += 1
            if self.strategy == 'faaspe':
                self.arbiter_overheads.append(bench_util.arbiter_overhead_us())
                self.profiler_choose_overheads.append(bench_util.profiler_overhead_us())
                plan = bench_util.profiler_last_plan()
            else:
                plan = self.default_plan(placement)
            
            op_start_time = time.time()
            res = self.perform(op_input, placement)  # Perform operation and capture latency
            op_end_time = time.time()
            
            latency = op_end_time - op_start_time
            latencies.append(latency)
            bench_util.record_profile(self.strategy, self.name, placement, latency * 1e6)
            if self.strategy == 'faaspe':
                self.profiler_update_overheads.append(bench_util.profiler_update_overhead_us())
            access_meta = snapshot_invocation_access_meta()
            self.log_invocation(
                i,
                placement_params,
                placement,
                plan,
                latency,
                access_meta,
                invocation_start_ns,
            )
            
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
        if self.profiler_update_overheads:
            self.results['profiler_mean_us'] = sum(self.profiler_update_overheads) / len(self.profiler_update_overheads)
            self.results['profiler_max_us'] = max(self.profiler_update_overheads)
        else:
            self.results['profiler_mean_us'] = 0.0
            self.results['profiler_max_us'] = 0.0
        self.results.update(bench_util.profiler_snapshot(self.strategy, self.name))
        self.print_stats(total_time, latencies)
        if self.name and 'trace' in self.name:
            bench_util.save_detailed_latency(latencies, os.path.join(self.result_dir, "temp_detailed.csv"))
        self.invocation_logger.flush_to_file()
        self.invocation_logger.close()

    # Helper function to print stats
    def print_stats(self, total_time, latencies):
        bench_util.print_latency_stats(self.results, latencies, self.name)
        bench_util.print_tput(self.results, self.success / total_time, "success ")
        bench_util.print_tput(self.results, (self.num_operations - self.success) / total_time, "abort ")
        bench_util.save_benchmark_to_csv(self.results, os.path.join(self.result_dir, "temp.csv"))
        
    def perform(self, op_input, placement):
        """Perform a single workload operation and return the latency for it."""
        return True

    def prepare_input(self, idx):
        """Prepare input for idx-th operation."""
        return None

    def arbiter_params(self, op_input):
        """Return low-cost invocation parameters used to solve registered RPN."""
        return {}

    def log_invocation(self, invocation_id, params, placement, plan, latency, access_meta, invocation_start_ns):
        logger_enabled = self.invocation_logger.is_enabled()
        async_profiler_enabled = bench_util.async_profiler_enabled()
        if not logger_enabled and not async_profiler_enabled:
            return

        selected_side = {
            "native": "compute",
            "func": "storage",
            "pushback": "compute",
        }.get(placement, placement)
        fallback_phase = plan.reason if getattr(plan, "fallback_active", False) else ""
        reason = "fallback" if getattr(plan, "fallback_active", False) else plan.arbiter_reason
        predicted_ns = int((getattr(plan, "expected_us", 0.0) or 0.0) * 1000.0)
        actual_ns = int(latency * 1e9)
        access_record = access_meta.as_dict()
        record = {
            "func_id": self.name,
            "side": selected_side,
            "predicted_ns": predicted_ns,
            "actual_ns": actual_ns,
            "estimated_ad": plan.access_depth,
            "trigger_used": bool(getattr(plan, "trigger_check_us", 0.0)),
            "fallback_used": bool(getattr(plan, "fallback_active", False)),
            "invocation_id": invocation_id,
            "invocation_start_ns": invocation_start_ns,
            "function_name": self.name,
            "function_id": self.name,
            "placement_params": params,
            "estimated_access_depth": plan.access_depth,
            "estimated_object_size": plan.object_size,
            "selected_side": selected_side,
            "raw_placement": placement,
            "reason": reason,
            "compute_side_estimated_latency_us": plan.compute_latency_us,
            "storage_side_estimated_latency_us": plan.storage_latency_us,
            "actual_execution_latency_us": latency * 1e6,
            "cache_hit": None,
            "storage_queue_load_indicator": params.get("storage_load_us"),
            "fallback_triggered": bool(getattr(plan, "fallback_active", False)),
            "fallback_phase": fallback_phase,
            "arbiter_decision_us": bench_util.arbiter_overhead_us() if self.strategy == "faaspe" else 0.0,
            "profiler_update_us": bench_util.profiler_update_overhead_us() if self.strategy == "faaspe" else 0.0,
            "trigger_check_us": plan.trigger_check_us,
            "ast_analysis_us": plan.ast_analysis_us,
        }
        record.update(access_record)
        if logger_enabled:
            self.invocation_logger.write(record)
        if async_profiler_enabled:
            bench_util.async_profiler_record_fast(record)

    def default_plan(self, placement):
        return SimpleNamespace(
            reason="normal",
            arbiter_reason="default",
            fallback_active=False,
            access_depth=None,
            object_size=None,
            compute_latency_us=None,
            storage_latency_us=None,
            trigger_check_us=0.0,
            ast_analysis_us=0.0,
        )

    def seed_random(self):
        seed = os.getenv("FAASPE_RANDOM_SEED")
        if seed is None:
            return
        seed = int(seed)
        random.seed(seed)
        try:
            import numpy as np
            np.random.seed(seed)
        except ImportError:
            pass
    
    def init_kvs(self):
        return None
