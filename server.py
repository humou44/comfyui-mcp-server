"""ComfyUI MCP Server - Main entry point"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from comfyui_client import ComfyUIClient
from managers.asset_registry import AssetRegistry
from managers.defaults_manager import DefaultsManager
from managers.workflow_manager import WorkflowManager
from tools.asset import register_asset_tools
from tools.configuration import register_configuration_tools
from tools.generation import register_workflow_generation_tools, register_regenerate_tool
from tools.job import register_job_tools
from tools.workflow import register_workflow_tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCP_Server")

# Configuration paths
WORKFLOW_DIR = Path(os.getenv("COMFY_MCP_WORKFLOW_DIR", str(Path(__file__).parent / "workflows")))

# Asset registry configuration
ASSET_TTL_HOURS = int(os.getenv("COMFY_MCP_ASSET_TTL_HOURS", "24"))

# Global ComfyUI client (fallback since context isn't available)
comfyui_url = os.getenv("COMFYUI_URL", "http://localhost:8188")
comfyui_client = ComfyUIClient(comfyui_url)
workflow_manager = WorkflowManager(WORKFLOW_DIR)
defaults_manager = DefaultsManager(comfyui_client)
asset_registry = AssetRegistry(ttl_hours=ASSET_TTL_HOURS, comfyui_base_url=comfyui_url)


# Define application context (for future use)
class AppContext:
    def __init__(self, comfyui_client: ComfyUIClient):
        self.comfyui_client = comfyui_client


# Lifespan management (placeholder for future context support)
@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle"""
    logger.info("Starting MCP server lifecycle...")
    try:
        # Startup: Could add ComfyUI health check here in the future
        logger.info("ComfyUI client initialized globally")
        yield AppContext(comfyui_client=comfyui_client)
    finally:
        # Shutdown: Cleanup (if needed)
        logger.info("Shutting down MCP server")


# Initialize FastMCP with lifespan and port configuration
# Using port 9000 for consistency with previous version
# Enable stateless_http to avoid requiring session management
mcp = FastMCP(
    "ComfyUI_MCP_Server",
    lifespan=app_lifespan,
    port=9000,
    stateless_http=True
)

# Register all MCP tools
register_configuration_tools(mcp, comfyui_client, defaults_manager)
register_workflow_tools(mcp, workflow_manager, comfyui_client, defaults_manager, asset_registry)
register_asset_tools(mcp, asset_registry)
register_workflow_generation_tools(mcp, workflow_manager, comfyui_client, defaults_manager, asset_registry)
register_regenerate_tool(mcp, comfyui_client, asset_registry)
register_job_tools(mcp, comfyui_client, asset_registry)

if __name__ == "__main__":
    # Check if running as MCP command (stdio) or standalone (streamable-http)
    # When run as command by MCP client (like Cursor), use stdio transport
    # When run standalone, use streamable-http for HTTP access
    if len(sys.argv) > 1 and sys.argv[1] == "--stdio":
        logger.info("Starting MCP server with stdio transport (for MCP clients)")
        mcp.run(transport="stdio")
    else:
        logger.info("Starting MCP server with streamable-http transport on http://127.0.0.1:9000/mcp")
        mcp.run(transport="streamable-http")
