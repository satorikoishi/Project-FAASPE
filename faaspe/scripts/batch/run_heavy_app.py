import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from runner import *

func_name_list = ['image', 'video', 'ml-serving']

def main():
    servers = [node.conn_addr() for node in read_nodes()]
    for func_name in func_name_list:
        update_build(servers, func_name)
        for access in ['cold']:
            for strategy in strategy_list:
                remote_run(func_name, 100, strategy, ACCESS=access)
        clear(servers[0], func_name)

if __name__ == "__main__":
    main()
