from fabric import Connection
from fabric.group import ThreadingGroup
import threading
import time
from param_parser import *
from pathlib import Path

def remote_abs(path, home):
    if path.startswith("~/"):
        return f"{home}/{path[2:]}"
    return path

def update_build(addr_list, f_name):
    cloudlab_cmake_fix = (
        "sed -i 's/Protobuf CONFIG REQUIRED/Protobuf REQUIRED/' CMakeLists.txt && "
        "sed -i 's#^set(_PROTOBUF_LIBPROTOBUF .*#set(_PROTOBUF_LIBPROTOBUF protobuf)#' CMakeLists.txt && "
        "sed -i 's#^set(_PROTOBUF_PROTOC .*#set(_PROTOBUF_PROTOC /usr/bin/protoc)#' CMakeLists.txt"
    )
    for idx, addr in enumerate(addr_list):
        with Connection(addr) as c:
            with c.cd(REMOTE_PROJECT_DIR):
                c.run('git pull')
            with c.cd(REMOTE_JKV_DIR):
                c.run(f'git pull && {cloudlab_cmake_fix} && make')
            if idx == 0:    # client node only
                with c.cd(REMOTE_FAASPE_DIR):
                    c.run(f'git pull && python3 ./platform/cli.py create {f_name}')

def clear(remote_ip, f_name):
    with Connection(remote_ip) as c:
        with c.cd(REMOTE_FAASPE_DIR):
            c.run(f'python3 ./platform/cli.py delete {f_name}')

def run_kvs(kvs_addr, home, stop_event, use_occ=False):
    with Connection(kvs_addr) as c:
        print("Running server on remote machine...")
        with c.cd(REMOTE_JKV_DIR):
            # Place config first
            # home = c.run("echo $HOME").stdout.strip()
            c.put(str(FAASPE_DIR / 'config.ini'), f'{remote_abs(REMOTE_JKV_DIR, home)}/config/config.ini')
            # Run
            if use_occ:
                result = c.run('./build/occ_server', asynchronous=True)
            else:
                result = c.run('./build/jkv_server', asynchronous=True)
            # Wait for the stop_event to be set (signaled by client)
            stop_event.wait()
            print(f"Stopping KVS server on {kvs_addr}...")
            if use_occ:
                c.run(f"pkill occ_server")
            else:
                c.run(f"pkill jkv_server")

def run_cache(cache_addr, home, stop_event, use_occ=False):
    with Connection(cache_addr) as c:
        print("Running cache on remote machine...")
        with c.cd(REMOTE_JKV_DIR):
            # Place config first
            # home = c.run("echo $HOME").stdout.strip()
            c.put(str(FAASPE_DIR / 'config.ini'), f'{remote_abs(REMOTE_JKV_DIR, home)}/config/config.ini')
            # Run
            if use_occ:
                result = c.run('./build/occ_cache', asynchronous=True)
            else:
                result = c.run('./build/cache_server', asynchronous=True)
            # Wait for the stop_event to be set (signaled by client)
            stop_event.wait()
            print(f"Stopping Cache server on {cache_addr}...")
            if use_occ:
                c.run(f"pkill occ_cache")
            else:
                c.run(f"pkill cache_server")

# def run_client_cpp(client_addr):
#     with Connection(client_addr) as c:
#         print("Running cpp client on remote machine...")
#         with c.cd('~/projects/jkv'):
#             result = c.run('./build/ping_client', timeout=15)
#         # Set the stop_event to notify the other threads to stop
#         print(f"Client finished. Signaling to stop servers...")
#         stop_event.set()

def run_client(client_addr, stop_event, f_name, num_operations, strategy, **kwargs):
    # Invoke through platform
    with Connection(client_addr) as c:
        print("Running client on remote machine...")
        # Generate json
        j_str = generate_json(f_name, num_operations, strategy, **kwargs)
        with c.cd(REMOTE_FAASPE_DIR):
            try:
                cmd = f'python3 ./platform/cli.py invoke {f_name} --params \'{j_str}\''
                print(cmd)
                c.run(cmd)
            except Exception as e:
                print(f"Error during command execution: {e}")
        # Set the stop_event to notify the other threads to stop
        print(f"Client finished. Signaling to stop servers...")
        stop_event.set()
        
def run(where, f_name, num_operations, strategy, use_occ=False, **kwargs):
    # Prepare config and bin
    if where == 'remote':
        servers = [node.conn_addr() for node in read_nodes()]
    else:
        servers = lab_servers
    # update_build(servers, f_name)
    generate_conf(where)
    stop_event = threading.Event()
    
    # Start bench threads
    threads = []
    threads.append(threading.Thread(target=run_kvs, args=(servers[1], home_path[where], stop_event, use_occ)))
    threads.append(threading.Thread(target=run_cache, args=(servers[0], home_path[where], stop_event, use_occ)))
    threads.append(threading.Thread(target=run_client, args=(servers[0], stop_event, f_name, num_operations, strategy), kwargs=kwargs))
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    # Fetch data to local (Optional)
    fetch_data(servers[0], f_name, f'{f_name}-{where}')
    if 'trace' in f_name:
        fetch_data(servers[0], f_name, f'{f_name}-{where}', "detailed", file_name='temp_detailed.csv')

def lab_run(f_name, num_operations=1000, strategy='local'):
    run('lab', f_name, num_operations, strategy)

def remote_run(f_name, num_operations=1000, strategy='local', use_occ=False, **kwargs):
    run('remote', f_name, num_operations, strategy, use_occ, **kwargs)

def fetch_data(remote_ip, f_name, local_dir=".", local_path_suffix="", container_file_dir="/usr/src/app/results", file_name='temp.csv'):
    local_path = FAASPE_DIR / "results" / local_dir / f"{f_name}{local_path_suffix}.csv"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with Connection(remote_ip) as c:
        home = c.run("echo $HOME", hide=True).stdout.strip()
        remote_tmp = f"{remote_abs(REMOTE_FAASPE_DIR, home)}/{file_name}"
        c.run(f'docker cp faaspe-{f_name}:{container_file_dir}/{file_name} {remote_tmp}')
        c.get(remote_tmp, str(local_path))

def test():
    pass
