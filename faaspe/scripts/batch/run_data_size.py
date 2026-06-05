import sys
sys.path.append('./scripts')

from runner import *

func_name = 'data-size'

def main():
    servers = [node.conn_addr() for node in read_nodes()]
    update_build(servers, func_name)
    for value_len in (1024, 1024 * 10, 1024 * 100, 1024 * 1024):
        for strategy in strategy_list:
            for hot_cold in ('hot', 'cold'):
                for op in ('get', 'update'):
                    remote_run(func_name, 1000, strategy, VALUE_LEN=value_len, ACCESS=f'{hot_cold}-{op}')

if __name__ == "__main__":
    main()
