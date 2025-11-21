"""
Log management API routes for InferenceNode
Handles log retrieval, filtering, and settings
"""

from flask import jsonify, request


def register_log_routes(app, node):
    """Register all log-related routes with the Flask app"""
    
    @app.route('/api/logs', methods=['GET'])
    def get_logs():
        """Get system logs with optional filtering"""
        try:
            if not node.log_manager or not node.log_manager.memory_handler:
                return jsonify({'error': 'Log manager not available'}), 500
            
            # Get query parameters for filtering
            level = request.args.get('level')
            component = request.args.get('component')
            search = request.args.get('search')
            limit = request.args.get('limit', type=int)
            
            # Get filtered logs
            logs = node.log_manager.memory_handler.get_logs(
                level=level,
                component=component,
                search=search,
                limit=limit
            )
            
            # Get statistics
            stats = node.log_manager.memory_handler.get_log_statistics()
            
            return jsonify({
                'success': True,
                'data': {
                    'logs': logs,
                    'stats': stats,
                    'count': len(logs)
                }
            })
            
        except Exception as e:
            node.logger.error(f"Get logs error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/logs/settings', methods=['GET'])
    def get_log_settings():
        """Get current log settings"""
        try:
            if not node.log_manager:
                return jsonify({'error': 'Log manager not available'}), 500
            
            settings = node.log_manager.get_settings()
            return jsonify({
                'success': True,
                'settings': settings
            })
            
        except Exception as e:
            node.logger.error(f"Get log settings error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/logs/settings', methods=['POST'])
    def update_log_settings():
        """Update log settings"""
        try:
            if not node.log_manager:
                return jsonify({'error': 'Log manager not available'}), 500
            
            data = request.get_json()
            success = node.log_manager.update_settings(data)
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Log settings updated successfully'
                })
            else:
                return jsonify({'error': 'Failed to update log settings'}), 500
            
        except Exception as e:
            node.logger.error(f"Update log settings error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/logs/clear', methods=['POST'])
    def clear_logs():
        """Clear all stored logs"""
        try:
            if not node.log_manager or not node.log_manager.memory_handler:
                return jsonify({'error': 'Log manager not available'}), 500
            
            node.log_manager.memory_handler.clear_logs()
            
            return jsonify({
                'success': True,
                'message': 'All logs cleared successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Clear logs error: {str(e)}")
            return jsonify({'error': str(e)}), 500
