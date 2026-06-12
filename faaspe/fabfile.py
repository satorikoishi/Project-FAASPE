import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent / "scripts"))

from fabric import task
import cloudlab_init
import runner

@task
def hello(ctx):
    print("Hello world!")

@task
def init(ctx):
    cloudlab_init.batch_init()

@task
def init_clean(ctx):
    cloudlab_init.batch_clean()
    
@task
def run(ctx, f_name='ycsb', num_operations=1000, strategy='local', where='remote'):
    if where == 'lab':
        runner.lab_run(f_name, int(num_operations), strategy)
    else:
        runner.remote_run(f_name, int(num_operations), strategy)

@task
def remote_run(ctx, f_name='ycsb', num_operations=1000, strategy='local'):
    runner.remote_run(f_name, int(num_operations), strategy)

@task
def test(ctx):
    runner.test()
