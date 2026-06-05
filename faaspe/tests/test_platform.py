import subprocess
import time
import pytest
import sys

# The URL where your serverless platform is running (default is localhost:5000)
BASE_URL = "http://localhost:5000"
function_name = "hello-world"
CLI_PATH = "./platform/cli.py"

@pytest.fixture(scope="module")
def setup_class():
    print("Setting up class resources.")
    yield
    print("Tearing down class resources.")

def run_cli_command(command):
    """Run a CLI command and return the output."""
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout

@pytest.mark.run(order=1)
def test_list_functions():
    """Test the 'ls' command."""
    output = run_cli_command(["python3", CLI_PATH, "ls"])
    assert "Functions:" in output

@pytest.mark.run(order=2)
def test_create_function():
    """Test the 'create' command."""
    output = run_cli_command(["python3", CLI_PATH, "create", function_name])
    assert "Function created:" in output

@pytest.mark.run(order=3)
def test_invoke_function():
    """Test the 'invoke' command."""
    output = run_cli_command(["python3", CLI_PATH, "invoke", function_name])
    assert "Function result:" in output
    
@pytest.mark.run(order=4)
def test_delete_function():
    """Test the 'delete' command."""
    output = run_cli_command(["python3", CLI_PATH, "delete", function_name])
    assert f"Function {function_name} deleted." in output
