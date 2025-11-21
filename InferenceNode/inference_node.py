import os
import sys
import uuid
import logging
import platform
import json
from typing import Dict, Any, Optional
from flask import Flask

# Import version
try:
    from ._version import __version__
except ImportError:
    # Fallback if version file is not available
    __version__ = "0.1.0"

# Add InferenceEngine imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from InferenceEngine import InferenceEngineFactory


# Add parent directory to path for imports when running standalone
if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent_dir)
else:
    # When imported as a module, also ensure parent directory is in path
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

from ResultPublisher import ResultPublisher, ResultDestination

# Import ModelRepository
try:
    from .model_repo import ModelRepository
except ImportError:
    from InferenceNode.model_repo import ModelRepository

# Import HardwareDetector
try:
    from .hardware_detector import HardwareDetector
except ImportError:
    from InferenceNode.hardware_detector import HardwareDetector

# Import settings_manager
try:
    from .settings_manager import load_settings, save_settings
except ImportError:
    from InferenceNode.settings_manager import load_settings, save_settings

# Import utility functions
try:
    from .utils import parse_windows_platform
except ImportError:
    from InferenceNode.utils import parse_windows_platform

# Import log manager
try:
    from .log_manager import LogManager
except ImportError:
    try:
        from InferenceNode.log_manager import LogManager
    except ImportError:
        LogManager = None
        print("Warning: LogManager not available")

# Import PipelineManager from pipeline module
try:
    from .pipeline_manager import PipelineManager
except ImportError:
    try:
        from InferenceNode.pipeline_manager import PipelineManager
    except ImportError:
        PipelineManager = None
        print("Warning: PipelineManager not available")

# Import DiscoveryManager from discovery_manager module
try:
    from .discovery_manager import DiscoveryManager
except ImportError:
    try:
        from InferenceNode.discovery_manager import DiscoveryManager
    except ImportError:
        DiscoveryManager = None
        print("Warning: DiscoveryManager not available")

# Try to import optional components (graceful degradation)
try:
    from .telemetry import NodeTelemetry
except ImportError:
    try:
        # Try absolute import if relative import fails
        from InferenceNode.telemetry import NodeTelemetry
    except ImportError:
        NodeTelemetry = None
        print("Warning: NodeTelemetry not available")


