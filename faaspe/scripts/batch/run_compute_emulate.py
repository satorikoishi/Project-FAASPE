import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from runner import *

func_name = 'compute-emulate'

def main():
    servers = [node.conn_addr() for node in read_nodes()]
    update_build(servers, func_name)
    for dependent_access in (1, 2, 4, 8):
        for compute_duration in (100, 1000, 10000, 100000):
            for strategy in strategy_list:
                remote_run(func_name, 1000, strategy, COMPUTE_DURATION=compute_duration, DEPENDENT_ACCESS=dependent_access)

if __name__ == "__main__":
    main()
