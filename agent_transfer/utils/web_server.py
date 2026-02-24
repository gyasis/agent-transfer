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

from ..models import Agent, Skill
from .parser import find_all_agents
from .skill_parser import find_all_skills
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
    
    # Add CSS for code highlighting - use 'friendly' style for light backgrounds
    formatter = HtmlFormatter(style='friendly')
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
        border: 1px solid #e1e4e8;
    }}
    .markdown-body code {{
        background-color: #eff1f3;
        border-radius: 3px;
        font-size: 85%;
        margin: 0;
        padding: .2em .4em;
        color: #24292e;
        font-weight: 500;
    }}
    .markdown-body pre code {{
        background-color: transparent;
        padding: 0;
        color: inherit;
        font-weight: normal;
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
    """Main page with agent and skill list."""
    agents = find_all_agents()
    skills = find_all_skills()

    # Group agents by type
    user_agents = [a for a in agents if a.agent_type == "user"]
    project_agents = [a for a in agents if a.agent_type == "project"]

    # Group skills by type
    user_skills = [s for s in skills if s.skill_type == "user"]
    project_skills = [s for s in skills if s.skill_type == "project"]

    template = jinja_env.get_template("index.html")
    return HTMLResponse(template.render(
        user_agents=user_agents,
        project_agents=project_agents,
        total_agents=len(agents),
        user_skills=user_skills,
        project_skills=project_skills,
        total_skills=len(skills)
    ))


@app.get("/agent/{agent_name}", response_class=HTMLResponse)
async def view_agent(request: Request, agent_name: str):
    """View a specific agent's content."""
    agents = find_all_agents()
    skills = find_all_skills()

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

    # Get all agents and skills for sidebar
    user_agents = [a for a in agents if a.agent_type == "user"]
    project_agents = [a for a in agents if a.agent_type == "project"]
    user_skills = [s for s in skills if s.skill_type == "user"]
    project_skills = [s for s in skills if s.skill_type == "project"]

    template = jinja_env.get_template("agent_view.html")
    return HTMLResponse(template.render(
        agent=agent,
        html_content=html_content,
        user_agents=user_agents,
        project_agents=project_agents,
        total_agents=len(agents),
        user_skills=user_skills,
        project_skills=project_skills,
        total_skills=len(skills)
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


@app.get("/skill/{skill_name}", response_class=HTMLResponse)
async def view_skill(request: Request, skill_name: str):
    """View a specific skill's content."""
    agents = find_all_agents()
    skills = find_all_skills()

    # Find the skill
    skill = None
    for s in skills:
        if s.name == skill_name or Path(s.skill_path).name == skill_name:
            skill = s
            break

    if not skill:
        return HTMLResponse("<h1>Skill not found</h1>", status_code=404)

    # Convert skill markdown content to HTML
    if skill.skill_md_content:
        html_content = markdown_to_html(skill.skill_md_content)
    else:
        html_content = "<p>Skill file content not available</p>"

    # Get all agents and skills for sidebar
    user_agents = [a for a in agents if a.agent_type == "user"]
    project_agents = [a for a in agents if a.agent_type == "project"]
    user_skills = [s for s in skills if s.skill_type == "user"]
    project_skills = [s for s in skills if s.skill_type == "project"]

    template = jinja_env.get_template("skill_view.html")
    return HTMLResponse(template.render(
        skill=skill,
        html_content=html_content,
        user_agents=user_agents,
        project_agents=project_agents,
        total_agents=len(agents),
        user_skills=user_skills,
        project_skills=project_skills,
        total_skills=len(skills)
    ))


@app.get("/api/skills")
async def get_skills():
    """API endpoint to get all skills."""
    skills = find_all_skills()
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "type": s.skill_type,
                "skill_path": s.skill_path,
                "allowed_tools": s.allowed_tools,
                "model": s.model,
                "file_count": s.file_count,
                "has_scripts": s.has_scripts,
                "has_requirements_txt": s.has_requirements_txt,
                "has_pyproject_toml": s.has_pyproject_toml
            }
            for s in skills
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
