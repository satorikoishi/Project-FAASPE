import sys
sys.path.append('./scripts')

from runner import *

func_name_list = ['auth', 'calc-avg', 'k-hop', 'file-replicator', 'user-follow']

def main():
    servers = [node.conn_addr() for node in read_nodes()]
    for func_name in func_name_list:
        update_build(servers, func_name)
        for access in ('hot', 'cold'):
                for strategy in strategy_list:
                    remote_run(func_name, 1000, strategy, ACCESS=access)
        clear(servers[0], func_name)

if __name__ == "__main__":
    main()
