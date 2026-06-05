import sys
sys.path.append('./scripts')

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
def run(ctx, f_name='ycsb'):
    runner.lab_run(f_name)

@task
def remote_run(ctx, f_name='ycsb'):
    runner.remote_run(f_name)

@task
def test(ctx):
    runner.test()