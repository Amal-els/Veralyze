import http.server
import socketserver
import webbrowser
import threading
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class VizServer:
    def __init__(self, tree_data: dict, port: int = 8080):
        self.tree_data = tree_data
        self.port = port
        self.viz_dir = Path(__file__).parent / "visualizer"
        self.server = None

    def start(self):
        # Write data.json to the visualizer directory for the frontend to fetch
        data_path = self.viz_dir / "data.json"
        
        # Transform tree_dict to 3d-force-graph format
        graph_data = {
            "nodes": [],
            "links": []
        }
        
        nodes = self.tree_data.get("nodes", {})
        for node_id, node_data in nodes.items():
            graph_data["nodes"].append({
                "id": str(node_id),
                "label": str(node_data.get("author_id", "unknown")),
                "text": str(node_data.get("text", "")),
                "type": str(node_data.get("edge_type", "root")),
                "score": float(node_data.get("bot_score", {}).get("aggregate", 0.0)) if isinstance(node_data.get("bot_score"), dict) else 0.0
            })
            
        for edge in self.tree_data.get("edges", []):
            graph_data["links"].append({
                "source": str(edge["parent"]),
                "target": str(edge["child"])
            })
            
        with open(data_path, "w") as f:
            json.dump(graph_data, f)

        # Start server
        os.chdir(self.viz_dir)
        handler = http.server.SimpleHTTPRequestHandler
        
        # Try to find an available port if 8080 is taken
        while True:
            try:
                self.server = socketserver.TCPServer(("", self.port), handler)
                break
            except OSError:
                self.port += 1

        print(f"\n  🛡️  Trust Graph Visualizer active at http://localhost:{self.port}")
        print(f"  💡  Close the browser tab or press Ctrl+C in this terminal to stop.")
        
        url = f"http://localhost:{self.port}"
        webbrowser.open(url)
        
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            self.server.shutdown()
            print("\n  Viz server stopped.")

def launch_interactive_viz(tree_data: dict):
    viz = VizServer(tree_data)
    viz.start()
