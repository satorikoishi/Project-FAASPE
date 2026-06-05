#!/usr/bin/python3
import click
import requests
import json

BASE_URL = "http://localhost:5000"  # URL of your Flask server

# Define a command to list all functions
@click.command()
def ls():
    """List all deployed serverless functions"""
    response = requests.get(f"{BASE_URL}/functions")
    if response.status_code == 200:
        functions = response.json()
        click.echo("Functions:")
        for function in functions:
            click.echo(f" - {function['name']}")
    else:
        click.echo("Error: Unable to fetch functions.")

# Define a command to create a function
@click.command()
@click.argument("function_code", type=str)
def create(function_code):
    """Create a new serverless function"""
    response = requests.post(
        f"{BASE_URL}/functions",
        data=function_code,
        headers={"Content-Type": "text/plain"},
    )
    if response.status_code == 201:
        function = response.json()
        click.echo(f"Function created: {function['name']}")
    else:
        click.echo("Error: Unable to create function.")

# Define a command to invoke a function
@click.command()
@click.argument("function_id", type=str)
@click.option("--params", type=str, help="JSON string containing parameters")
def invoke(function_id, params):
    """Invoke a deployed function"""
    if params:
        try:
            params_data = json.loads(params)  # Convert the JSON string into a Python dictionary
        except json.JSONDecodeError:
            click.echo("Error: Invalid JSON string provided for parameters.")
            return
    else:
        params_data = {}  # Default to empty dict if no parameters are provided

    response = requests.post(
        f"{BASE_URL}/functions/{function_id}/invoke",
        json=params_data  # Sending the parsed JSON as the request body
    )
    if response.status_code == 200:
        result = response.json()
        click.echo(f"Function result: {result['result']}")
        click.echo(f"E2E Latency: {result['latency_seconds']}")
    else:
        click.echo("Error: Unable to invoke function.")

# Define a command to delete a function
@click.command()
@click.argument("function_id", type=str)
def delete(function_id):
    """Delete a deployed function"""
    response = requests.delete(f"{BASE_URL}/functions/{function_id}")
    if response.status_code == 200:
        click.echo(f"Function {function_id} deleted.")
    else:
        click.echo("Error: Unable to delete function.")

# Group all commands into one entry point
@click.group()
def cli():
    pass

cli.add_command(ls)
cli.add_command(create)
cli.add_command(invoke)
cli.add_command(delete)

if __name__ == "__main__":
    cli()