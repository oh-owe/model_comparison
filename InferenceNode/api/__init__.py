"""
API module for InferenceNode
Handles route registration for all API endpoints
"""

def register_routes(app, node):
    """Register all API routes with the Flask app"""
    from .routes_models import register_model_routes
    from .routes_web import register_web_routes
    from .routes_publisher import register_publisher_routes
    from .routes_pipelines import register_pipeline_routes
    from .routes_telemetry import register_telemetry_routes
    from .routes_hardware import register_hardware_routes
    from .routes_logs import register_log_routes
    from .routes_node import register_node_routes
    from .routes_discovery import register_discovery_routes
    from .routes_frame_sources import register_frame_source_routes
    from .routes_engines import register_engine_routes
    
    # Register web page routes
    register_web_routes(app, node)
    
    # Register API routes
    register_model_routes(app, node)
    register_publisher_routes(app, node)
    register_pipeline_routes(app, node)
    register_telemetry_routes(app, node)
    register_hardware_routes(app, node)
    register_log_routes(app, node)
    register_node_routes(app, node)
    register_discovery_routes(app, node)
    register_frame_source_routes(app, node)
    register_engine_routes(app, node)
    
    # Health check endpoint
    from flask import jsonify
    from datetime import datetime
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint for Docker and monitoring"""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': node.node_info.get('version', getattr(node, '__version__', '0.1.0'))
        })
    
    @app.route('/api/info', methods=['GET'])
    def get_node_info():
        """Get node information and capabilities"""
        return jsonify(node.node_info)
