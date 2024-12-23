import subprocess
import json
import sys
import os
from typing import Dict, List, Set, Tuple
import requests

def run_command(cmd: List[str]) -> str:
    """Execute a shell command and return output, handling errors and successes."""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error executing command {' '.join(cmd)}: {e.stderr}")
        sys.exit(1)

def get_all_orgs_and_spaces() -> List[Tuple[str, str, str, str]]:
    """Retrieve all organizations and their spaces to prepare for service instance queries."""
    all_orgs_spaces = []
    orgs_output = run_command(['cf', 'curl', '/v3/organizations'])
    orgs = json.loads(orgs_output)
    if 'resources' in orgs:
        for org in orgs['resources']:
            org_name = org['name']
            org_guid = org['guid']
            spaces_output = run_command(['cf', 'curl', f'/v3/spaces?organization_guids={org_guid}'])
            spaces = json.loads(spaces_output)
            if 'resources' in spaces:
                for space in spaces['resources']:
                    all_orgs_spaces.append((org_name, org_guid, space['name'], space['guid']))
    return all_orgs_spaces

def get_service_instances(org_name: str, space_name: str, space_guid: str) -> List[Dict]:
    """Get all RabbitMQ service instances in a specific space across the foundation."""
    instances = []
    services_output = run_command(['cf', 'curl', f'/v3/service_instances?space_guids={space_guid}&type=managed'])
    services = json.loads(services_output)
    if 'resources' in services:
        for service in services['resources']:
            if 'rabbitmq' in service['name'].lower():
                instances.append({
                    'guid': service['guid'],
                    'name': service['name'],
                    'org_name': org_name,
                    'space_name': space_name
                })
    return instances

def get_instance_credentials(service_guid: str) -> Dict:
    """Retrieve credentials for a specific service instance identified by GUID."""
    service_keys_output = run_command(['cf', 'curl', f'/v3/service_credential_bindings?service_instance_guids={service_guid}'])
    service_keys = json.loads(service_keys_output)
    if 'resources' in service_keys:
        service_key_guid = service_keys['resources'][0]['guid']
        key_output = run_command(['cf', 'curl', f'/v3/service_credential_bindings/{service_key_guid}/details'])
        return json.loads(key_output)
    return {}

def check_queue_mirroring(credentials: Dict) -> List[Dict]:
    """Check for mirrored queues using RabbitMQ HTTP API."""
    api_uri = credentials.get('uri')
    username = credentials.get('username')
    password = credentials.get('password')
    vhost = credentials.get('vhost')
    try:
        encoded_vhost = requests.utils.quote(vhost, safe='')
        response = requests.get(f"{api_uri}/api/queues/{encoded_vhost}", auth=(username, password), verify=True)
        queues = response.json()
        mirrored_queues = [q for q in queues if 'slave_nodes' in q and len(q['slave_nodes']) > 0]
        return mirrored_queues
    except requests.exceptions.RequestException as e:
        print(f"Error checking queue mirroring: {e}")
        return []

def main():
    all_orgs_spaces = get_all_orgs_and_spaces()
    for org_name, org_guid, space_name, space_guid in all_orgs_spaces:
        instances = get_service_instances(org_name, space_name, space_guid)
        for instance in instances:
            credentials = get_instance_credentials(instance['guid'])
            if credentials:
                mirrored_queues = check_queue_mirroring(credentials)
                if mirrored_queues:
                    print(f"Mirrored queues found in {instance['name']} under {org_name}/{space_name}")
                    for queue in mirrored_queues:
                        print(f"Queue Name: {queue['name']}, Mirrors: {len(queue['slave_nodes'])}")
            else:
                print(f"No credentials found for {instance['name']} under {org_name}/{space_name}")

if __name__ == '__main__':
    main()
