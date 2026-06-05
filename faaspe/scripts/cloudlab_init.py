from fabric import Connection
from fabric.group import ThreadingGroup
from param_parser import *

def get_host_connections():
    conns = []
    for node in read_nodes():
        host_c = Connection(host=node.host, user = node.username, port = node.port)
        conns.append(host_c)
    return conns

def batch_init():
    conns = get_host_connections()
    g_host = ThreadingGroup.from_connections(conns)
    
    print("Batch init start")
    token = read_token()
    init_cmd = [f'git clone https://{token}@github.com/satorikoishi/faaspe.git ~/projects/faaspe',
                f'git clone https://{token}@github.com/satorikoishi/jkv.git ~/projects/jkv',
                f'git clone --recurse-submodules -b v1.68.0 --depth 1 --shallow-submodules https://{token}@github.com/grpc/grpc ~/grpc',
                'cd ~/projects/faaspe && ./scripts/init.sh']
    for cmd in init_cmd:
        g_host.run(cmd)
    print("Batch init finished")
    
    print("Master init start")
    master_conn = conns[0]
    master_conn.run(f'cd ~/projects/faaspe && ./scripts/docker_init.sh')
    print("Master init finished")

def batch_clean():
    g_host = ThreadingGroup.from_connections(get_host_connections())
    g_host.run('rm -rf ~/projects')
    print("Batch clean finished")
    
if __name__ == "__main__":
    pass