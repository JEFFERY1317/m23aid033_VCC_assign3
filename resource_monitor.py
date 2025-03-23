import time
import psutil
import requests
import json
import logging
import os
import subprocess
import traceback
from prometheus_client import start_http_server, Gauge
from google.oauth2 import service_account
from googleapiclient import discovery


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='/var/log/resource_monitor.log'
)


CHECK_INTERVAL = 30  
THRESHOLD = 75  


PROJECT_ID = "m23aid033-vcc-assign3"
ZONE = "us-central1-a"  
MACHINE_TYPE = "e2-medium"  
IMAGE_PROJECT = "ubuntu-os-cloud"
IMAGE_FAMILY = "ubuntu-2004-lts"
SERVICE_ACCOUNT_FILE = "/opt/monitoring/gcp-credentials.json"


cpu_usage = Gauge('system_cpu_usage_percent', 'Current CPU usage in percent')
memory_usage = Gauge('system_memory_usage_percent', 'Current memory usage in percent')
disk_usage = Gauge('system_disk_usage_percent', 'Current disk usage in percent')

def collect_metrics():
    """Collect system resource metrics and update Prometheus gauges"""
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_usage.set(cpu_percent)
    
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    memory_usage.set(memory_percent)
    
    disk = psutil.disk_usage('/')
    disk_percent = disk.percent
    disk_usage.set(disk_percent)
    
    return {
        'cpu': cpu_percent,
        'memory': memory_percent,
        'disk': disk_percent
    }

def should_scale():
    """Determine if we should scale to the cloud based on resource usage"""
    metrics = collect_metrics()
    logging.info(f"Current metrics - CPU: {metrics['cpu']}%, Memory: {metrics['memory']}%, Disk: {metrics['disk']}%")
    
    if metrics['cpu'] > THRESHOLD or metrics['memory'] > THRESHOLD:
        logging.warning(f"Resource usage exceeds threshold of {THRESHOLD}%!")
        return True
    
    return False

