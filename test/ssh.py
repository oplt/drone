# check_ssh_config.py
import subprocess
import os

# Check what SSH key you're currently using
print("Checking SSH configuration...")
print(f"Home directory: {os.path.expanduser('~')}")
print(f"SSH directory exists: {os.path.exists(os.path.expanduser('~/.ssh'))}")

# List SSH keys
ssh_dir = os.path.expanduser('~/.ssh')
if os.path.exists(ssh_dir):
    print("\nSSH keys found:")
    for file in os.listdir(ssh_dir):
        if file.endswith('.pub'):
            pub_key = os.path.join(ssh_dir, file)
            with open(pub_key, 'r') as f:
                print(f"  {file}: {f.read().strip()[:50]}...")

# Test SSH connection manually
print("\nTesting SSH connection manually...")
result = subprocess.run(
    ["ssh", "pi@192.168.129.14", "echo 'SSH test successful'"],
    capture_output=True,
    text=True
)
print(f"Exit code: {result.returncode}")
print(f"Stdout: {result.stdout}")
print(f"Stderr: {result.stderr}")