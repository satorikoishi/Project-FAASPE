import numpy as np
import logging
import os
import csv
import random
from arbiter import get_arbiter
from profiler import get_profiler

def print_latency_stats(results, latencies, operation_type=""):
    """Prints various latency statistics for a given list of latencies."""
    if not latencies:
        logging.info(f"No latency data available for {operation_type}.")
        return

    latencies = np.array(latencies) * 1e3
    median = np.median(latencies)
    p90 = np.percentile(latencies, 90)
    p99 = np.percentile(latencies, 99)
    max_latency = np.max(latencies)
    min_latency = np.min(latencies)
    mean_latency = np.mean(latencies)
    
    results['median'] = median
    results['p90'] = p90
    results['p99'] = p99
    results['max'] = max_latency
    results['min'] = min_latency
    results['mean'] = mean_latency

    logging.info(f"{operation_type} Latency Statistics:")
    logging.info(f"  Median: {median:.4f} ms")
    logging.info(f"  90th Percentile: {p90:.4f} ms")
    logging.info(f"  99th Percentile: {p99:.4f} ms")
    logging.info(f"  Max: {max_latency:.4f} ms")
    logging.info(f"  Min: {min_latency:.4f} ms")
    logging.info(f"  Mean: {mean_latency:.4f} ms")

def print_tput(results, tput, prefix=""):
    results[f"{prefix}tput"]=f"{tput:.2f}"
    logging.info(f"{prefix}Throughput: {tput:.2f} ops/sec")
    
def save_benchmark_to_csv(benchmark_results, output_filename):
    """Saves benchmark results to a CSV file."""
    directory = os.path.dirname(output_filename)
    if not os.path.exists(directory):
        os.makedirs(directory)
        logging.info(f"Directory '{directory}' created.")
    else:
        logging.info(f"Directory '{directory}' already exists.")
        
    file_exists = os.path.exists(output_filename)

    with open(output_filename, mode='a', newline='') as file:
        csv_writer = csv.DictWriter(file, fieldnames=benchmark_results.keys())

        if not file_exists:
            # Write header only if the file does not exist
            csv_writer.writeheader()

        # Write each benchmark result
        csv_writer.writerow(benchmark_results)
        
    logging.info(f"Benchmark results {benchmark_results} saved to {output_filename}")

def save_detailed_latency(latencies, output_filename):
    directory = os.path.dirname(output_filename)
    if not os.path.exists(directory):
        os.makedirs(directory)
        logging.info(f"Directory '{directory}' created.")
    else:
        logging.info(f"Directory '{directory}' already exists.")
    
    with open(output_filename, mode='a', newline='') as file:
        csv_writer = csv.writer(file)
        csv_writer.writerow(latencies)

# Strategy: local, remote, kayak, asfp, faaspe
# Placement: native, func, pushback(func + native)
def strategy_placement(s, function_name=None, params=None):
    if s == 'local':
        return 'native'
    elif s == 'remote':
        return 'func'
    elif s == 'kayak':
        if random.random() < 0.5:
            return 'native'
        else:
            return 'func'
    elif s == 'asfp':
        if random.random() < 0.2:
            return 'pushback'
        else:
            return 'func'
    elif s == 'faaspe':
        return get_profiler().choose(function_name, params, get_arbiter()).placement
    else:
        raise ValueError('Unknown Strategy')

def arbiter_overhead_us():
    return get_arbiter().last_overhead_us

def profiler_overhead_us():
    return get_profiler().last_overhead_us

def record_profile(strategy, function_name, placement, latency_us):
    if strategy == 'faaspe':
        get_profiler().record(function_name, placement, latency_us)

def profiler_snapshot(strategy, function_name):
    if strategy == 'faaspe':
        return get_profiler().snapshot(function_name)
    return {
        "profiler_fallback_count": 0,
        "profiler_fallback_invocations": 0,
        "profiler_recheck_count": 0,
        "profiler_override": "",
    }
        
