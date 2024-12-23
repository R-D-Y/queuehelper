import subprocess
import json
import sys
import os
from typing import Dict, List, Set, Tuple
import requests


def check_cf_auth() -> bool:
    """Check if user is authenticated with CF CLI"""
    try:
        result = subprocess.run(['cf', 'target'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        if result.returncode != 0:
            print("Error: Not authenticated with CF CLI. Please run 'cf login' first.")
            return False
            
        if 'org:' not in result.stdout or 'space:' not in result.stdout:
            print("Error: No org/space targeted. Please run 'cf target -o ORG -s SPACE' first.")
            return False
            
        return True
        
    except FileNotFoundError:
        print("Error: CF CLI not found. Please install it first.")
        return False


def run_command(cmd: List[str]) -> str:
    """Execute a shell command and return output"""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error executing command {' '.join(cmd)}: {e.stderr}")
        sys.exit(1)


def get_service_instances() -> List[Dict]:
    """Get all RabbitMQ service instances across foundation"""
    instances = []
    
    try:
        # Get all orgs
        orgs_output = run_command(['cf', 'curl', '/v3/organizations'])
        orgs = json.loads(orgs_output)
        
        if 'resources' not in orgs:
            print("Error: Unexpected API response format for organizations")
            sys.exit(1)
        
        for org in orgs['resources']:
            org_guid = org['guid']
            org_name = org['name']
            
            # Get spaces in org
            spaces_output = run_command(['cf', 'curl', f'/v3/spaces?organization_guids={org_guid}'])
            spaces = json.loads(spaces_output)
            
            if 'resources' not in spaces:
                print(f"Error: Unexpected API response format for spaces in org {org_name}")
                continue
            
            for space in spaces['resources']:
                space_guid = space['guid']
                space_name = space['name']
                
                # Get service instances in space
                services_output = run_command(['cf', 'curl', f'/v3/service_instances?space_guids={space_guid}&type=managed'])
                services = json.loads(services_output)
                
                if 'resources' not in services:
                    print(f"Error: Unexpected API response format for services in space {space_name}")
                    continue
                
                for service in services['resources']:
                    if ('name' in service and 
                        isinstance(service['name'], str) and 
                        'rabbitmq' in service['name'].lower()):
                        instances.append({
                            'guid': service['guid'],
                            'name': service['name'],
                            'org_name': org_name,
                            'space_name': space_name
                        })
    
    except Exception as e:
        print(f"Error getting service instances: {e}")
        sys.exit(1)
        
    return instances


def get_instance_credentials(instance_guid: str, org_name: str, space_name: str) -> Dict:
    """Get RabbitMQ credentials from service key"""
    try:
        # First target the correct org/space
        run_command(['cf', 'target', '-o', org_name, '-s', space_name])
        
        # Get the service name using the GUID
        service_info = json.loads(run_command(['cf', 'curl', f'/v3/service_instances/{instance_guid}']))
        service_name = service_info['name']
        print(f"DEBUG: Getting credentials for service: {service_name} in {org_name}/{space_name}")
        
        # Get service key info
        key_output = run_command(['cf', 'service-key', service_name, 'admin-key'])
        
        # Clean up the output to ensure valid JSON
        json_lines = []
        started = False
        for line in key_output.splitlines():
            if '{' in line:
                started = True
            if started:
                json_lines.append(line)
                
        if not json_lines:
            print("DEBUG: No JSON content found in service key output")
            return {}
            
        json_content = '\n'.join(json_lines)
        
        try:
            return json.loads(json_content)
        except json.JSONDecodeError as e:
            print(f"Error parsing credentials JSON: {e}")
            return {}
            
    except Exception as e:
        print(f"Error getting instance credentials: {e}")
        return {}


def check_queue_mirroring(api_uri: str, vhost: str, username: str, password: str) -> List[Dict]:
    """Check for mirrored queues using RabbitMQ HTTP API"""
    try:
        # URL encode the vhost
        import urllib.parse
        encoded_vhost = urllib.parse.quote(vhost, safe='')
        
        # Get all queues in the vhost
        response = requests.get(
            f"{api_uri}queues/{encoded_vhost}",
            verify=True
        )
        response.raise_for_status()
        queues = response.json()
        
        mirrored_queues = []
        for queue in queues:
            # Check if queue has slave nodes (mirrors)
            if queue.get('slave_nodes') and len(queue['slave_nodes']) > 0:
                mirrored_queues.append({
                    'name': queue['name'],
                    'policy': queue.get('policy'),
                    'mirrors': len(queue['slave_nodes']),
                    'synchronized_mirrors': len(queue.get('synchronised_slave_nodes', [])),
                    'policy_definition': queue.get('effective_policy_definition', {})
                })
        
        return mirrored_queues
        
    except requests.exceptions.RequestException as e:
        print(f"Error checking queue mirroring: {e}")
        return []


def main():
    if not check_cf_auth():
        sys.exit(1)
        
    print("Analyzing RabbitMQ instances...")
    
    instances = get_service_instances()
    results = []
    
    for instance in instances:
        print(f"Checking instance: {instance['name']} in {instance['org_name']}/{instance['space_name']}")
        credentials = get_instance_credentials(instance['guid'], instance['org_name'], instance['space_name'])
        
        if not credentials:
            print(f"No credentials found for {instance['name']}")
            continue
            
        api_uri = credentials.get('http_api_uri')
        username = credentials.get('username')
        password = credentials.get('password')
        vhost = credentials.get('vhost')
        
        if not all([api_uri, username, password, vhost]):
            print(f"Missing required credential information for {instance['name']}")
            continue
            
        mirrored_queues = check_queue_mirroring(api_uri, vhost, username, password)
        
        if mirrored_queues:
            results.append({
                'service_instance': instance['name'],
                'organization': instance['org_name'],
                'space': instance['space_name'],
                'mirrored_queues': mirrored_queues
            })
    
    if results:
        print("\nFound instances using classic queue mirroring:")
        print(json.dumps(results, indent=2))
        print("\nSummary:")
        for result in results:
            print(f"\nInstance: {result['service_instance']} in {result['organization']}/{result['space']}")
            print("\nMirrored Queues:")
            for queue in result['mirrored_queues']:
                print(f"  - Queue: {queue['name']}")
                print(f"    Policy: {queue['policy']}")
                print(f"    Mirrors: {queue['mirrors']} ({queue['synchronized_mirrors']} synchronized)")
    else:
        print("\nNo instances found using classic queue mirroring")


if __name__ == '__main__':
    main()
