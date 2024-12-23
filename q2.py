import subprocess
import json
import sys
from typing import Dict, List

def run_command(cmd: List[str]) -> str:
    """Execute a shell command and return output"""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if result.returncode != 0:
            print(f"Command failed with error: {result.stderr}")
            return None
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error executing command {' '.join(cmd)}: {e}")
        sys.exit(1)

def get_service_instances() -> List[Dict]:
    """Get all RabbitMQ service instances across the foundation"""
    instances = []
    # Get all orgs
    orgs_output = run_command(['cf', 'curl', '/v3/organizations'])
    if not orgs_output:
        print("Failed to retrieve organizations.")
        return instances

    orgs = json.loads(orgs_output)
    if 'resources' not in orgs:
        print("Error: Unexpected API response format for organizations")
        return instances

    for org in orgs['resources']:
        org_guid = org['guid']
        org_name = org['name']
        # Get spaces in org
        spaces_output = run_command(['cf', 'curl', f'/v3/spaces?organization_guids={org_guid}'])
        if not spaces_output:
            print(f"Failed to retrieve spaces for organization {org_name}")
            continue

        spaces = json.loads(spaces_output)
        if 'resources' not in spaces:
            print(f"Error: Unexpected API response format for spaces in org {org_name}")
            continue

        for space in spaces['resources']:
            space_guid = space['guid']
            space_name = space['name']
            # Get service instances in space
            services_output = run_command(['cf', 'curl', f'/v3/service_instances?space_guids={space_guid}&type=managed'])
            if not services_output:
                print(f"Failed to retrieve services for space {space_name}")
                continue

            services = json.loads(services_output)
            if 'resources' not in services:
                print(f"Error: Unexpected API response format for services in space {space_name}")
                continue

            for service in services['resources']:
                if 'rabbitmq' in service['name'].lower():
                    instances.append({
                        'guid': service['guid'],
                        'name': service['name'],
                        'org_name': org_name,
                        'space_name': space_name
                    })

    return instances

def main():
    print("Analyzing RabbitMQ instances...")
    instances = get_service_instances()
    if not instances:
        print("No RabbitMQ instances found.")
        return

    for instance in instances:
        print(f"Found RabbitMQ instance: {instance['name']} in {instance['org_name']}/{instance['space_name']}")

if __name__ == '__main__':
    main()
