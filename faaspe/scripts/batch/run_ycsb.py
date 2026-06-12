import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from runner import *

def main():
    servers = [node.conn_addr() for node in read_nodes()]
    update_build(servers, 'ycsb')
    for workload_type in ['A', 'B', 'C', 'D', 'F']:
        for strategy in strategy_list:
            remote_run('ycsb', 1000, strategy, BENCH_TYPE=workload_type)

if __name__ == "__main__":
    main()
