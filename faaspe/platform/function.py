#!/usr/bin/python3
import os
import subprocess
import docker
from flask import Flask, request, jsonify
import uuid
import time
import json
import sys

sys.path.append("./lib")
from arbiter import DEFAULT_PROFILES, PROFILE_MANIFEST

app = Flask(__name__)
client = docker.from_env()  # Docker client
FUNCTIONS_DIR = "./functions"
FAASPE_PREFIX = "faaspe-"

# Ensure functions directory exists
os.makedirs(FUNCTIONS_DIR, exist_ok=True)

@app.route("/functions", methods=["GET"])
def list_functions():
    """List all the running serverless functions"""
    all_containers = client.containers.list()
    containers = [container for container in all_containers if container.name.startswith('faaspe-')]
    functions = []
    for container in containers:
        functions.append({"id": container.id, "name": container.name})
    return jsonify(functions)

def try_destroy_function(function_name):
    try:
        container = client.containers.get(FAASPE_PREFIX + function_name)
        container.stop()
        container.remove()
        return True
    except docker.errors.NotFound:
        print(f"Function {function_name} not found")
        return False

def write_arbiter_profile(function_dir, function_name):
    profile = DEFAULT_PROFILES.get(function_name)
    if not profile:
        return
    manifest_path = os.path.join(function_dir, PROFILE_MANIFEST)
    with open(manifest_path, "w") as f:
        json.dump({function_name: profile}, f)

@app.route("/functions", methods=["POST"])
def create_function(): 
    """Create a new serverless function"""
    # func_uuid = str(uuid.uuid4())  # Unique function name
    
    # Search function code from directory
    function_name = request.data.decode("utf-8")
    # Remove running one, then update
    try_destroy_function(function_name)
    
    function_dir = os.path.join(FUNCTIONS_DIR, function_name)

    if not os.path.exists(function_dir):
        return f"Path {function_dir} not exist", 400
    write_arbiter_profile(function_dir, function_name)

    function_name = FAASPE_PREFIX + function_name  # Rename it, differenciate from other images
    
    #  # Check if a requirements.txt exists and prepare Dockerfile accordingly
    # requirements_txt = os.path.join(function_dir, "requirements.txt")
    # Check if the image already exists, and remove it if it does
    try:
        existing_image = client.images.get(function_name)  # Try to get the existing image by name
        print(f"Found existing image: {function_name}. Removing old image...")
        client.images.remove(existing_image.id)  # Remove the image
    except docker.errors.ImageNotFound:
        print(f"No existing image found for {function_name}. Proceeding to build a new one.")
    
    subprocess.run(["docker", "build", "-t", f"{FAASPE_PREFIX}base", "lib"], check=True)
    
    # Create a Docker image with the function code
    dockerfile = f"""
    FROM {FAASPE_PREFIX}base
    WORKDIR /usr/src/app
    COPY . .
    RUN if [ -f func_requirements.txt ]; then pip install --no-cache-dir -r func_requirements.txt; fi
    RUN if [ -f init_hack.sh ]; then ./init_hack.sh; fi
    CMD ["tail", "-f", "/dev/null"]
    """
    with open(os.path.join(function_dir, "Dockerfile"), "w") as f:
        f.write(dockerfile)

    # Build Docker image
    subprocess.run(["docker", "build", "-t", function_name, function_dir], check=True)

    # Run the function in a Docker container
    container = client.containers.run(
        function_name,
        detach=True,
        name=function_name,
    )

    return jsonify({"id": container.id, "name": container.name}), 201

@app.route("/functions/<function_id>", methods=["DELETE"])
def destroy_function(function_id):
    """Destroy a serverless function (stop and remove its container)"""
    ok = try_destroy_function(function_id)
    if ok:
        return jsonify({"status": "deleted", "id": function_id}), 200
    else:
        return jsonify({"error": "Function not found"}), 404

@app.route("/functions/<function_id>/invoke", methods=["POST"])
def invoke_function(function_id):
    """Invoke a serverless function by sending HTTP request"""
    try:
        # Load JSON data from the request
        data = request.get_json(silent=True) or {}
        
        container = client.containers.get(FAASPE_PREFIX + function_id)
        # Start timing for e2e latency measurement
        start_time = time.time()

        # Directly use the entire JSON payload as environment variables
        env_vars = {key: str(value) for key, value in data.items()}
        # Run the function inside the container and capture the output
        result = container.exec_run("python handler.py", environment=env_vars).output.decode("utf-8")
        
        # Calculate latency
        end_time = time.time()
        latency = end_time - start_time
        
        return jsonify({
            "result": result,
            "latency_seconds": latency
        }), 200
    except docker.errors.NotFound:
        return jsonify({"error": "Function not found"}), 404

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
