from fabric import Connection
from fabric.group import ThreadingGroup
from param_parser import *

PROJECT_REPO = 'github.com/satorikoishi/Project-FAASPE.git'
PROJECT_DIR = '~/projects/Project-FAASPE'

def get_host_connections():
    conns = []
    for node in read_nodes():
        host_c = Connection(host=node.host, user = node.username, port = node.port)
        conns.append(host_c)
    return conns

def get_repo_url():
    token = read_token()
    if token:
        return f'https://{token}@{PROJECT_REPO}'
    return f'https://{PROJECT_REPO}'

def batch_init():
    conns = get_host_connections()
    g_host = ThreadingGroup.from_connections(conns)
    
    print("Batch init start")
    repo_url = get_repo_url()
    init_cmd = ['mkdir -p ~/projects',
                f'if [ -d {PROJECT_DIR}/.git ]; then cd {PROJECT_DIR} && git fetch origin master && git reset --hard origin/master; else git clone {repo_url} {PROJECT_DIR}; fi',
                f'ln -sfn {PROJECT_DIR}/faaspe ~/projects/faaspe',
                f'ln -sfn {PROJECT_DIR}/jkv ~/projects/jkv']
    for cmd in init_cmd:
        g_host.run(cmd)
    g_host.run('cd ~/projects/faaspe && bash ./scripts/init.sh')
    print("Batch init finished")
    
    print("Master init start")
    master_conn = conns[0]
    master_conn.run(f'cd ~/projects/faaspe && bash ./scripts/docker_init.sh')
    print("Master init finished")

def batch_clean():
    g_host = ThreadingGroup.from_connections(get_host_connections())
    g_host.run('rm -rf ~/projects')
    print("Batch clean finished")
    
if __name__ == "__main__":
    pass
