"""
Settings management for InferenceNode
Handles loading and saving node configuration
"""
import os
import json
import logging


logger = logging.getLogger(__name__)


def load_settings(node):
    """Load saved settings from file"""
    try:
        if os.path.exists(node.settings_file):
            with open(node.settings_file, 'r') as f:
                settings = json.load(f)
                
                # Restore node name if saved
                if 'node_name' in settings:
                    node.node_name = settings['node_name']
                    node.node_info['node_name'] = node.node_name
                
                # Restore favorite configurations
                if 'favorite_configs' in settings:
                    node.favorite_configs = settings['favorite_configs']
                    logger.info(f"Loaded {len(node.favorite_configs)} favorite configurations")
                
                # Restore result publishers
                if 'result_publishers' in settings:
                    _deserialize_publishers(settings['result_publishers'], node)
                
                # Restore telemetry settings
                if 'telemetry' in settings and node.telemetry:
                    telemetry_settings = settings['telemetry']
                    
                    # Configure MQTT if settings exist
                    if 'mqtt_server' in telemetry_settings:
                        try:
                            node.telemetry.configure_mqtt(
                                mqtt_server=telemetry_settings['mqtt_server'],
                                mqtt_port=telemetry_settings.get('mqtt_port', 1883),
                                mqtt_topic=telemetry_settings.get('mqtt_topic', 'infernode/telemetry')
                            )
                        except Exception as e:
                            logger.warning(f"Failed to restore telemetry MQTT config: {e}")
                    
                    # Set publish interval
                    if 'publish_interval' in telemetry_settings:
                        node.telemetry.update_interval = telemetry_settings['publish_interval']
                    
                    # Start telemetry if it was enabled
                    if telemetry_settings.get('enabled', False):
                        node.telemetry.start_telemetry()
                
                logger.info(f"Settings loaded from {node.settings_file}")
                
    except Exception as e:
        logger.warning(f"Failed to load settings: {e}")


def save_settings(node):
    """Save current settings to file"""
    try:
        settings = {
            'node_name': node.node_name,
            'favorite_configs': node.favorite_configs,
            'result_publishers': _serialize_publishers(node.result_publisher),
        }
        
        # Save telemetry settings if available
        if node.telemetry:
            settings['telemetry'] = {
                'enabled': getattr(node.telemetry, 'running', False),
                'publish_interval': getattr(node.telemetry, 'update_interval', 30),
                'mqtt_server': getattr(node.telemetry, 'mqtt_server', ''),
                'mqtt_port': getattr(node.telemetry, 'mqtt_port', 1883),
                'mqtt_topic': getattr(node.telemetry, 'mqtt_topic', 'infernode/telemetry')
            }
        
        with open(node.settings_file, 'w') as f:
            json.dump(settings, f, indent=2)
            
        logger.debug(f"Settings saved to {node.settings_file}")
        
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")


def _serialize_publishers(result_publisher):
    """Serialize result publishers to JSON-compatible format"""
    serialized = []
    
    for dest in result_publisher.destinations:
        dest_data = {
            'id': getattr(dest, '_id', None),
            'type': dest.__class__.__name__.replace('Destination', '').lower(),
            'rate_limit': dest.rate_limit,
            'config': {}
        }
        
        # Extract configuration based on destination type
        # MQTT
        if hasattr(dest, 'server'):
            dest_data['config']['server'] = dest.server
            dest_data['config']['port'] = dest.port
            dest_data['config']['topic'] = dest.topic
            if hasattr(dest, 'username') and dest.username:
                dest_data['config']['username'] = dest.username
            if hasattr(dest, 'password') and dest.password:
                dest_data['config']['password'] = dest.password
            if hasattr(dest, 'include_image_data'):
                dest_data['config']['include_image_data'] = dest.include_image_data
        
        # Webhook
        elif hasattr(dest, 'url'):
            dest_data['config']['url'] = dest.url
            if hasattr(dest, 'timeout'):
                dest_data['config']['timeout'] = dest.timeout
            if hasattr(dest, 'include_image_data'):
                dest_data['config']['include_image_data'] = dest.include_image_data
        
        # Serial
        elif hasattr(dest, 'com_port'):
            dest_data['config']['com_port'] = dest.com_port
            dest_data['config']['baud'] = dest.baud
            if hasattr(dest, 'include_image_data'):
                dest_data['config']['include_image_data'] = dest.include_image_data
        
        # Folder
        elif hasattr(dest, 'folder_path'):
            dest_data['config']['folder_path'] = dest.folder_path
            if hasattr(dest, 'format'):
                dest_data['config']['format'] = dest.format
        
        # Add other destination types as needed
        
        serialized.append(dest_data)
    
    return serialized


def _deserialize_publishers(publishers_data, node):
    """Deserialize and restore result publishers"""
    from ResultPublisher import ResultDestination
    
    for pub_data in publishers_data:
        try:
            dest_type = pub_data['type']
            config = pub_data.get('config', {})
            rate_limit = pub_data.get('rate_limit')
            dest_id = pub_data.get('id')
            
            # Create destination
            destination = ResultDestination(dest_type)
            
            # Set ID if available
            if dest_id:
                destination._id = dest_id
            
            # Set context variables
            destination.set_context_variables(
                node_id=node.node_id,
                node_name=node.node_name
            )
            
            # Configure destination
            destination.configure(**config)
            
            # Set rate limit
            if rate_limit is not None:
                destination.set_rate_limit(rate_limit)
            
            # Add to publisher
            node.result_publisher.add(destination)
            
        except Exception as e:
            logger.warning(f"Failed to restore publisher {pub_data.get('type', 'unknown')}: {e}")
