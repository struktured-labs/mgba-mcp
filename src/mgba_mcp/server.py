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
        Tool(
            name="mgba_xxd",
            description="Hex dump of ROM file bytes (like xxd). Useful for disassembly and ROM analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "rom_path": {
                        "type": "string",
                        "description": "Path to the ROM file",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Byte offset to start reading from (default: 0)",
                        "default": 0,
                    },
                    "length": {
                        "type": "integer",
                        "description": "Number of bytes to read (default: 256, max: 4096)",
                        "default": 256,
                    },
                    "disassemble": {
                        "type": "boolean",
                        "description": "If true, attempt to disassemble as Z80/LR35902 instructions (default: false)",
                        "default": False,
                    },
                },
                "required": ["rom_path"],
            },
        ),
        Tool(
            name="mgba_search_bytes",
            description="Search for a byte pattern in a ROM file. Returns all matching offsets.",
            inputSchema={
                "type": "object",
                "properties": {
                    "rom_path": {
                        "type": "string",
                        "description": "Path to the ROM file",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Hex string to search for (e.g., 'CD 96 42' or 'CD9642')",
                    },
                    "start_offset": {
                        "type": "integer",
                        "description": "Start searching from this offset (default: 0)",
                        "default": 0,
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["rom_path", "pattern"],
            },
        ),
    ]


# LR35902 (Game Boy CPU) instruction set for basic disassembly
_LR35902_OPCODES = {
    0x00: ("NOP", 1), 0x01: ("LD BC,nn", 3), 0x02: ("LD [BC],A", 1), 0x03: ("INC BC", 1),
    0x04: ("INC B", 1), 0x05: ("DEC B", 1), 0x06: ("LD B,n", 2), 0x07: ("RLCA", 1),
    0x08: ("LD [nn],SP", 3), 0x09: ("ADD HL,BC", 1), 0x0A: ("LD A,[BC]", 1), 0x0B: ("DEC BC", 1),
    0x0C: ("INC C", 1), 0x0D: ("DEC C", 1), 0x0E: ("LD C,n", 2), 0x0F: ("RRCA", 1),
    0x10: ("STOP", 1), 0x11: ("LD DE,nn", 3), 0x12: ("LD [DE],A", 1), 0x13: ("INC DE", 1),
    0x14: ("INC D", 1), 0x15: ("DEC D", 1), 0x16: ("LD D,n", 2), 0x17: ("RLA", 1),
    0x18: ("JR n", 2), 0x19: ("ADD HL,DE", 1), 0x1A: ("LD A,[DE]", 1), 0x1B: ("DEC DE", 1),
    0x1C: ("INC E", 1), 0x1D: ("DEC E", 1), 0x1E: ("LD E,n", 2), 0x1F: ("RRA", 1),
    0x20: ("JR NZ,n", 2), 0x21: ("LD HL,nn", 3), 0x22: ("LD [HL+],A", 1), 0x23: ("INC HL", 1),
    0x24: ("INC H", 1), 0x25: ("DEC H", 1), 0x26: ("LD H,n", 2), 0x27: ("DAA", 1),
    0x28: ("JR Z,n", 2), 0x29: ("ADD HL,HL", 1), 0x2A: ("LD A,[HL+]", 1), 0x2B: ("DEC HL", 1),
    0x2C: ("INC L", 1), 0x2D: ("DEC L", 1), 0x2E: ("LD L,n", 2), 0x2F: ("CPL", 1),
    0x30: ("JR NC,n", 2), 0x31: ("LD SP,nn", 3), 0x32: ("LD [HL-],A", 1), 0x33: ("INC SP", 1),
    0x34: ("INC [HL]", 1), 0x35: ("DEC [HL]", 1), 0x36: ("LD [HL],n", 2), 0x37: ("SCF", 1),
    0x38: ("JR C,n", 2), 0x39: ("ADD HL,SP", 1), 0x3A: ("LD A,[HL-]", 1), 0x3B: ("DEC SP", 1),
    0x3C: ("INC A", 1), 0x3D: ("DEC A", 1), 0x3E: ("LD A,n", 2), 0x3F: ("CCF", 1),
    0x40: ("LD B,B", 1), 0x41: ("LD B,C", 1), 0x42: ("LD B,D", 1), 0x43: ("LD B,E", 1),
    0x44: ("LD B,H", 1), 0x45: ("LD B,L", 1), 0x46: ("LD B,[HL]", 1), 0x47: ("LD B,A", 1),
    0x48: ("LD C,B", 1), 0x49: ("LD C,C", 1), 0x4A: ("LD C,D", 1), 0x4B: ("LD C,E", 1),
    0x4C: ("LD C,H", 1), 0x4D: ("LD C,L", 1), 0x4E: ("LD C,[HL]", 1), 0x4F: ("LD C,A", 1),
    0x50: ("LD D,B", 1), 0x51: ("LD D,C", 1), 0x52: ("LD D,D", 1), 0x53: ("LD D,E", 1),
    0x54: ("LD D,H", 1), 0x55: ("LD D,L", 1), 0x56: ("LD D,[HL]", 1), 0x57: ("LD D,A", 1),
    0x58: ("LD E,B", 1), 0x59: ("LD E,C", 1), 0x5A: ("LD E,D", 1), 0x5B: ("LD E,E", 1),
    0x5C: ("LD E,H", 1), 0x5D: ("LD E,L", 1), 0x5E: ("LD E,[HL]", 1), 0x5F: ("LD E,A", 1),
    0x60: ("LD H,B", 1), 0x61: ("LD H,C", 1), 0x62: ("LD H,D", 1), 0x63: ("LD H,E", 1),
    0x64: ("LD H,H", 1), 0x65: ("LD H,L", 1), 0x66: ("LD H,[HL]", 1), 0x67: ("LD H,A", 1),
    0x68: ("LD L,B", 1), 0x69: ("LD L,C", 1), 0x6A: ("LD L,D", 1), 0x6B: ("LD L,E", 1),
    0x6C: ("LD L,H", 1), 0x6D: ("LD L,L", 1), 0x6E: ("LD L,[HL]", 1), 0x6F: ("LD L,A", 1),
    0x70: ("LD [HL],B", 1), 0x71: ("LD [HL],C", 1), 0x72: ("LD [HL],D", 1), 0x73: ("LD [HL],E", 1),
    0x74: ("LD [HL],H", 1), 0x75: ("LD [HL],L", 1), 0x76: ("HALT", 1), 0x77: ("LD [HL],A", 1),
    0x78: ("LD A,B", 1), 0x79: ("LD A,C", 1), 0x7A: ("LD A,D", 1), 0x7B: ("LD A,E", 1),
    0x7C: ("LD A,H", 1), 0x7D: ("LD A,L", 1), 0x7E: ("LD A,[HL]", 1), 0x7F: ("LD A,A", 1),
    0x80: ("ADD A,B", 1), 0x81: ("ADD A,C", 1), 0x82: ("ADD A,D", 1), 0x83: ("ADD A,E", 1),
    0x84: ("ADD A,H", 1), 0x85: ("ADD A,L", 1), 0x86: ("ADD A,[HL]", 1), 0x87: ("ADD A,A", 1),
    0x88: ("ADC A,B", 1), 0x89: ("ADC A,C", 1), 0x8A: ("ADC A,D", 1), 0x8B: ("ADC A,E", 1),
    0x8C: ("ADC A,H", 1), 0x8D: ("ADC A,L", 1), 0x8E: ("ADC A,[HL]", 1), 0x8F: ("ADC A,A", 1),
    0x90: ("SUB B", 1), 0x91: ("SUB C", 1), 0x92: ("SUB D", 1), 0x93: ("SUB E", 1),
    0x94: ("SUB H", 1), 0x95: ("SUB L", 1), 0x96: ("SUB [HL]", 1), 0x97: ("SUB A", 1),
    0x98: ("SBC A,B", 1), 0x99: ("SBC A,C", 1), 0x9A: ("SBC A,D", 1), 0x9B: ("SBC A,E", 1),
    0x9C: ("SBC A,H", 1), 0x9D: ("SBC A,L", 1), 0x9E: ("SBC A,[HL]", 1), 0x9F: ("SBC A,A", 1),
    0xA0: ("AND B", 1), 0xA1: ("AND C", 1), 0xA2: ("AND D", 1), 0xA3: ("AND E", 1),
    0xA4: ("AND H", 1), 0xA5: ("AND L", 1), 0xA6: ("AND [HL]", 1), 0xA7: ("AND A", 1),
    0xA8: ("XOR B", 1), 0xA9: ("XOR C", 1), 0xAA: ("XOR D", 1), 0xAB: ("XOR E", 1),
    0xAC: ("XOR H", 1), 0xAD: ("XOR L", 1), 0xAE: ("XOR [HL]", 1), 0xAF: ("XOR A", 1),
    0xB0: ("OR B", 1), 0xB1: ("OR C", 1), 0xB2: ("OR D", 1), 0xB3: ("OR E", 1),
    0xB4: ("OR H", 1), 0xB5: ("OR L", 1), 0xB6: ("OR [HL]", 1), 0xB7: ("OR A", 1),
    0xB8: ("CP B", 1), 0xB9: ("CP C", 1), 0xBA: ("CP D", 1), 0xBB: ("CP E", 1),
    0xBC: ("CP H", 1), 0xBD: ("CP L", 1), 0xBE: ("CP [HL]", 1), 0xBF: ("CP A", 1),
    0xC0: ("RET NZ", 1), 0xC1: ("POP BC", 1), 0xC2: ("JP NZ,nn", 3), 0xC3: ("JP nn", 3),
    0xC4: ("CALL NZ,nn", 3), 0xC5: ("PUSH BC", 1), 0xC6: ("ADD A,n", 2), 0xC7: ("RST 00", 1),
    0xC8: ("RET Z", 1), 0xC9: ("RET", 1), 0xCA: ("JP Z,nn", 3), 0xCB: ("PREFIX CB", 1),
    0xCC: ("CALL Z,nn", 3), 0xCD: ("CALL nn", 3), 0xCE: ("ADC A,n", 2), 0xCF: ("RST 08", 1),
    0xD0: ("RET NC", 1), 0xD1: ("POP DE", 1), 0xD2: ("JP NC,nn", 3), 0xD3: ("???", 1),
    0xD4: ("CALL NC,nn", 3), 0xD5: ("PUSH DE", 1), 0xD6: ("SUB n", 2), 0xD7: ("RST 10", 1),
    0xD8: ("RET C", 1), 0xD9: ("RETI", 1), 0xDA: ("JP C,nn", 3), 0xDB: ("???", 1),
    0xDC: ("CALL C,nn", 3), 0xDD: ("???", 1), 0xDE: ("SBC A,n", 2), 0xDF: ("RST 18", 1),
    0xE0: ("LDH [n],A", 2), 0xE1: ("POP HL", 1), 0xE2: ("LD [C],A", 1), 0xE3: ("???", 1),
    0xE4: ("???", 1), 0xE5: ("PUSH HL", 1), 0xE6: ("AND n", 2), 0xE7: ("RST 20", 1),
    0xE8: ("ADD SP,n", 2), 0xE9: ("JP HL", 1), 0xEA: ("LD [nn],A", 3), 0xEB: ("???", 1),
    0xEC: ("???", 1), 0xED: ("???", 1), 0xEE: ("XOR n", 2), 0xEF: ("RST 28", 1),
    0xF0: ("LDH A,[n]", 2), 0xF1: ("POP AF", 1), 0xF2: ("LD A,[C]", 1), 0xF3: ("DI", 1),
    0xF4: ("???", 1), 0xF5: ("PUSH AF", 1), 0xF6: ("OR n", 2), 0xF7: ("RST 30", 1),
    0xF8: ("LD HL,SP+n", 2), 0xF9: ("LD SP,HL", 1), 0xFA: ("LD A,[nn]", 3), 0xFB: ("EI", 1),
    0xFC: ("???", 1), 0xFD: ("???", 1), 0xFE: ("CP n", 2), 0xFF: ("RST 38", 1),
}


def _disassemble_lr35902(data: bytes, base_addr: int) -> list[str]:
    """Disassemble LR35902 (Game Boy) machine code."""
    lines = []
    i = 0
    while i < len(data):
        addr = base_addr + i
        opcode = data[i]

        if opcode in _LR35902_OPCODES:
            mnemonic, size = _LR35902_OPCODES[opcode]

            # Get operand bytes
            if size == 2 and i + 1 < len(data):
                operand = data[i + 1]
                hex_bytes = f"{opcode:02X} {operand:02X}"
                # Replace 'n' with actual value
                if "n" in mnemonic and "nn" not in mnemonic:
                    if "JR" in mnemonic:
                        # Signed relative jump
                        target = addr + 2 + (operand if operand < 128 else operand - 256)
                        mnemonic = mnemonic.replace("n", f"0x{target:04X}")
                    else:
                        mnemonic = mnemonic.replace("n", f"0x{operand:02X}")
            elif size == 3 and i + 2 < len(data):
                lo, hi = data[i + 1], data[i + 2]
                operand = (hi << 8) | lo
                hex_bytes = f"{opcode:02X} {lo:02X} {hi:02X}"
                mnemonic = mnemonic.replace("nn", f"0x{operand:04X}")
            else:
                hex_bytes = f"{opcode:02X}"
                size = 1  # Truncate if not enough data

            lines.append(f"{addr:04X}: {hex_bytes:<12} {mnemonic}")
            i += size
        else:
            lines.append(f"{addr:04X}: {opcode:02X}           DB 0x{opcode:02X}")
            i += 1

    return lines


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

    elif name == "mgba_xxd":
        rom_path = Path(arguments["rom_path"])
        offset = arguments.get("offset", 0)
        length = min(arguments.get("length", 256), 4096)  # Cap at 4KB
        disassemble = arguments.get("disassemble", False)

        try:
            with open(rom_path, "rb") as f:
                f.seek(offset)
                data = f.read(length)

            lines = [f"Hex dump of {rom_path.name} at 0x{offset:04X} ({len(data)} bytes):"]
            lines.append("")

            if disassemble:
                # Basic LR35902 disassembly
                lines.extend(_disassemble_lr35902(data, offset))
            else:
                # Standard xxd-style output
                for i in range(0, len(data), 16):
                    addr = offset + i
                    chunk = data[i:i+16]
                    hex_part = " ".join(f"{b:02X}" for b in chunk)
                    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                    lines.append(f"{addr:08X}: {hex_part:<48}  {ascii_part}")

            result_content.append(TextContent(type="text", text="\n".join(lines)))
        except Exception as e:
            result_content.append(TextContent(type="text", text=f"Error: {e}"))

    elif name == "mgba_search_bytes":
        rom_path = Path(arguments["rom_path"])
        pattern_str = arguments["pattern"].replace(" ", "").upper()
        start_offset = arguments.get("start_offset", 0)
        max_results = arguments.get("max_results", 50)

        try:
            # Parse hex pattern
            pattern = bytes.fromhex(pattern_str)

            with open(rom_path, "rb") as f:
                rom_data = f.read()

            # Search for pattern
            results = []
            pos = start_offset
            while len(results) < max_results:
                pos = rom_data.find(pattern, pos)
                if pos == -1:
                    break
                results.append(pos)
                pos += 1

            lines = [f"Search for pattern '{pattern_str}' in {rom_path.name}:"]
            lines.append(f"Found {len(results)} match(es)" + (f" (limited to {max_results})" if len(results) == max_results else ""))
            lines.append("")

            for pos in results:
                # Show context (8 bytes before, pattern, 8 bytes after)
                ctx_start = max(0, pos - 8)
                ctx_end = min(len(rom_data), pos + len(pattern) + 8)
                ctx = rom_data[ctx_start:ctx_end]
                hex_ctx = " ".join(f"{b:02X}" for b in ctx)
                lines.append(f"  0x{pos:06X}: {hex_ctx}")

            result_content.append(TextContent(type="text", text="\n".join(lines)))
        except ValueError as e:
            result_content.append(TextContent(type="text", text=f"Invalid hex pattern: {e}"))
        except Exception as e:
            result_content.append(TextContent(type="text", text=f"Error: {e}"))

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
