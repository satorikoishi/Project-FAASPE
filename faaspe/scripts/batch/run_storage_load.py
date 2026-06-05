import sys
sys.path.append('./scripts')

from runner import *

func_name = 'storage-load-trace'

def main():
    servers = [node.conn_addr() for node in read_nodes()]
    update_build(servers, func_name)
    for strategy in strategy_list + ('faaspe', ):
        remote_run(func_name, 1000, strategy, ACCESS='hot')

if __name__ == "__main__":
    main()
