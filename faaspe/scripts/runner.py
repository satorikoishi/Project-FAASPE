from fabric import Connection
from fabric.group import ThreadingGroup
import threading
import time
import shlex
from param_parser import *

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
                c.run('git fetch origin master && git reset --hard origin/master')
            with c.cd(REMOTE_JKV_DIR):
                c.run(f'{cloudlab_cmake_fix} && make')
            if idx == 0:    # client node only
                with c.cd(REMOTE_FAASPE_DIR):
                    c.run(f'python3 ./platform/cli.py create {f_name}')

def clear(remote_ip, f_name):
    with Connection(remote_ip) as c:
        with c.cd(REMOTE_FAASPE_DIR):
            c.run(f'python3 ./platform/cli.py delete {f_name}')

def env_prefix(env):
    if not env:
        return ""
    return " ".join(f"{key}={shlex.quote(str(value))}" for key, value in env.items()) + " "

def run_kvs(kvs_addr, home, stop_event, use_occ=False, kvs_env=None):
    with Connection(kvs_addr) as c:
        print("Running server on remote machine...")
        with c.cd(REMOTE_JKV_DIR):
            # Place config first
            # home = c.run("echo $HOME").stdout.strip()
            c.put(str(FAASPE_DIR / 'config.ini'), f'{remote_abs(REMOTE_JKV_DIR, home)}/config/config.ini')
            # Run
            prefix = env_prefix(kvs_env)
            if use_occ:
                result = c.run(f'{prefix}./build/occ_server', asynchronous=True)
            else:
                result = c.run(f'{prefix}./build/jkv_server', asynchronous=True)
            # Wait for the stop_event to be set (signaled by client)
            stop_event.wait()
            print(f"Stopping KVS server on {kvs_addr}...")
            if use_occ:
                c.run(f"pkill occ_server")
            else:
                c.run(f"pkill jkv_server")

def run_cache(cache_addr, home, stop_event, use_occ=False, cache_env=None):
    with Connection(cache_addr) as c:
        print("Running cache on remote machine...")
        with c.cd(REMOTE_JKV_DIR):
            # Place config first
            # home = c.run("echo $HOME").stdout.strip()
            c.put(str(FAASPE_DIR / 'config.ini'), f'{remote_abs(REMOTE_JKV_DIR, home)}/config/config.ini')
            # Run
            prefix = env_prefix(cache_env)
            if use_occ:
                result = c.run(f'{prefix}./build/occ_cache', asynchronous=True)
            else:
                result = c.run(f'{prefix}./build/cache_server', asynchronous=True)
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
    local_dir = kwargs.pop("_local_dir", f"{f_name}-{where}")
    local_suffix = kwargs.pop("_local_suffix", "")
    local_file_name = kwargs.pop("_local_file_name", None)
    fetch_invocations = kwargs.pop("_fetch_invocations", False)
    container_result_dir = kwargs.pop("_container_result_dir", "/usr/src/app/results")
    kvs_env = kwargs.pop("_kvs_env", None)
    cache_env = kwargs.pop("_cache_env", None)

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
    threads.append(threading.Thread(target=run_kvs, args=(servers[1], home_path[where], stop_event, use_occ, kvs_env)))
    threads.append(threading.Thread(target=run_cache, args=(servers[0], home_path[where], stop_event, use_occ, cache_env)))
    threads.append(threading.Thread(target=run_client, args=(servers[0], stop_event, f_name, num_operations, strategy), kwargs=kwargs))
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    # Fetch data to local (Optional)
    fetch_data(
        servers[0],
        f_name,
        local_dir,
        local_suffix,
        container_file_dir=container_result_dir,
        local_file_name=local_file_name,
    )
    if fetch_invocations:
        fetch_data(
            servers[0],
            f_name,
            local_dir,
            local_suffix,
            container_file_dir=container_result_dir,
            file_name="invocations.jsonl",
            local_file_name=f"{f_name}{local_suffix}.jsonl",
        )
    if 'trace' in f_name:
        fetch_data(
            servers[0],
            f_name,
            local_dir,
            f"{local_suffix}detailed",
            container_file_dir=container_result_dir,
            file_name='temp_detailed.csv',
        )

def lab_run(f_name, num_operations=1000, strategy='local'):
    run('lab', f_name, num_operations, strategy)

def remote_run(f_name, num_operations=1000, strategy='local', use_occ=False, **kwargs):
    run('remote', f_name, num_operations, strategy, use_occ, **kwargs)

def fetch_data(
    remote_ip,
    f_name,
    local_dir=".",
    local_path_suffix="",
    container_file_dir="/usr/src/app/results",
    file_name='temp.csv',
    local_file_name=None,
):
    if local_file_name is None:
        local_file_name = f"{f_name}{local_path_suffix}.csv"
    local_path = FAASPE_DIR / "results" / local_dir / local_file_name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with Connection(remote_ip) as c:
        home = c.run("echo $HOME", hide=True).stdout.strip()
        remote_tmp = f"{remote_abs(REMOTE_FAASPE_DIR, home)}/{file_name}"
        c.run(f'docker cp faaspe-{f_name}:{container_file_dir}/{file_name} {remote_tmp}')
        c.get(remote_tmp, str(local_path))

def test():
    pass
