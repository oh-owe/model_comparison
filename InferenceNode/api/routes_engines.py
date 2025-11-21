"""
Inference Engine API Routes
Handles inference engine discovery and information
"""
from flask import jsonify


def register_engine_routes(app, node):
    """Register all inference engine-related routes"""
    
    @app.route('/api/inference/engines', methods=['GET'])
    def get_inference_engines():
        """Get available inference engines with their metadata"""
        try:
            from InferenceEngine import InferenceEngineFactory
            engine_types = InferenceEngineFactory.get_available_engines_with_metadata()
            
            return jsonify({
                'status': 'success',
                'engine_types': engine_types
            })
            
        except Exception as e:
            node.logger.error(f"Get inference engines error: {str(e)}")
            return jsonify({'error': str(e)}), 500
