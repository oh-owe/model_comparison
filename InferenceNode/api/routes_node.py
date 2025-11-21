"""
Node management API routes for InferenceNode
Handles node information, configuration, and restart
"""

from flask import jsonify, request
import platform
import tempfile
import threading
import subprocess
import sys
import os

try:
    from ..settings_manager import save_settings
    from ..utils import parse_windows_platform
    from .._version import __version__
except ImportError:
    from InferenceNode.settings_manager import save_settings
    from InferenceNode.utils import parse_windows_platform
    from InferenceNode._version import __version__


def register_node_routes(app, node):
    """Register all node-related routes with the Flask app"""
    
    @app.route('/api/node/info', methods=['GET'])
    def get_detailed_node_info():
        """Get comprehensive node information for the node info page"""
        try:
            import psutil
            import socket
            import uuid
            import time
            from datetime import datetime
            
            # Get system info
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            boot_time = psutil.boot_time()
            
            detailed_info = {
                'success': True,
                'data': {
                    # Basic system information
                    'node_id': node.node_id,
                    'version': __version__,
                    'platform': parse_windows_platform(platform.platform()),
                    'architecture': platform.architecture()[0],
                    'python_version': platform.python_version(),
                    'hostname': socket.gethostname(),
                    'ip_address': socket.gethostbyname(socket.gethostname()),
                    'mac_address': ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0,8*6,8)][::-1]),
                    'uptime': int(time.time() - boot_time),
                    'app_uptime': int(time.time() - node.app_start_time),
                    'start_time': datetime.fromtimestamp(boot_time).strftime('%Y-%m-%d %H:%M:%S'),
                    
                    # Hardware information
                    'hardware': {
                        'cpu_model': platform.processor() or 'Unknown',
                        'cpu_cores': psutil.cpu_count(logical=False),
                        'cpu_threads': psutil.cpu_count(logical=True),
                        'cpu_freq': psutil.cpu_freq().current if psutil.cpu_freq() else None,
                        'memory_total': memory.total,
                        'memory_available': memory.available,
                        'memory_used': memory.used,
                        'disk_total': disk.total,
                        'disk_used': disk.used,
                        'disk_free': disk.free,
                        'gpu_info': node.hardware_detector.get_gpu_details(),
                        'storage_info': node.hardware_detector.get_storage_details(),
                        'resource_usage': {
                            'cpu': psutil.cpu_percent(interval=1),
                            'memory': memory.percent,
                            'disk': (disk.used / disk.total) * 100
                        }
                    },
                    
                    # Configuration
                    'config': {
                        'node_name': node.node_name,
                        'log_level': 'INFO',
                        'web_port': node.port
                    },
                    
                    # Status
                    'status': {
                        'healthy': True,
                        'load_average': psutil.cpu_percent(interval=0.1),
                        'inference_count': len(getattr(node, 'active_pipelines', {})),
                        'error_count': 0
                    }
                }
            }
            
            return jsonify(detailed_info)
            
        except Exception as e:
            node.logger.error(f"Detailed node info error: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Failed to get detailed node info: {str(e)}'
            }), 500
    
    @app.route('/api/node/config', methods=['POST'])
    def update_node_config():
        """Update node configuration"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No configuration data provided'}), 400
            
            # Update node name if provided
            if 'node_name' in data and data['node_name']:
                old_name = node.node_name
                node.node_name = data['node_name']
                node.logger.info(f"Node name updated from '{old_name}' to '{node.node_name}'")
                
                # Update node info for discovery
                node.node_info['node_name'] = node.node_name
                if node.discovery_manager:
                    node.discovery_manager.set_node_info(node.node_id, node.node_info)
            
            # Update log level if provided
            if 'log_level' in data and node.log_manager:
                try:
                    node.log_manager.setup_logging(log_level=data['log_level'], enable_file_logging=True)
                    node.logger.info(f"Log level updated to {data['log_level']}")
                except Exception as e:
                    node.logger.warning(f"Failed to update log level: {e}")
            
            # Note: Web port changes would require restart
            if 'web_port' in data and data['web_port'] != node.port:
                node.logger.info(f"Web port change requested to {data['web_port']} (requires restart)")
            
            # Save settings
            save_settings(node)
            
            return jsonify({
                'success': True,
                'message': 'Configuration updated successfully',
                'config': {
                    'node_name': node.node_name,
                    'log_level': data.get('log_level', 'INFO'),
                    'web_port': node.port
                }
            })
            
        except Exception as e:
            node.logger.error(f"Update node config error: {str(e)}")
            return jsonify({'error': f'Failed to update configuration: {str(e)}'}), 500
    
    @app.route('/api/node/restart', methods=['POST'])
    def restart_node():
        """Restart the inference node"""
        try:
            node.logger.info("Restart requested via API")
            
            def perform_restart():
                import time
                time.sleep(1)
                node.logger.info("Performing restart...")
                
                node.stop()
                
                python = sys.executable
                script = sys.argv[0]
                
                if platform.system() == 'Windows':
                    batch_content = f'@echo off\ntimeout /t 2 /nobreak > nul\nstart "" "{python}" "{script}" {" ".join(sys.argv[1:])}\n'
                    batch_file = os.path.join(tempfile.gettempdir(), 'infernode_restart.bat')
                    with open(batch_file, 'w') as f:
                        f.write(batch_content)
                    subprocess.Popen(['cmd.exe', '/c', batch_file], 
                                   creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    os.execv(python, [python] + sys.argv)
                
                os._exit(0)
            
            restart_thread = threading.Thread(target=perform_restart)
            restart_thread.daemon = True
            restart_thread.start()
            
            return jsonify({
                'success': True,
                'message': 'Restart initiated'
            })
            
        except Exception as e:
            node.logger.error(f"Restart error: {str(e)}")
            return jsonify({'error': f'Failed to restart: {str(e)}'}), 500
