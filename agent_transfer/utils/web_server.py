"""Web server for browsing agents with beautiful HTML interface."""

import webbrowser
import threading
import time
import re
from pathlib import Path
from typing import List, Optional, Tuple
import markdown
from pygments.formatters import HtmlFormatter

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
import uvicorn

from ..models import Agent
from .parser import find_all_agents
from .discovery import find_agent_directories

app = FastAPI(title="Agent Transfer Viewer")

# Setup templates - templates are in agent_transfer/templates/
BASE_DIR = Path(__file__).parent.parent  # agent_transfer/
templates_dir = BASE_DIR / "templates"

jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)))


def parse_frontmatter(content: str) -> Tuple[str, str]:
    """Extract YAML frontmatter and markdown body from content.

    Returns:
        Tuple of (frontmatter_text, body_text)
    """
    # Match YAML frontmatter between --- markers
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)

    if match:
        return match.group(1), match.group(2)
    return "", content


def unescape_newlines(text: str) -> str:
    """Convert escaped \\n to actual newlines."""
    # Replace literal \n with actual newlines
    return text.replace('\\n', '\n')


def markdown_to_html(content: str) -> str:
    """Convert markdown to HTML with syntax highlighting."""
    # Parse out frontmatter and get just the body
    frontmatter, body = parse_frontmatter(content)

    # Unescape any literal \n in the body
    body = unescape_newlines(body)

    # Configure markdown extensions
    md = markdown.Markdown(extensions=[
        'fenced_code',
        'codehilite',
        'tables',
        'toc',
        'nl2br',
        'sane_lists'
    ])

    html = md.convert(body)
    
    # Add CSS for code highlighting
    formatter = HtmlFormatter(style='github-dark')
    css = formatter.get_style_defs('.highlight')
    
    return f"""
    <style>
    {css}
    .markdown-body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        font-size: 16px;
        line-height: 1.6;
        color: #24292e;
        max-width: 1012px;
        margin: 0 auto;
        padding: 45px;
    }}
    .markdown-body pre {{
        background-color: #f6f8fa;
        border-radius: 6px;
        padding: 16px;
        overflow: auto;
    }}
    .markdown-body code {{
        background-color: rgba(27,31,35,.05);
        border-radius: 3px;
        font-size: 85%;
        margin: 0;
        padding: .2em .4em;
    }}
    .markdown-body pre code {{
        background-color: transparent;
        padding: 0;
    }}
    .markdown-body table {{
        border-collapse: collapse;
        margin: 15px 0;
    }}
    .markdown-body table th,
    .markdown-body table td {{
        border: 1px solid #dfe2e5;
        padding: 6px 13px;
    }}
    .markdown-body table th {{
        background-color: #f6f8fa;
        font-weight: 600;
    }}
    </style>
    <div class="markdown-body">
    {html}
    </div>
    """


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page with agent list."""
    agents = find_all_agents()
    
    # Group agents by type
    user_agents = [a for a in agents if a.agent_type == "user"]
    project_agents = [a for a in agents if a.agent_type == "project"]
    
    template = jinja_env.get_template("index.html")
    return HTMLResponse(template.render(
        user_agents=user_agents,
        project_agents=project_agents,
        total_agents=len(agents)
    ))


@app.get("/agent/{agent_name}", response_class=HTMLResponse)
async def view_agent(request: Request, agent_name: str):
    """View a specific agent's content."""
    agents = find_all_agents()
    
    # Find the agent
    agent = None
    for a in agents:
        if a.name == agent_name or Path(a.file_path).stem == agent_name:
            agent = a
            break
    
    if not agent:
        return HTMLResponse("<h1>Agent not found</h1>", status_code=404)
    
    # Read and convert markdown
    agent_path = Path(agent.file_path)
    if agent_path.exists():
        content = agent_path.read_text(encoding='utf-8')
        html_content = markdown_to_html(content)
    else:
        html_content = "<p>Agent file not found</p>"
    
    # Get all agents for sidebar
    user_agents = [a for a in agents if a.agent_type == "user"]
    project_agents = [a for a in agents if a.agent_type == "project"]
    
    template = jinja_env.get_template("agent_view.html")
    return HTMLResponse(template.render(
        agent=agent,
        html_content=html_content,
        user_agents=user_agents,
        project_agents=project_agents,
        total_agents=len(agents)
    ))


@app.get("/api/agents")
async def get_agents():
    """API endpoint to get all agents."""
    agents = find_all_agents()
    return {
        "agents": [
            {
                "name": a.name,
                "description": a.description,
                "type": a.agent_type,
                "file_path": a.file_path,
                "tools": a.tools
            }
            for a in agents
        ]
    }


def start_server(host: str = "127.0.0.1", port: int = 7651, open_browser: bool = True):
    """Start the web server."""
    url = f"http://{host}:{port}"
    
    print(f"\n🚀 Starting Agent Transfer Viewer...")
    print(f"📡 Server running at: {url}")
    if open_browser:
        print(f"🌐 Opening browser...")
    print(f"\nPress Ctrl+C to stop the server\n")
    
    if open_browser:
        # Open browser after a short delay
        def open_browser_delayed():
            time.sleep(1.5)
            webbrowser.open(url)
        
        threading.Thread(target=open_browser_delayed, daemon=True).start()
    
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
