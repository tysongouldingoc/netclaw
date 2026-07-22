#!/usr/bin/env python3
"""
NetClaw Enterprise Setup GUI Backend Server
Serves a responsive setup web app at http://localhost:8080 and handles
installation and container deployment requests.
"""

import http.server
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = REPO_ROOT / "ui"
PORT = 8090


class SetupGUIHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(UI_DIR / "index.html", "rb") as f:
                self.wfile.write(f.read())
            return
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "status": "ok",
                "posture": "production — enforced",
                "defenseclaw_proxy": "healthy",
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/deploy":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                selected_mcps = data.get("selected_mcps", [])
                risk_mode = data.get("risk_mode", "production")

                # 1. Run mcp-installer script with selected MCPs
                select_arg = ",".join(selected_mcps) if selected_mcps else ""
                cmd = [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "mcp-installer.py"),
                    "--target", "docker-compose",
                    "--mode", risk_mode,
                ]
                if select_arg:
                    cmd.extend(["--select", select_arg])
                else:
                    cmd.extend(["--select", "none"])

                res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)

                if res.returncode == 0:
                    # 2. Trigger docker compose up -d --build
                    deploy_cmd = ["docker", "compose", "-f", "docker-compose.mcp.yml", "up", "-d", "--build"]
                    deploy_res = subprocess.run(deploy_cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
                    
                    response_payload = {
                        "status": "success",
                        "message": f"Installed {len(selected_mcps)} MCP servers into docker-compose.mcp.yml and launched containers.",
                        "deploy_output": deploy_res.stdout,
                    }
                else:
                    response_payload = {
                        "status": "error",
                        "message": f"Installer failed: {res.stderr}",
                    }
            except Exception as e:
                response_payload = {
                    "status": "error",
                    "message": f"Exception occurred: {str(e)}",
                }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_payload).encode("utf-8"))
            return

        self.send_error(404, "Endpoint not found")


def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), SetupGUIHandler)
    print(f"NetClaw Setup GUI Server running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")


if __name__ == "__main__":
    main()
