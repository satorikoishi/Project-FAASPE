import sys
sys.path.append('./scripts')

from runner import *

func_name = 'list-traversal'

def main():
    servers = [node.conn_addr() for node in read_nodes()]
    update_build(servers, func_name)
    for access in ('hot', 'cold'):
        for depth in (1, 2, 4, 8):
            for strategy in strategy_list:
                remote_run(func_name, 1000, strategy, ACCESS=access, DEPTH=depth)

if __name__ == "__main__":
    main()
