"""
Telemetry API routes for InferenceNode
Handles telemetry configuration and data retrieval
"""

from flask import jsonify, request
import platform

try:
    from ..settings_manager import save_settings
    from ..utils import parse_windows_platform
except ImportError:
    from InferenceNode.settings_manager import save_settings
    from InferenceNode.utils import parse_windows_platform


def register_telemetry_routes(app, node):
    """Register all telemetry-related routes with the Flask app"""
    
    @app.route('/api/telemetry/configure', methods=['POST'])
    def configure_telemetry():
        """Configure telemetry settings"""
        try:
            data = request.get_json()
            
            if not node.telemetry:
                return jsonify({'error': 'Telemetry service not available'}), 400
            
            enabled = data.get('enabled', True)
            publish_interval = data.get('publish_interval', 30)
            mqtt_server = data.get('mqtt_server', '')
            mqtt_port = data.get('mqtt_port', 1883)
            mqtt_topic = data.get('mqtt_topic', 'infernode/telemetry')
            
            if mqtt_server:
                try:
                    node.telemetry.configure_mqtt(
                        mqtt_server=mqtt_server,
                        mqtt_port=int(mqtt_port),
                        mqtt_topic=mqtt_topic
                    )
                except Exception as e:
                    return jsonify({'error': f'Failed to configure MQTT: {str(e)}'}), 400
            
            if hasattr(node.telemetry, 'update_interval'):
                node.telemetry.update_interval = float(publish_interval)
            
            if enabled:
                node.telemetry.start_telemetry()
            else:
                node.telemetry.stop_telemetry()
            
            save_settings(node)
            
            return jsonify({
                'status': 'configured',
                'enabled': enabled,
                'publish_interval': publish_interval,
                'mqtt_server': mqtt_server,
                'mqtt_port': mqtt_port,
                'mqtt_topic': mqtt_topic
            })
            
        except Exception as e:
            node.logger.error(f"Telemetry configuration error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/telemetry/config', methods=['GET'])
    def get_telemetry_config():
        """Get current telemetry configuration"""
        try:
            if not node.telemetry:
                return jsonify({'error': 'Telemetry service not available'}), 400
            
            config = {
                'enabled': getattr(node.telemetry, 'running', False),
                'publish_interval': getattr(node.telemetry, 'update_interval', 30),
                'mqtt_server': getattr(node.telemetry, 'mqtt_server', ''),
                'mqtt_port': getattr(node.telemetry, 'mqtt_port', 1883),
                'mqtt_topic': getattr(node.telemetry, 'mqtt_topic', 'infernode/telemetry')
            }
            
            return jsonify(config)
            
        except Exception as e:
            node.logger.error(f"Get telemetry config error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/telemetry', methods=['GET'])
    def get_telemetry_data():
        """Get current telemetry data"""
        try:
            if not node.telemetry:
                return jsonify({
                    'metrics': {
                        'cpu': 0,
                        'memory': 0,
                        'disk': 0,
                        'temperature': None
                    },
                    'system': {
                        'uptime': 0,
                        'node_id': node.node_id,
                        'platform': parse_windows_platform(platform.platform()),
                        'cpu_cores': node.node_info.get('cpu_count', 0),
                        'total_memory': node.node_info.get('memory_gb', 0) * 1024**3,
                        'disk_space': 0,
                        'gpu_info': 'Not available'
                    },
                    'network': {
                        'ip_address': 'Unknown',
                        'hostname': platform.node(),
                        'usage_percent': 0,
                        'bytes_recv': 0,
                        'bytes_sent': 0
                    }
                })
            
            system_info = node.telemetry.get_system_info()
            
            telemetry_data = {
                'metrics': {
                    'cpu': system_info.get('cpu', {}).get('usage_percent', 0),
                    'memory': system_info.get('memory', {}).get('usage_percent', 0),
                    'disk': system_info.get('disk', {}).get('usage_percent', 0),
                    'temperature': system_info.get('cpu', {}).get('temperature_c', None)
                },
                'system': {
                    'uptime': 0,
                    'node_id': node.node_id,
                    'platform': system_info.get('system', {}).get('platform', parse_windows_platform(platform.platform())),
                    'cpu_cores': system_info.get('cpu', {}).get('count', 0),
                    'total_memory': system_info.get('memory', {}).get('total_gb', 0) * 1024**3,
                    'disk_space': system_info.get('disk', {}).get('total_gb', 0) * 1024**3,
                    'gpu_info': str(system_info.get('gpu', {}).get('devices', 'Not available'))
                },
                'network': {
                    'ip_address': 'Unknown',
                    'hostname': platform.node(),
                    'usage_percent': 0,
                    'bytes_recv': system_info.get('network', {}).get('bytes_recv', 0),
                    'bytes_sent': system_info.get('network', {}).get('bytes_sent', 0)
                }
            }
            
            return jsonify(telemetry_data)
            
        except Exception as e:
            node.logger.error(f"Get telemetry data error: {str(e)}")
            return jsonify({'error': str(e)}), 500
