"""
Publisher API Routes
Handles result publisher configuration and management
"""
import uuid
from datetime import datetime
from flask import request, jsonify
from ResultPublisher import ResultDestination, get_available_destination_types

try:
    from ..settings_manager import save_settings
except ImportError:
    from InferenceNode.settings_manager import save_settings


def register_publisher_routes(app, node):
    """Register all publisher-related routes"""
    
    @app.route('/api/publisher/configure', methods=['POST'])
    def configure_publisher():
        """Configure result publisher destinations"""
        try:
            data = request.get_json()
            destination_type = data.get('type')
            config = data.get('config', {})
            
            # Extract rate_limit from config if present
            rate_limit = config.pop('rate_limit', None)
            
            destination = ResultDestination(destination_type)
            
            # Set context variables for variable substitution
            destination.set_context_variables(
                node_id=node.node_id,
                node_name=node.node_name
            )
            
            # Configure destination with error handling
            try:
                destination.configure(**config)
            except Exception as config_error:
                node.logger.error(f"Failed to configure {destination_type} destination: {str(config_error)}")
                return jsonify({
                    'error': f'Configuration failed: {str(config_error)}',
                    'type': destination_type
                }), 400
            
            # Only proceed if configuration succeeded
            if not destination.is_configured:
                return jsonify({
                    'error': f'{destination_type} destination configuration failed - check logs for details',
                    'type': destination_type
                }), 400
            
            # Set rate limit if provided
            if rate_limit is not None:
                destination.set_rate_limit(rate_limit)
            
            publisher_id = node.result_publisher.add(destination)
            
            # Save settings after adding publisher
            save_settings(node)
            
            return jsonify({
                'status': 'configured', 
                'type': destination_type,
                'id': publisher_id
            })
            
        except Exception as e:
            node.logger.error(f"Publisher configuration error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/test', methods=['POST'])
    def test_publish():
        """Test publishing a message to all configured destinations"""
        try:
            data = request.get_json()
            message = data.get('message', {})
            
            if not message:
                return jsonify({'error': 'No message provided'}), 400
            
            # Check if any destinations are configured
            if not node.result_publisher.destinations:
                return jsonify({
                    'status': 'warning',
                    'message': 'No destinations configured - cannot publish test message',
                    'results': {},
                    'destinations_count': 0
                })
            
            # Add metadata to the test message
            test_message = {
                'test': True,
                'node_id': node.node_id,
                'node_name': node.node_name,
                'timestamp': data.get('timestamp') or message.get('timestamp'),
                'data': message
            }
            
            # Publish to all configured destinations
            results = node.result_publisher.publish(test_message)
            
            return jsonify({
                'status': 'success',
                'message': 'Test message published',
                'results': results,
                'destinations_count': len(node.result_publisher.destinations)
            })
            
        except Exception as e:
            node.logger.error(f"Test publish error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/test-favorites', methods=['POST'])
    def test_publish_favorites():
        """Test publishing a message to selected favorite destinations"""
        try:
            data = request.get_json()
            message = data.get('message', {})
            favorite_ids = data.get('favorite_ids', [])
            
            if not message:
                return jsonify({'error': 'No message provided'}), 400
            
            if not favorite_ids:
                return jsonify({'error': 'No favorite destinations selected'}), 400
            
            # Get selected favorites
            selected_favorites = []
            for fav_id in favorite_ids:
                if fav_id in node.favorite_configs:
                    selected_favorites.append(node.favorite_configs[fav_id])
            
            if not selected_favorites:
                return jsonify({
                    'status': 'warning',
                    'message': 'No valid favorite destinations found',
                    'destinations_count': 0
                })
            
            # Add metadata to the test message
            test_message = {
                'test': True,
                'node_id': node.node_id,
                'node_name': node.node_name,
                'timestamp': data.get('timestamp') or message.get('timestamp'),
                'data': message
            }
            
            # Create temporary destinations from favorites and publish
            temp_destinations = []
            for favorite in selected_favorites:
                try:
                    destination = ResultDestination(favorite['type'])
                    destination.set_context_variables(
                        node_id=node.node_id,
                        node_name=node.node_name
                    )
                    destination.configure(**favorite['config'])
                    temp_destinations.append(destination)
                except Exception as e:
                    node.logger.error(f"Failed to create destination for favorite {favorite.get('name', 'unknown')}: {str(e)}")
            
            # Publish using temporary destinations
            results = {}
            for dest in temp_destinations:
                try:
                    result = dest.publish(test_message)
                    results[dest.__class__.__name__] = result
                except Exception as e:
                    results[dest.__class__.__name__] = {'error': str(e)}
            
            return jsonify({
                'status': 'success',
                'message': f'Test message sent to {len(temp_destinations)} favorite destination(s)',
                'results': results,
                'destinations_count': len(temp_destinations)
            })
            
        except Exception as e:
            node.logger.error(f"Test publish favorites error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/edit/<publisher_id>', methods=['PUT'])
    def edit_publisher(publisher_id):
        """Edit a specific publisher by ID"""
        try:
            data = request.get_json()
            config = data.get('config', {})
            
            # Find the publisher by ID
            destination = node.result_publisher.get_by_id(publisher_id)
            if not destination:
                return jsonify({'error': 'Publisher not found'}), 404
            
            # Extract rate_limit from config if present
            rate_limit = config.pop('rate_limit', None)
            
            # Clean up config - remove null values and empty strings
            cleaned_config = {}
            for key, value in config.items():
                if value is not None and value != '':
                    cleaned_config[key] = value
            
            # Set context variables for variable substitution
            destination.set_context_variables(
                node_id=node.node_id,
                node_name=node.node_name
            )
            
            # Reconfigure the destination
            destination.configure(**cleaned_config)
            
            # Set rate limit if provided
            if rate_limit is not None:
                destination.set_rate_limit(rate_limit)
            
            # Save settings after editing publisher
            save_settings(node)
            
            return jsonify({
                'status': 'updated',
                'id': publisher_id,
                'message': 'Publisher configuration updated'
            })
            
        except Exception as e:
            node.logger.error(f"Edit publisher error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/delete/<publisher_id>', methods=['DELETE'])
    def delete_publisher(publisher_id):
        """Delete a specific publisher by ID"""
        try:
            success = node.result_publisher.remove_by_id(publisher_id)
            if not success:
                return jsonify({'error': 'Publisher not found'}), 404
            
            # Save settings after deleting publisher
            save_settings(node)
            
            return jsonify({
                'status': 'deleted',
                'id': publisher_id,
                'message': 'Publisher removed successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Delete publisher error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/favorites', methods=['GET'])
    def get_favorite_configs():
        """Get all saved favorite publisher configurations"""
        try:
            return jsonify({
                'status': 'success',
                'favorites': list(node.favorite_configs.values())
            })
            
        except Exception as e:
            node.logger.error(f"Get favorites error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/favorites', methods=['POST'])
    def save_favorite_config():
        """Save a publisher configuration as a favorite"""
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            description = data.get('description', '').strip()
            destination_type = data.get('type')
            config = data.get('config', {})
            
            if not name:
                return jsonify({'error': 'Name is required'}), 400
            
            if not destination_type:
                return jsonify({'error': 'Destination type is required'}), 400
            
            # Generate unique ID for the favorite
            favorite_id = str(uuid.uuid4())
            
            # Create favorite configuration
            favorite = {
                'id': favorite_id,
                'name': name,
                'description': description,
                'type': destination_type,
                'config': config,
                'created_at': datetime.now().isoformat()
            }
            
            # Check if a favorite with this name already exists
            for existing_fav in node.favorite_configs.values():
                if existing_fav['name'].lower() == name.lower():
                    return jsonify({'error': f'A favorite named "{name}" already exists'}), 400
            
            # Save the favorite
            node.favorite_configs[favorite_id] = favorite
            
            # Save to file
            save_settings(node)
            
            return jsonify({
                'status': 'saved',
                'favorite': favorite,
                'message': f'Configuration saved as favorite: {name}'
            })
            
        except Exception as e:
            node.logger.error(f"Save favorite error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/favorites/<favorite_id>', methods=['DELETE'])
    def delete_favorite_config(favorite_id):
        """Delete a favorite configuration"""
        try:
            if favorite_id not in node.favorite_configs:
                return jsonify({'error': 'Favorite not found'}), 404
            
            favorite_name = node.favorite_configs[favorite_id]['name']
            del node.favorite_configs[favorite_id]
            
            # Save to file
            save_settings(node)
            
            return jsonify({
                'status': 'deleted',
                'id': favorite_id,
                'message': f'Favorite "{favorite_name}" deleted successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Delete favorite error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/favorites/<favorite_id>', methods=['PUT'])
    def update_favorite_config(favorite_id):
        """Update a favorite configuration"""
        try:
            if favorite_id not in node.favorite_configs:
                return jsonify({'error': 'Favorite not found'}), 404
            
            data = request.get_json()
            favorite = node.favorite_configs[favorite_id]
            
            # Update fields if provided
            if 'name' in data:
                new_name = data['name'].strip()
                if not new_name:
                    return jsonify({'error': 'Name cannot be empty'}), 400
                
                # Check if another favorite has this name
                for fav_id, existing_fav in node.favorite_configs.items():
                    if fav_id != favorite_id and existing_fav['name'].lower() == new_name.lower():
                        return jsonify({'error': f'A favorite named "{new_name}" already exists'}), 400
                
                favorite['name'] = new_name
            
            if 'description' in data:
                favorite['description'] = data['description'].strip()
            
            if 'config' in data:
                favorite['config'] = data['config']
            
            favorite['updated_at'] = datetime.now().isoformat()
            
            # Save to file
            save_settings(node)
            
            return jsonify({
                'status': 'updated',
                'favorite': favorite,
                'message': f'Favorite "{favorite["name"]}" updated successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Update favorite error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/types', methods=['GET'])
    def get_publisher_types():
        """Get available publisher/destination types"""
        try:
            destination_types = get_available_destination_types()
            
            return jsonify({
                'status': 'success',
                'destination_types': destination_types
            })
            
        except Exception as e:
            node.logger.error(f"Get publisher types error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/publisher/destination-types', methods=['GET'])
    def get_destination_types_with_schemas():
        """Get available destination types with their configuration schemas"""
        try:
            destination_types = get_available_destination_types()
            
            return jsonify({
                'status': 'success',
                'destination_types': destination_types
            })
            
        except Exception as e:
            node.logger.error(f"Get destination types with schemas error: {str(e)}")
            return jsonify({'error': str(e)}), 500
