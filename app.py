from flask import Flask, jsonify
import psutil
import socket
import os
import threading
import time

app = Flask(__name__)

@app.route('/')
def index():
    return """
    <html>
    <head>
        <title>Resource Monitor Demo</title>
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
                <h1>Resource Monitor Demo</h1>
                <div>Running on: """ + socket.gethostname() + """</div>
            </div>
            
            <h2>System Resources</h2>
            
            <div class="metric """ + ("high" if psutil.cpu_percent() > 75 else "") + """">
                <h3>CPU Usage</h3>
                <div style="width: """ + str(psutil.cpu_percent()) + """%%; background: #0066ff; color: white; padding: 5px 0; text-align: center;">""" + str(psutil.cpu_percent()) + """%%</div>
            </div>
            
            <div class="metric """ + ("high" if psutil.virtual_memory().percent > 75 else "") + """">
                <h3>Memory Usage</h3>
                <div style="width: """ + str(psutil.virtual_memory().percent) + """%%; background: #33cc33; color: white; padding: 5px 0; text-align: center;">""" + str(psutil.virtual_memory().percent) + """%%</div>
            </div>
            
            <div class="metric """ + ("high" if psutil.disk_usage('/').percent > 75 else "") + """">
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

@app.route('/load/cpu/<int:percent>')
def load_cpu(percent):
    """Generate CPU load for testing"""
    if percent < 0 or percent > 100:
        return jsonify({'error': 'Percentage must be between 0 and 100'})
    
    def generate_load(target_percent):
        start_time = time.time()
        while True:
            x = 0
            while x < 1000000:
                x = x + 1
            time.sleep((100 - target_percent) / 100 * 0.1)
    
    for i in range(psutil.cpu_count()):
        t = threading.Thread(target=generate_load, args=(percent,))
        t.daemon = True
        t.start()
    
    return jsonify({'message': f'Generated {percent}% CPU load'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
