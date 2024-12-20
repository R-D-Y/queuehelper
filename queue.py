import subprocess
import json
import sys
import requests

def run_command(cmd: List[str]) -> str:
    """Execute a shell command and return output, handling both success and errors."""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error executing command {' '.join(cmd)}: {e.stderr}")
        sys.exit(1)

def get_organizations() -> List[Dict]:
    """Retrieve all organizations"""
    orgs_output = run_command(['cf', 'curl', '/v3/organizations'])
    orgs = json.loads(orgs_output)
    return orgs.get('resources', [])

def get_spaces(org_guid: str) -> List[Dict]:
    """Retrieve spaces for a given organization GUID"""
    spaces_output = run_command(['cf', 'curl', f'/v3/spaces?organization_guids={org_guid}'])
    spaces = json.loads(spaces_output)
    return spaces.get('resources', [])

def get_service_instances(space_guid: str) -> List[Dict]:
    """Retrieve service instances for a given space GUID"""
    services_output = run_command(['cf', 'curl', f'/v3/service_instances?space_guids={space_guid}&type=managed'])
    services = json.loads(services_output)
    return services.get('resources', [])

def check_queue_mirroring(api_uri: str, vhost: str, username: str, password: str) -> List[Dict]:
    """Check for mirrored queues using RabbitMQ HTTP API"""
    try:
        import urllib.parse
        encoded_vhost = urllib.parse.quote(vhost, safe='')
        response = requests.get(f"{api_uri}queues/{encoded_vhost}", auth=(username, password), verify=True)
        response.raise_for_status()
        queues = response.json()
        
        mirrored_queues = []
        for queue in queues:
            if 'mirrors' in queue and queue['mirrors'] > 0:
                mirrored_queues.append({
                    'name': queue['name'],
                    'mirrors': queue['mirrors']
                })
        
        return mirrored_queues
    except requests.exceptions.RequestException as e:
        print(f"Error checking queue mirroring: {e}")
        return []

def main():
    orgs = get_organizations()
    results = []
    for org in orgs:
        org_name = org['name']
        org_guid = org['guid']
        spaces = get_spaces(org_guid)
        for space in spaces:
            space_name = space['name']
            space_guid = space['guid']
            services = get_service_instances(space_guid)
            for service in services:
                if 'rabbitmq' in service['name'].lower():
                    print(f"Checking RabbitMQ service {service['name']} in {org_name}/{space_name}")
                    api_uri = service.get('http_api_uri')
                    username = service.get('username')
                    password = service.get('password')
                    vhost = service.get('vhost')
                    
                    if all([api_uri, username, password, vhost]):
                        mirrored_queues = check_queue_mirroring(api_uri, vhost, username, password)
                        if mirrored_queues:
                            results.append({
                                'service_instance': service['name'],
                                'organization': org_name,
                                'space': space_name,
                                'mirrored_queues': mirrored_queues
                            })
    
    if results:
        print("Found deprecated mirrored queues in the following instances:")
        for result in results:
            print(f"\nService Instance: {result['service_instance']} in {result['organization']}/{result['space']}")
            for queue in result['mirrored_queues']:
                print(f"Queue: {queue['name']}, Mirrors: {queue['mirrors']}")
    else:
        print("No deprecated mirrored queues found.")

if __name__ == '__main__':
    main()