def create_gcp_instance():
    """Create a new GCP VM instance when resources exceed threshold"""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        compute = discovery.build('compute', 'v1', credentials=credentials, cache_discovery=False)
      
        instance_name = f"auto-scaled-vm-{int(time.time())}"
        
        instance_body = {
            'name': instance_name,
            'machineType': f"zones/{ZONE}/machineTypes/{MACHINE_TYPE}",
            'disks': [{
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': f"projects/{IMAGE_PROJECT}/global/images/family/{IMAGE_FAMILY}"
                }
            }],
            'networkInterfaces': [{
                'network': 'global/networks/default',
                'accessConfigs': [
                    {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
                ]
            }],
            'metadata': {
                'items': [{
                    'key': 'startup-script',
                    'value': '''#!/bin/bash
                        apt-get update
                        apt-get install -y git docker.io docker-compose
                        systemctl enable docker
                        systemctl start docker
                        
                        # Create app directory
                        mkdir -p /home/ubuntu/app
                        
                        # Create app files
                        cat > /home/ubuntu/app/docker-compose.yml << 'EOFINNER'
                        version: '3'
                        services:
                          webapp:
                            build: .
                            ports:
                              - "80:5000"
                            restart: always
                            environment:
                              - FLASK_APP=app.py
                              - FLASK_ENV=production
                        EOFINNER
                        
                        cat > /home/ubuntu/app/Dockerfile << 'EOFINNER'
                        FROM python:3.9-slim
                        
                        WORKDIR /app
                        
                        COPY requirements.txt .
                        RUN pip install --no-cache-dir -r requirements.txt
                        
                        COPY . .
                        
                        CMD ["python", "app.py"]
                        EOFINNER
                        
                        cat > /home/ubuntu/app/requirements.txt << 'EOFINNER'
                        flask==2.0.1
                        werkzeug==2.0.3
                        psutil==5.8.0
                        EOFINNER
                        
                        cat > /home/ubuntu/app/app.py << 'EOFINNER'
                        from flask import Flask, jsonify
                        import psutil
                        import socket
                        import os
                        
                        app = Flask(__name__)
                        
                        @app.route('/')
                        def index():
                            return """
                            <html>
                            <head>
                                <title>GCP Auto-Scaled Instance</title>
                                <meta http-equiv="refresh" content="5">
                                <style>
                                    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                                    .container { max-width: 800px; margin: 0 auto; }
                                    .metric { background: #f4f4f4; padding: 15px; margin-bottom: 10px; border-radius: 5px; }
                                    .high { background: #ffdddd; }
                                    .header { display: flex; justify-content: space-between; align-items: center; }
                                    h1 { color: #333; }
                                </style>
                            </head>
                            <body>
                                <div class="container">
                                    <div class="header">
                                        <h1>GCP Auto-Scaled Instance</h1>
                                        <div>Running on: """ + socket.gethostname() + """</div>
                                    </div>
                                    
                                    <h2>System Resources</h2>
                                    
                                    <div class="metric">
                                        <h3>CPU Usage</h3>
                                        <div style="width: """ + str(psutil.cpu_percent()) + """%%; background: #0066ff; color: white; padding: 5px 0; text-align: center;">""" + str(psutil.cpu_percent()) + """%%</div>
                                    </div>
                                    
                                    <div class="metric">
                                        <h3>Memory Usage</h3>
                                        <div style="width: """ + str(psutil.virtual_memory().percent) + """%%; background: #33cc33; color: white; padding: 5px 0; text-align: center;">""" + str(psutil.virtual_memory().percent) + """%%</div>
                                    </div>
                                    
                                    <div class="metric">
                                        <h3>Disk Usage</h3>
                                        <div style="width: """ + str(psutil.disk_usage('/').percent) + """%%; background: #ff9900; color: white; padding: 5px 0; text-align: center;">""" + str(psutil.disk_usage('/').percent) + """%%</div>
                                    </div>
                                    
                                    <h2>System Information</h2>
                                    <div class="metric">
                                        <h3>Platform</h3>
                                        """ + " ".join(os.uname()) + """
                                    </div>
                                </div>
                            </body>
                            </html>
                            """
                        
                        @app.route('/api/metrics')
                        def metrics():
                            return jsonify({
                                'cpu': psutil.cpu_percent(),
                                'memory': psutil.virtual_memory().percent,
                                'disk': psutil.disk_usage('/').percent,
                                'hostname': socket.gethostname()
                            })
                        
                        if __name__ == '__main__':
                            app.run(host='0.0.0.0', port=5000)
                        EOFINNER
                        
                        # Deploy application
                        cd /home/ubuntu/app
                        docker-compose up -d
                    '''
                }]
            },
            'tags': {
                'items': [
                    'http-server',
                    'https-server'
                ]
            }
        }

        logging.info(f"Creating GCP instance: {instance_name}")
        operation = compute.instances().insert(
            project=PROJECT_ID,
            zone=ZONE,
            body=instance_body
        ).execute()
        
        wait_for_operation(compute, PROJECT_ID, ZONE, operation['name'])
  
        instance = compute.instances().get(
            project=PROJECT_ID,
            zone=ZONE,
            instance=instance_name
        ).execute()

        external_ip = instance['networkInterfaces'][0]['accessConfigs'][0].get('natIP')
        logging.info(f"Instance created successfully. External IP: {external_ip}")
        
        return instance_name
    
    except Exception as e:
        logging.error(f"Error creating GCP instance: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return None

def wait_for_operation(compute, project, zone, operation):
    """Wait for a GCP operation to complete"""
    logging.info(f"Waiting for operation {operation} to finish...")
    while True:
        result = compute.zoneOperations().get(
            project=project,
            zone=zone,
            operation=operation
        ).execute()
        
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return result
        
        time.sleep(5)

def main():
    """Main function to run the monitoring loop"""
    start_http_server(8000)
    logging.info("Resource monitor started. Prometheus metrics available at :8000")
    
    scaled = False
    
    while True:
        if not scaled and should_scale():
            instance_name = create_gcp_instance()
            if instance_name:
                scaled = True
                logging.info(f"Scaled to GCP instance: {instance_name}")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
