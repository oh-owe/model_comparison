"""
Node discovery API routes for InferenceNode
Handles network discovery and node management
"""

from flask import jsonify, request
from datetime import datetime


def register_discovery_routes(app, node):
    """Register all discovery-related routes with the Flask app"""
    
    @app.route('/api/discovery/nodes', methods=['GET'])
    def get_discovered_nodes():
        """Get all discovered nodes"""
        try:
            if not node.discovery_manager:
                return jsonify({'error': 'Discovery manager not available'}), 503
            
            nodes = node.discovery_manager.get_discovered_nodes()
            return jsonify({
                'nodes': nodes,
                'count': len(nodes),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            node.logger.error(f"Get discovered nodes error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/discovery/nodes/refresh', methods=['POST'])
    def refresh_discovered_nodes():
        """Refresh all discovered nodes"""
        try:
            if not node.discovery_manager:
                return jsonify({'error': 'Discovery manager not available'}), 503
            
            # Trigger refresh of all nodes
            node.discovery_manager.refresh_all_nodes()
            
            # Return updated node list
            nodes = node.discovery_manager.get_discovered_nodes()
            return jsonify({
                'success': True,
                'message': 'Nodes refreshed successfully',
                'nodes': nodes,
                'count': len(nodes),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            node.logger.error(f"Refresh discovered nodes error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/discovery/nodes/<node_id>', methods=['GET'])
    def get_discovered_node(node_id):
        """Get specific discovered node information"""
        try:
            if not node.discovery_manager:
                return jsonify({'error': 'Discovery manager not available'}), 503
            
            discovered_node = node.discovery_manager.get_node(node_id)
            if not discovered_node:
                return jsonify({'error': 'Node not found'}), 404
            
            return jsonify(discovered_node)
        except Exception as e:
            node.logger.error(f"Get discovered node error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/discovery/nodes/<node_id>/control', methods=['POST'])
    def control_discovered_node(node_id):
        """Control discovered node operations"""
        try:
            if not node.discovery_manager:
                return jsonify({'error': 'Discovery manager not available'}), 503
            
            data = request.get_json()
            action = data.get('action')
            
            if not action:
                return jsonify({'error': 'Action required'}), 400
            
            result = node.discovery_manager.control_node(node_id, action)
            
            if 'error' in result:
                return jsonify(result), 400
            
            return jsonify(result)
        except Exception as e:
            node.logger.error(f"Control discovered node error: {str(e)}")
            return jsonify({'error': str(e)}), 500
