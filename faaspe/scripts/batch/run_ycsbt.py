import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from runner import *

func_name = 'ycsb-t'

def main():
    servers = [node.conn_addr() for node in read_nodes()]
    update_build(servers, func_name)
    for access in ('hot', 'cold'):
        for strategy in strategy_list:
            remote_run(func_name, 1000, strategy, True, ACCESS=access)
    clear(servers[0], func_name)

if __name__ == "__main__":
    main()
