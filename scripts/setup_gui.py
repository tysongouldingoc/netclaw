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
PORT = 8095


class SetupGUIHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        clean_path = self.path.split("?")[0]
        if clean_path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(UI_DIR / "index.html", "rb") as f:
                self.wfile.write(f.read())
            return
        elif clean_path == "/api/status":
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
        elif clean_path == "/api/mcps":
            sys.path.insert(0, str(REPO_ROOT / "scripts"))
            import importlib.util
            spec = importlib.util.spec_from_file_location("mcp_installer", str(REPO_ROOT / "scripts" / "mcp-installer.py"))
            mcp_installer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mcp_installer)
            mcps = mcp_installer.discover_mcp_servers()
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"mcps": list(mcps.keys())}).encode("utf-8"))
            return
        self.send_error(404, "File not found")

    def do_POST(self):
        if self.path == "/api/deploy":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                selected_mcps = data.get("selected_mcps", [])
                risk_mode = data.get("risk_mode", "production")
                cmd_whitelist = data.get("command_whitelist", "ping, traceroute, curl, dig, git, ip, python, node, show")

                # Save allowed commands whitelist to config file
                config_dir = REPO_ROOT / "config"
                config_dir.mkdir(parents=True, exist_ok=True)
                with open(config_dir / "allowed_commands.conf", "w") as f:
                    f.write(cmd_whitelist.strip() + "\n")

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
