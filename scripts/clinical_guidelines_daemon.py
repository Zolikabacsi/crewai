#!/usr/bin/env python3
"""
Clinical Guidelines Daemon
Listens on AgentBus as 'ClinicalGuidelines' and handles clinical question requests.
"""

import sys
import os
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# Setup sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
CREWAI_ROOT = SCRIPT_DIR.parent.parent  # ~/srv/crewai
sys.path.insert(0, str(CREWAI_ROOT))
sys.path.insert(0, str(CREWAI_ROOT / 'src'))

from src.config import Config
from src.bus import AgentBus
from src.prompts import CLINICAL_PROMPT_PATH

# Constants
VAULT_ROOT = Path('/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO')
LOG_PATH = Path('/home/zoltan/logs/clinical_guidelines_daemon.log')
CLAUDE_CODE_BIN = Path.home() / '.local' / 'bin' / 'claude'

# Ensure directories exist
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
VAULT_ROOT.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ClinicalGuidelinesDaemon')


def load_clinical_prompt() -> str:
    """Load the clinical prompt template."""
    try:
        with open(CLINICAL_PROMPT_PATH, 'r') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load clinical prompt: {e}")
        return ""


def call_claude_code(prompt: str, timeout: int = 180) -> str:
    """Call Claude Code subprocess and return the result."""
    env = {
        'ANTHROPIC_API_KEY': Config.ANTHROPIC_AUTH_TOKEN,
        'ANTHROPIC_BASE_URL': 'https://chat.ultimateai.org'
    }
    
    try:
        result = subprocess.run(
            [str(CLAUDE_CODE_BIN), '-p', '--model', 'MiniMax-M2.7', '--output-format', 'json'],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **env}
        )
        
        if result.returncode != 0:
            logger.error(f"Claude Code error: {result.stderr}")
            return f"Error: {result.stderr}"
        
        # Parse JSON output
        try:
            output = json.loads(result.stdout)
            return output.get('result', result.stdout)
        except json.JSONDecodeError:
            logger.warning("Claude Code output was not valid JSON, returning raw output")
            return result.stdout
            
    except subprocess.TimeoutExpired:
        logger.error("Claude Code call timed out")
        return "Error: Request timed out"
    except Exception as e:
        logger.error(f"Claude Code call failed: {e}")
        return f"Error: {e}"


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from text."""
    lines = text.split('\n')
    # Remove first line if it's a markdown code fence
    if lines and lines[0].strip().startswith('```'):
        lines = lines[1:]
    # Remove last line if it's a markdown code fence
    if lines and lines[-1].strip() == '```':
        lines = lines[:-1]
    return '\n'.join(lines).strip()


def save_to_vault(content: str, date_str: str = None) -> Path:
    """Save content to vault with YAML frontmatter."""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    
    # Find unique filename
    vault_dir = VAULT_ROOT / 'guidelines'
    vault_dir.mkdir(parents=True, exist_ok=True)
    
    counter = 1
    while True:
        filename = f"{date_str}_task"
        if counter > 1:
            filename = f"{date_str}_task_{counter}"
        path = vault_dir / f"{filename}.md"
        if not path.exists():
            break
        counter += 1
    
    # Create content with YAML frontmatter
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    frontmatter = f"""---
date: {timestamp}
agent: ClinicalGuidelines
type: clinical_guidelines
---

"""
    full_content = frontmatter + content
    
    with open(path, 'w') as f:
        f.write(full_content)
    
    logger.info(f"Saved guidelines to {path}")
    return path


def handle_clinical_request(task: str, from_agent: str, bus: AgentBus):
    """Handle a clinical request."""
    logger.info(f"Received clinical request from {from_agent}: {task[:100]}...")
    
    # Load prompt template
    prompt_template = load_clinical_prompt()
    
    # Build full prompt
    full_prompt = f"You are ClinicalGuidelines for Aestas Healthcare.\n\n{prompt_template}\n\nQUESTION: {task}\n\nProvide clinical guidelines analysis."
    
    # Call Claude Code
    raw_result = call_claude_code(full_prompt)
    
    # Strip markdown fences
    result = strip_markdown_fences(raw_result)
    
    # Save to vault
    vault_path = save_to_vault(result)
    
    # Send response back
    response_data = {
        'result': result,
        'vault_path': str(vault_path)
    }
    bus.send(to=from_agent, action='clinical_result', data=response_data)
    logger.info(f"Sent clinical result to {from_agent}")


def handle_ping(from_agent: str, bus: AgentBus):
    """Handle a ping request."""
    logger.info(f"Received ping from {from_agent}")
    bus.send(to=from_agent, action='pong', data={'status': 'alive'})
    logger.info(f"Sent pong to {from_agent}")


def main():
    """Main daemon loop."""
    logger.info("Starting Clinical Guidelines Daemon...")
    
    bus = AgentBus()
    logger.info(f"Connected to AgentBus as 'ClinicalGuidelines'")
    
    while True:
        try:
            message = bus.recv(agent_name='ClinicalGuidelines', timeout=300)
            
            if message is None:
                logger.debug("No message received, continuing to wait...")
                continue
            
            action = message.get('action')
            from_agent = message.get('from_agent', 'unknown')
            data = message.get('data', {})
            
            logger.info(f"Received message from {from_agent}: action={action}")
            
            if action == 'clinical_request':
                task = data if isinstance(data, str) else data.get('task', '')
                handle_clinical_request(task, from_agent, bus)
            elif action == 'ping':
                handle_ping(from_agent, bus)
            else:
                logger.warning(f"Unknown action: {action}")
                
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            continue
    
    logger.info("Clinical Guidelines Daemon stopped")


if __name__ == '__main__':
    main()
