import libconf
import io
import os
import json
from pathlib import Path

lab_servers = [item.strip() for item in os.getenv('FAASPE_LAB_SERVERS', 'jw@10.0.16.45,jw@10.0.16.12').split(',') if item.strip()]
remote_servers = [item.strip() for item in os.getenv('FAASPE_REMOTE_SERVERS', 'jinwei@10.10.1.1,jinwei@10.10.1.2').split(',') if item.strip()]

home_path = { "lab": "/home/jw", "remote": "/users/jinwei"}
strategy_list = ('local', 'remote', 'kayak', 'asfp')

FAASPE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = FAASPE_DIR.parent
JKV_DIR = REPO_ROOT / "jkv"
WORKING_DIR = str(REPO_ROOT)
REMOTE_PROJECT_DIR = os.getenv('FAASPE_REMOTE_PROJECT_DIR', '~/projects/Project-FAASPE')
REMOTE_FAASPE_DIR = os.getenv('FAASPE_REMOTE_FAASPE_DIR', f'{REMOTE_PROJECT_DIR}/faaspe')
REMOTE_JKV_DIR = os.getenv('FAASPE_REMOTE_JKV_DIR', f'{REMOTE_PROJECT_DIR}/jkv')

def read_token():
    env_token = os.getenv('GITHUB_TOKEN')
    if env_token:
        return env_token.strip()
    if not os.path.exists('token'):
        return ''
    with open('token', 'r') as f:
        return f.readline().strip()

class Node(object):
    def __init__(self, id, username, port, host):
        self.id = id
        self.username = username
        self.port = port
        self.host = host
    
    def home_addr(self):
        return f'{self.username}@{self.host}:/users/{self.username}'
    
    def conn_addr(self):
        return f'{self.username}@{self.host}'

def read_nodes(config_file = None):
    env_hosts = os.getenv('FAASPE_REMOTE_HOSTS')
    if env_hosts:
        nodes = []
        for node_id, item in enumerate(env_hosts.split(',')):
            item = item.strip()
            if not item:
                continue
            if '@' in item:
                username, host = item.split('@', 1)
            else:
                username, host = os.getenv('FAASPE_REMOTE_USER', 'jinwei'), item
            nodes.append(Node(node_id, username, 22, host))
        return nodes
    if config_file is None:
        config_file = os.getenv('FAASPE_NODES_FILE', str(FAASPE_DIR / "nodes.txt"))
    nodes = []
    node_id = 0
    with open(config_file, 'r') as f:
        for line in f:
            res = line.split(' ')[1].strip().split('@')
            nodes.append(Node(node_id, res[0], 22, res[1]))
            node_id = node_id + 1
    # for node in nodes:
    #     print(f'Node id {node.id}, username {node.username}, port {node.port}, host {node.host}')
    return nodes

def read_conf(file_name=None):
    if file_name is None:
        file_name = JKV_DIR / "config" / "config.ini"
    with io.open(file_name) as f:
        config = libconf.load(f)
    return config

def generate_conf(where='remote', template=None, target=None):
    if template is None:
        template = JKV_DIR / "config" / "config.example"
    if target is None:
        target = FAASPE_DIR / "config.ini"
    config = read_conf(template)
    if where == 'remote':
        client_ip = remote_servers[0].strip().split('@')[1]
        kvs_ip = remote_servers[1].strip().split('@')[1]
    else:
        client_ip = lab_servers[0].strip().split('@')[1]
        kvs_ip = lab_servers[1].strip().split('@')[1]
    config['kvs']['ip'] = kvs_ip
    config['cache_client']['ip'] = client_ip     # Other two are useless
    # print(libconf.dumps(config))
    with open(target, 'w') as f:
        libconf.dump(config, f)
    print(f"Configuration successfully written to {target}")

def generate_json(f_name, num_operations, strategy, **kwargs):
    params = {}
    # basic params
    params['BENCH_NAME'] = f_name
    params['NUM_OPERATION'] = num_operations
    params['STRATEGY'] = strategy
    params.update(kwargs)
    
    # zmq addr
    config = read_conf(FAASPE_DIR / "config.ini")
    base_port = config['base_port']
    cache_ip = config['cache_client']['ip']
    recv_port = base_port + config['cache_client']['recv_port']
    send_port = base_port + config['cache_client']['send_port']
    params['PUSH_ADDR'] = f'tcp://{cache_ip}:{recv_port}'
    params['PULL_ADDR'] = f'tcp://{cache_ip}:{send_port}'
    return json.dumps(params)
    
if __name__ == "__main__":
    # config = read_conf()
    # print(config)
    generate_conf()
