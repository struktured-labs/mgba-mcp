"""MCP server for mGBA emulator control."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

from .emulator import MGBAEmulator

# Initialize MCP server
server = Server("mgba-mcp")

# Global emulator instance
_emulator: MGBAEmulator | None = None


def get_emulator() -> MGBAEmulator:
    """Get or create the emulator instance."""
    global _emulator
    if _emulator is None:
        _emulator = MGBAEmulator()
    return _emulator


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="mgba_run",
            description="Run a GB/GBC/GBA ROM for a specified number of frames and capture a screenshot",
            inputSchema={
                "type": "object",
                "properties": {
                    "rom_path": {
                        "type": "string",
                        "description": "Path to the ROM file (.gb, .gbc, .gba)",
                    },
                    "frames": {
                        "type": "integer",
                        "description": "Number of frames to run (default: 60)",
                        "default": 60,
                    },
                    "savestate_path": {
                        "type": "string",
                        "description": "Optional path to a savestate file to load",
                    },
                },
                "required": ["rom_path"],
            },
        ),
        Tool(
            name="mgba_read_memory",
            description="Read memory at specified addresses after running for some frames",
            inputSchema={
                "type": "object",
                "properties": {
                    "rom_path": {
                        "type": "string",
                        "description": "Path to the ROM file",
                    },
                    "addresses": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of memory addresses to read (as integers, e.g., [0xC200, 0xFFBF])",
                    },
                    "savestate_path": {
                        "type": "string",
                        "description": "Optional savestate to load",
                    },
                    "frames": {
                        "type": "integer",
                        "description": "Frames to run before reading (default: 60)",
                        "default": 60,
                    },
                },
                "required": ["rom_path", "addresses"],
            },
        ),
        Tool(
            name="mgba_read_range",
            description="Read a contiguous range of memory addresses",
            inputSchema={
                "type": "object",
                "properties": {
                    "rom_path": {
                        "type": "string",
                        "description": "Path to the ROM file",
                    },
                    "start_address": {
                        "type": "integer",
                        "description": "Starting memory address",
                    },
                    "length": {
                        "type": "integer",
                        "description": "Number of bytes to read",
                    },
                    "savestate_path": {
                        "type": "string",
                        "description": "Optional savestate to load",
                    },
                    "frames": {
                        "type": "integer",
                        "description": "Frames to run before reading (default: 60)",
                        "default": 60,
                    },
                },
                "required": ["rom_path", "start_address", "length"],
            },
        ),
        Tool(
            name="mgba_dump_oam",
            description="Dump OAM (Object Attribute Memory) sprite data - shows all 40 sprites with position, tile, flags, and palette",
            inputSchema={
                "type": "object",
                "properties": {
                    "rom_path": {
                        "type": "string",
                        "description": "Path to the ROM file",
                    },
                    "savestate_path": {
                        "type": "string",
                        "description": "Optional savestate to load",
                    },
                    "frames": {
                        "type": "integer",
                        "description": "Frames to run before dumping (default: 60)",
                        "default": 60,
                    },
                },
                "required": ["rom_path"],
            },
        ),
        Tool(
            name="mgba_dump_entities",
            description="Dump entity/actor data from WRAM - useful for analyzing game objects",
            inputSchema={
                "type": "object",
                "properties": {
                    "rom_path": {
                        "type": "string",
                        "description": "Path to the ROM file",
                    },
                    "entity_base": {
                        "type": "integer",
                        "description": "Base address of entity array (default: 0xC200)",
                        "default": 49664,
                    },
                    "entity_size": {
                        "type": "integer",
                        "description": "Size of each entity in bytes (default: 24)",
                        "default": 24,
                    },
                    "entity_count": {
                        "type": "integer",
                        "description": "Number of entities to dump (default: 10)",
                        "default": 10,
                    },
                    "savestate_path": {
                        "type": "string",
                        "description": "Optional savestate to load",
                    },
                    "frames": {
                        "type": "integer",
                        "description": "Frames to run before dumping (default: 60)",
                        "default": 60,
                    },
                },
                "required": ["rom_path"],
            },
        ),
        Tool(
            name="mgba_run_lua",
            description="Run a custom Lua script in the emulator. The script can use emu:read8(), emu:write8(), emu:screenshot(), callbacks:add(), etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "rom_path": {
                        "type": "string",
                        "description": "Path to the ROM file",
                    },
                    "script": {
                        "type": "string",
                        "description": "Lua script to execute. Use emu:quit() to exit. Write JSON to 'output.json' for structured data.",
                    },
                    "savestate_path": {
                        "type": "string",
                        "description": "Optional savestate to load",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["rom_path", "script"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent]:
    """Handle tool calls."""
    emu = get_emulator()
    result_content: list[TextContent | ImageContent] = []

    if name == "mgba_run":
        result = emu.run_frames(
            rom_path=arguments["rom_path"],
            frames=arguments.get("frames", 60),
            savestate_path=arguments.get("savestate_path"),
            screenshot=True,
        )

        if result.success:
            result_content.append(TextContent(type="text", text="Emulator ran successfully"))
            if result.screenshot:
                result_content.append(ImageContent(
                    type="image",
                    data=base64.b64encode(result.screenshot).decode(),
                    mimeType="image/png",
                ))
        else:
            result_content.append(TextContent(type="text", text=f"Error: {result.error}"))

    elif name == "mgba_read_memory":
        result = emu.read_memory(
            rom_path=arguments["rom_path"],
            addresses=arguments["addresses"],
            savestate_path=arguments.get("savestate_path"),
            frames_before_read=arguments.get("frames", 60),
        )

        if result.success and result.data:
            # Format memory as hex dump
            lines = ["Memory dump:"]
            for addr_str, value in result.data.items():
                lines.append(f"  {addr_str}: 0x{value:02X} ({value})")
            result_content.append(TextContent(type="text", text="\n".join(lines)))
            if result.screenshot:
                result_content.append(ImageContent(
                    type="image",
                    data=base64.b64encode(result.screenshot).decode(),
                    mimeType="image/png",
                ))
        else:
            result_content.append(TextContent(type="text", text=f"Error: {result.error}"))

    elif name == "mgba_read_range":
        result = emu.read_memory_range(
            rom_path=arguments["rom_path"],
            start_addr=arguments["start_address"],
            length=arguments["length"],
            savestate_path=arguments.get("savestate_path"),
            frames_before_read=arguments.get("frames", 60),
        )

        if result.success and result.data:
            data = result.data["data"]
            start = result.data["start"]
            # Format as hex dump with 16 bytes per line
            lines = [f"Memory range 0x{start:04X} - 0x{start + len(data) - 1:04X}:"]
            for i in range(0, len(data), 16):
                addr = start + i
                hex_bytes = " ".join(f"{b:02X}" for b in data[i:i+16])
                lines.append(f"  {addr:04X}: {hex_bytes}")
            result_content.append(TextContent(type="text", text="\n".join(lines)))
            if result.screenshot:
                result_content.append(ImageContent(
                    type="image",
                    data=base64.b64encode(result.screenshot).decode(),
                    mimeType="image/png",
                ))
        else:
            result_content.append(TextContent(type="text", text=f"Error: {result.error}"))

    elif name == "mgba_dump_oam":
        result = emu.dump_oam(
            rom_path=arguments["rom_path"],
            savestate_path=arguments.get("savestate_path"),
            frames_before_dump=arguments.get("frames", 60),
        )

        if result.success and result.data:
            oam = result.data["oam"]
            lines = ["OAM Sprite Data (40 slots):"]
            lines.append("Slot  Y    X   Tile  Flags  Pal  Visible")
            lines.append("-" * 45)
            for sprite in oam:
                if sprite["visible"]:
                    lines.append(
                        f"{sprite['slot']:3d}  {sprite['y']:3d}  {sprite['x']:3d}  "
                        f"0x{sprite['tile']:02X}   0x{sprite['flags']:02X}    {sprite['palette']}    *"
                    )
            result_content.append(TextContent(type="text", text="\n".join(lines)))
            if result.screenshot:
                result_content.append(ImageContent(
                    type="image",
                    data=base64.b64encode(result.screenshot).decode(),
                    mimeType="image/png",
                ))
        else:
            result_content.append(TextContent(type="text", text=f"Error: {result.error}"))

    elif name == "mgba_dump_entities":
        result = emu.dump_entities(
            rom_path=arguments["rom_path"],
            entity_base=arguments.get("entity_base", 0xC200),
            entity_size=arguments.get("entity_size", 24),
            entity_count=arguments.get("entity_count", 10),
            savestate_path=arguments.get("savestate_path"),
            frames_before_dump=arguments.get("frames", 60),
        )

        if result.success and result.data:
            lines = [f"Boss flag: 0x{result.data['boss_flag']:02X}"]
            lines.append("\nEntity Data:")
            for ent in result.data["entities"]:
                bytes_data = ent["bytes"]
                # Check if entity has any non-zero data
                if any(b != 0 for b in bytes_data):
                    hex_str = " ".join(f"{b:02X}" for b in bytes_data[:16])
                    lines.append(f"  Entity {ent['index']} (0x{ent['address']:04X}): {hex_str}...")
            result_content.append(TextContent(type="text", text="\n".join(lines)))
            if result.screenshot:
                result_content.append(ImageContent(
                    type="image",
                    data=base64.b64encode(result.screenshot).decode(),
                    mimeType="image/png",
                ))
        else:
            result_content.append(TextContent(type="text", text=f"Error: {result.error}"))

    elif name == "mgba_run_lua":
        result = emu.run_lua_script(
            rom_path=arguments["rom_path"],
            script=arguments["script"],
            savestate_path=arguments.get("savestate_path"),
            timeout=arguments.get("timeout", 30),
        )

        lines = []
        if result.success:
            lines.append("Lua script executed successfully")
            if result.data:
                lines.append(f"Output data: {json.dumps(result.data, indent=2)}")
            if result.output:
                lines.append(f"Stdout: {result.output}")
        else:
            lines.append(f"Error: {result.error}")

        result_content.append(TextContent(type="text", text="\n".join(lines)))
        if result.screenshot:
            result_content.append(ImageContent(
                type="image",
                data=base64.b64encode(result.screenshot).decode(),
                mimeType="image/png",
            ))

    else:
        result_content.append(TextContent(type="text", text=f"Unknown tool: {name}"))

    return result_content


def main():
    """Run the MCP server."""
    import asyncio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