class InferenceNode:
    """Main inference node class that coordinates all components"""
    
    def __init__(self, node_name: Optional[str] = None, port: int = 5000, node_id: Optional[str] = None):
        # Track app start time
        import time
        self.app_start_time = time.time()
        
        self.node_id = node_id or str(uuid.uuid4())
        self.node_name = node_name or f"InferNode-{platform.node()}"
        self.port = port
        
        # Settings file path
        self.settings_file = os.path.join(os.path.dirname(__file__), 'node_settings.json')
        
        # Setup logging first
        self.log_manager = None
        if LogManager:
            self.log_manager = LogManager()
            self.log_manager.setup_logging(log_level='INFO', enable_file_logging=True)
            print("[OK] Log manager initialized")
        else:
            # Fallback to basic logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            print("[ERROR] Log manager not available, using basic logging")
        
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Hardware detection (initialize early so node capabilities can use it)
        self.hardware_detector = HardwareDetector()
        print(f"[TOOL] Hardware detection completed:")
        print(f"   Available devices: {', '.join(self.hardware_detector.available_devices)}")
        
        # Core components
        self.inference_engine = None
        self.result_publisher = ResultPublisher()
        self.current_engine_info = None
        
        # Favorite publisher configurations
        self.favorite_configs = {}
        
        # Model repository
        repo_path = os.path.join(os.path.dirname(__file__), 'model_repository')
        self.model_repo = ModelRepository(repo_path)
        
        # Pipeline manager
        if PipelineManager:
            self.pipeline_manager = PipelineManager(repo_path, node_id=self.node_id, node_name=self.node_name)
        else:
            self.pipeline_manager = None
            print("[ERROR] Pipeline manager not available")
        
        # Discovery manager
        if DiscoveryManager:
            self.discovery_manager = DiscoveryManager()
            print(f"[OK] Discovery Manager initialized")
            print(f"   Discovery port: {self.discovery_manager.discovery_port}")
        else:
            self.discovery_manager = None
            print("[ERROR] DiscoveryManager not available")
        
        # Node capabilities and info (hardware detector is now available)
        self.node_info = self._get_node_capabilities()
        
        # Set node info in discovery manager for broadcasting
        if self.discovery_manager:
            self.discovery_manager.set_node_info(self.node_id, self.node_info)
        
        # Services (optional)
        self.telemetry = None
        
        if NodeTelemetry:
            self.telemetry = NodeTelemetry(self.node_id)
            print(f"[OK] Telemetry service initialized")
        else:
            print("[ERROR] Telemetry service not available")
        
        # Load saved settings
        load_settings(self)
        
        # Flask web API - use local templates and static files
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        # Use environment variable or generate a secure random key
        self.app.secret_key = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24).hex()
        self._setup_routes()
        
        self.logger.info(f"Inference node initialized: {self.node_name} ({self.node_id})")
    
    def _update_node_info_with_pipelines(self):
        """Update node_info with current pipeline information"""
        if self.pipeline_manager:
            # Only include basic pipeline stats for discovery announcements
            # Full pipeline info will be fetched by discovery server via API
            stats = self.pipeline_manager.get_pipeline_stats()
            self.node_info['pipeline_stats'] = stats
            
            # Update discovery manager with new info if it's running
            if self.discovery_manager and self.node_id:
                self.discovery_manager.set_node_info(self.node_id, self.node_info)
    
    def _get_node_capabilities(self) -> Dict[str, Any]:
        """Get node hardware capabilities"""
        try:
            import psutil
            
            # Basic system info
            capabilities = {
                "node_id": self.node_id,
                "node_name": self.node_name,
                "version": __version__,
                "platform": parse_windows_platform(platform.platform()),
                "processor": platform.processor(),
                "architecture": platform.architecture()[0],
                "cpu_count": psutil.cpu_count(),
                "memory_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "available_engines": InferenceEngineFactory.get_available_types(),
                "api_port": self.port
            }
            
            # Hardware detection using HardwareDetector
            capabilities["hardware"] = self.hardware_detector.hardware_info
            capabilities["available_devices"] = self.hardware_detector.available_devices
            capabilities["optimal_device"] = self.hardware_detector.get_optimal_device_for_hardware()
            
            return capabilities
            
        except ImportError:
            self.logger.warning("psutil not available for capability detection")
            # Fallback capabilities
            capabilities = {
                "node_id": self.node_id,
                "node_name": self.node_name,
                "version": __version__,
                "platform": parse_windows_platform(platform.platform()),
                "architecture": platform.architecture()[0],
                "processor": platform.processor(),
                # Fallbacks when psutil is unavailable
                "cpu_count": os.cpu_count() or 0,
                "memory_gb": None,
                "available_engines": InferenceEngineFactory.get_available_types(),
                "api_port": self.port
            }
            
            # Hardware detection using HardwareDetector (even without psutil)
            capabilities["hardware"] = self.hardware_detector.hardware_info
            capabilities["available_devices"] = self.hardware_detector.available_devices
            capabilities["optimal_device"] = self.hardware_detector.get_optimal_device_for_hardware()
            
            return capabilities
    
    def _setup_routes(self):
        """Setup Flask API routes using modular route registration"""
        try:
            from .api import register_routes
        except ImportError:
            from InferenceNode.api import register_routes
        register_routes(self.app, self)
        
        # NOTE: Routes now registered via api/__init__.py
        # Keeping this comment as a marker for the old route location
        return
        
    def _load_settings(self):
        """Load settings from file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                
                # Restore node configuration
                if 'node_name' in settings and settings['node_name']:
                    self.node_name = settings['node_name']
                    self.logger.info(f"Restored node name: {self.node_name}")
                
                # Restore publisher configurations
                if 'publishers' in settings:
                    for pub_config in settings['publishers']:
                        try:
                            # Map saved type names to actual destination types
                            destination_type = pub_config['type']
                            if destination_type in ['MQTTDestination', 'mqtt']:
                                destination_type = 'mqtt'
                            elif destination_type in ['WebhookDestination', 'webhook']:
                                destination_type = 'webhook'
                            elif destination_type in ['SerialDestination', 'serial']:
                                destination_type = 'serial'
                            elif destination_type in ['FileDestination', 'file']:
                                destination_type = 'file'
                            
                            # Clean up config - remove null values and empty strings
                            config = pub_config.get('config', {})
                            cleaned_config = {}
                            for key, value in config.items():
                                if value is not None and value != '':
                                    cleaned_config[key] = value
                            
                            self.logger.info(f"Attempting to restore {destination_type} publisher with config: {cleaned_config}")
                            
                            destination = ResultDestination(destination_type)
                            
                            # Set context variables for variable substitution
                            destination.set_context_variables(
                                node_id=self.node_id,
                                node_name=self.node_name
                            )
                            
                            destination.configure(**cleaned_config)
                            
                            # Restore rate limit if it exists
                            if 'rate_limit' in pub_config and pub_config['rate_limit'] is not None:
                                destination.set_rate_limit(pub_config['rate_limit'])
                            
                            # Restore include_image_data flag if it exists
                            if 'include_image_data' in pub_config:
                                destination.include_image_data = pub_config['include_image_data']
                            
                            # Restore the ID if it exists
                            if 'id' in pub_config:
                                destination._id = pub_config['id']
                                self.result_publisher.destinations.append(destination)
                                self.logger.info(f"[OK] Successfully restored publisher: {destination_type} with ID: {pub_config['id']}")
                            else:
                                # Generate new ID for legacy publishers without IDs
                                publisher_id = self.result_publisher.add(destination)
                                self.logger.info(f"[OK] Successfully restored publisher: {destination_type} with new ID: {publisher_id}")
                        except Exception as e:
                            self.logger.error(f"[ERROR] Failed to restore publisher {pub_config.get('type', 'unknown')}: {str(e)}")
                            # Log the full config for debugging
                            self.logger.debug(f"Failed config was: {pub_config.get('config', {})}")
                
                # Restore telemetry configuration
                if 'telemetry' in settings and self.telemetry:
                    telemetry_config = settings['telemetry']
                    try:
                        # Restore MQTT configuration
                        if telemetry_config.get('mqtt_server'):
                            # Use the new format with separate server and port
                            host = telemetry_config['mqtt_server']
                            port = telemetry_config.get('mqtt_port', 1883)
                            
                            # Store MQTT configuration attributes
                            self.telemetry.mqtt_server = host
                            self.telemetry.mqtt_port = port
                            self.telemetry.mqtt_topic = telemetry_config.get('mqtt_topic', 'infernode/telemetry')
                            
                            self.telemetry.configure_mqtt(
                                mqtt_server=host,
                                mqtt_port=port,
                                mqtt_topic=telemetry_config.get('mqtt_topic', 'infernode/telemetry')
                            )
                        elif telemetry_config.get('mqtt_broker'):
                            # Legacy format for backward compatibility
                            mqtt_broker = telemetry_config['mqtt_broker']
                            if ':' in mqtt_broker:
                                host, port = mqtt_broker.split(':', 1)
                                port = int(port)
                            else:
                                host = mqtt_broker
                                port = 1883
                            
                            # Store MQTT configuration attributes
                            self.telemetry.mqtt_server = host
                            self.telemetry.mqtt_port = port
                            self.telemetry.mqtt_topic = telemetry_config.get('mqtt_topic', 'infernode/telemetry')
                            
                            self.telemetry.configure_mqtt(
                                mqtt_server=host,
                                mqtt_port=port,
                                mqtt_topic=telemetry_config.get('mqtt_topic', 'infernode/telemetry')
                            )
                        
                        # Configure publish interval
                        if hasattr(self.telemetry, 'update_interval'):
                            self.telemetry.update_interval = float(telemetry_config.get('publish_interval', 30))
                        
                        # Start or stop telemetry based on enabled flag
                        enabled = telemetry_config.get('enabled', False)
                        if enabled:
                            self.telemetry.start_telemetry()
                            self.logger.info("[OK] Telemetry started based on saved settings")
                        else:
                            self.telemetry.stop_telemetry()
                            self.logger.info("[STOP] Telemetry stopped based on saved settings")
                        
                        self.logger.info("Restored telemetry configuration")
                    except Exception as e:
                        self.logger.error(f"Failed to restore telemetry config: {str(e)}")
                
                # Restore favorite publisher configurations
                if 'favorite_configs' in settings:
                    try:
                        self.favorite_configs = settings['favorite_configs']
                        favorite_count = len(self.favorite_configs)
                        self.logger.info(f"[PIN] Restored {favorite_count} favorite configuration(s)")
                    except Exception as e:
                        self.logger.error(f"Failed to restore favorite configs: {str(e)}")
                        self.favorite_configs = {}
                
                self.logger.info(f"Settings loaded from {self.settings_file}")
                
                # Log how many publishers were restored
                publisher_count = len(self.result_publisher.destinations) if self.result_publisher.destinations else 0
                self.logger.info(f"[LIST] Restored {publisher_count} publisher(s) from settings")
                
            else:
                self.logger.info("No settings file found, starting with default configuration")
                
        except Exception as e:
            self.logger.error(f"Failed to load settings: {str(e)}")
    
    def _save_settings(self):
        """Save current settings to file"""
        
        #TODO - check all these hard coded strings
        try:
            settings = {
                'node_id': self.node_id,
                'node_name': self.node_name,
                'publishers': [],
                'telemetry': {}
            }
            
            # Save publisher configurations
            for dest in self.result_publisher.destinations:
                # Determine destination type from class name or attributes
                dest_type = 'unknown'
                if hasattr(dest, 'server') and hasattr(dest, 'port') and hasattr(dest, 'topic'):
                    dest_type = 'mqtt'
                elif hasattr(dest, 'url'):
                    dest_type = 'webhook'
                elif hasattr(dest, 'com_port'):
                    dest_type = 'serial'
                elif hasattr(dest, 'file_path'):
                    dest_type = 'file'
                
                pub_config = {
                    'type': dest_type,
                    'config': {}
                }
                
                # Include publisher ID if it exists
                if hasattr(dest, '_id') and dest._id:
                    pub_config['id'] = dest._id
                
                # Include rate limit if it exists
                if hasattr(dest, 'rate_limit') and dest.rate_limit is not None:
                    pub_config['rate_limit'] = dest.rate_limit
                
                # Include image data flag if it exists
                if hasattr(dest, 'include_image_data'):
                    pub_config['include_image_data'] = getattr(dest, 'include_image_data', False)
                
                # Extract configuration based on destination type
                if dest_type == 'mqtt':
                    # MQTT destination - only save non-empty values
                    config = {}
                    if hasattr(dest, 'server') and getattr(dest, 'server', ''):
                        config['server'] = getattr(dest, 'server')
                    if hasattr(dest, 'port'):
                        config['port'] = getattr(dest, 'port', 1883)
                    if hasattr(dest, 'topic') and getattr(dest, 'topic', ''):
                        config['topic'] = getattr(dest, 'topic')
                    if hasattr(dest, 'username') and getattr(dest, 'username', ''):
                        config['username'] = getattr(dest, 'username')
                    if hasattr(dest, 'password') and getattr(dest, 'password', ''):
                        config['password'] = getattr(dest, 'password')
                    pub_config['config'] = config
                elif dest_type == 'webhook':
                    # Webhook destination - only save non-empty values
                    config = {}
                    if hasattr(dest, 'url') and getattr(dest, 'url', ''):
                        config['url'] = getattr(dest, 'url')
                    if hasattr(dest, 'headers') and getattr(dest, 'headers', {}):
                        config['headers'] = getattr(dest, 'headers')
                    if hasattr(dest, 'method'):
                        config['method'] = getattr(dest, 'method', 'POST')
                    pub_config['config'] = config
                elif dest_type == 'serial':
                    # Serial destination - only save non-empty values
                    config = {}
                    if hasattr(dest, 'com_port') and getattr(dest, 'com_port', ''):
                        config['com_port'] = getattr(dest, 'com_port')
                    if hasattr(dest, 'baud'):
                        config['baud'] = getattr(dest, 'baud', 9600)
                    if hasattr(dest, 'timeout'):
                        config['timeout'] = getattr(dest, 'timeout', 1)
                    pub_config['config'] = config
                elif dest_type == 'file':
                    # File destination - only save non-empty values
                    config = {}
                    if hasattr(dest, 'file_path') and getattr(dest, 'file_path', ''):
                        config['file_path'] = getattr(dest, 'file_path')
                    if hasattr(dest, 'format'):
                        config['format'] = getattr(dest, 'format', 'json')
                    pub_config['config'] = config
                
                settings['publishers'].append(pub_config)
            
            # Save telemetry configuration
            if self.telemetry:
                telemetry_config = {
                    'enabled': getattr(self.telemetry, 'running', False),
                    'publish_interval': getattr(self.telemetry, 'update_interval', 30)
                }
                
                # Add MQTT config if available
                if hasattr(self.telemetry, 'mqtt_server') and getattr(self.telemetry, 'mqtt_server', ''):
                    telemetry_config.update({
                        'mqtt_server': getattr(self.telemetry, 'mqtt_server', ''),
                        'mqtt_port': getattr(self.telemetry, 'mqtt_port', 1883),
                        'mqtt_topic': getattr(self.telemetry, 'mqtt_topic', 'infernode/telemetry')
                    })
                
                settings['telemetry'] = telemetry_config
            
            # Save favorite publisher configurations
            settings['favorite_configs'] = self.favorite_configs
            
            # Write settings to file
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            
            self.logger.info(f"Settings saved to {self.settings_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save settings: {str(e)}")
    
    def start(self, enable_discovery: bool = True, enable_telemetry: bool = False, production: bool = False):
        """Start the inference node
        
        Args:
            enable_discovery (bool): Enable discovery manager for finding other nodes
            enable_telemetry (bool): Enable telemetry data collection
            production (bool): If True, use Waitress WSGI server for production.
                              If False, use Flask development server.
        """
        try:
            # Initialize pipeline information in node_info
            self._update_node_info_with_pipelines()
            
            # Start discovery manager (for finding other nodes)
            if enable_discovery and self.discovery_manager:
                print(f"[DISCOVER] Starting discovery manager...")
                self.discovery_manager.start_discovery()
                print(f"[OK] Discovery manager started - listening on port {self.discovery_manager.discovery_port}")
                
                # Perform initial network scan to discover existing nodes
                print(f"[SCAN] Performing initial network scan...")
                import threading
                scan_thread = threading.Thread(target=self.discovery_manager.scan_network, daemon=True)
                scan_thread.start()
                print(f"[OK] Initial network scan started")
            elif enable_discovery and not self.discovery_manager:
                print(f"[ERROR] Discovery manager requested but service not available")
            
            # Start telemetry if requested
            if enable_telemetry and self.telemetry:
                print(f"[DATA] Starting telemetry service...")
                self.telemetry.start_telemetry()
                print(f"[OK] Telemetry service started")
            elif enable_telemetry and not self.telemetry:
                print(f"[ERROR] Telemetry requested but service not available")
            
            # Start the web server
            if production:
                from waitress import serve
                print(f"[LAUNCH] Starting production web server (Waitress) on port {self.port}...")
                self.logger.info(f"Starting inference node in production mode on port {self.port}")
                serve(self.app, host='0.0.0.0', port=self.port, threads=6)
            else:
                print(f"[LAUNCH] Starting development web server (Flask) on port {self.port}...")
                self.logger.info(f"Starting inference node in development mode on port {self.port}")
                self.app.run(host='0.0.0.0', port=self.port, debug=False)
            
        except Exception as e:
            self.logger.error(f"Failed to start node: {str(e)}")
            self.stop()
    
    def stop(self):
        """Stop the inference node and cleanup resources"""
        self.logger.info("Stopping inference node...")
        
        # Stop services
        if self.discovery_manager:
            self.discovery_manager.stop_discovery()
        if self.telemetry:
            self.telemetry.stop_telemetry()
        
        # Clear publishers
        self.result_publisher.clear()
        
        self.logger.info("Inference node stopped")


if __name__ == "__main__":
    import sys
    import argparse
    
    # Parse command line arguments with proper argument parser
    parser = argparse.ArgumentParser(description='Start an InferenceNode')
    parser.add_argument('--port', type=int, default=5555, help='Port to run the web interface on')
    parser.add_argument('--node-id', type=str, help='Specific node ID to use (optional)')
    parser.add_argument('--node-name', type=str, help='Human-readable node name')
    parser.add_argument('--discovery', type=str, default='true', choices=['true', 'false'], help='Enable discovery service')
    parser.add_argument('--telemetry', type=str, default='true', choices=['true', 'false'], help='Enable telemetry service')
    
    args = parser.parse_args()
    
    port = args.port
    node_name = args.node_name
    node_id = args.node_id
    enable_discovery = args.discovery.lower() == 'true'
    enable_telemetry = args.telemetry.lower() == 'true'
    
    # Create and start the node
    print(f"Starting InferenceNode...")
    print(f"  Node ID: {node_id or 'Auto-generated'}")
    print(f"  Node Name: {node_name or 'Auto-generated'}")
    print(f"  Port: {port}")
    print(f"  Discovery: {'Enabled' if enable_discovery else 'Disabled'}")
    print(f"  Telemetry: {'Enabled' if enable_telemetry else 'Disabled'}")
    print(f"  Web Interface: http://localhost:{port}")
    print("-" * 50)
    
    node = InferenceNode(node_name, port=port, node_id=node_id)
    
    try:
        node.start(enable_discovery=enable_discovery, enable_telemetry=enable_telemetry)
    except KeyboardInterrupt:
        print("\nShutting down...")
        node.stop()
