"""
Web page routes for InferenceNode dashboard and UI pages
"""
from flask import render_template


def register_web_routes(app, node):
    """Register all web UI page routes"""
    
    @app.route('/')
    def dashboard():
        """Main dashboard page"""
        return render_template('dashboard.html', node_info=node.node_info)
    
    @app.route('/models')
    def models_page():
        """Model management page"""
        return render_template('models.html', node_info=node.node_info)
    
    @app.route('/pipeline-builder')
    def pipeline_page():
        """Pipeline builder page"""
        return render_template('pipeline_builder.html', node_info=node.node_info)
    
    @app.route('/pipeline-management')
    def pipeline_management_page():
        """Pipeline management page"""
        return render_template('pipeline_management.html', node_info=node.node_info)
    
    @app.route('/publisher')
    def publisher_page():
        """Result publisher configuration page"""
        return render_template('publisher.html', node_info=node.node_info)
    
    @app.route('/telemetry')
    def telemetry_page():
        """Telemetry monitoring page"""
        return render_template('telemetry.html', node_info=node.node_info)
    
    @app.route('/api-docs')
    def api_docs():
        """API documentation page"""
        return render_template('api_docs.html', node_info=node.node_info)
    
    @app.route('/node-info')
    def node_info_page():
        """Detailed node information page"""
        return render_template('node_info.html', node_info=node.node_info)
    
    @app.route('/logs')
    def logs_page():
        """System logs page"""
        return render_template('logs.html', node_info=node.node_info)
    
    @app.route('/node-discovery')
    def node_discovery_page():
        """Node discovery page"""
        return render_template('node_discovery.html', node_info=node.node_info)
