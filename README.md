# mgba-mcp

MCP (Model Context Protocol) server for mGBA emulator - enables programmatic control of Game Boy, Game Boy Color, and Game Boy Advance emulation.

## Features

- **Headless execution** - Runs via xvfb for automated testing
- **Screenshot capture** - Get PNG screenshots at any frame
- **Memory reading** - Read individual addresses or memory ranges
- **OAM dumping** - Dump all 40 sprite entries with position, tile, flags, and palette
- **Entity dumping** - Read game entity/actor data from WRAM
- **Custom Lua scripts** - Execute arbitrary Lua code in the emulator
- **Savestate support** - Load savestates for reproducible testing

## Installation

```bash
# Install with uv
uv pip install -e .

# Or with pip
pip install -e .
```

### Requirements

- Python 3.11+
- mGBA (mgba-qt) installed and in PATH
- xvfb-run (for headless operation on Linux)

## MCP Tools

### mgba_run
Run a ROM for a specified number of frames and capture a screenshot.

```json
{
  "rom_path": "/path/to/game.gb",
  "frames": 120,
  "savestate_path": "/path/to/save.ss0"
}
```

### mgba_read_memory
Read memory at specified addresses.

```json
{
  "rom_path": "/path/to/game.gb",
  "addresses": [49664, 65471],
  "frames": 60
}
```

### mgba_read_range
Read a contiguous range of memory.

```json
{
  "rom_path": "/path/to/game.gb",
  "start_address": 49664,
  "length": 256,
  "frames": 60
}
```

### mgba_dump_oam
Dump OAM (Object Attribute Memory) sprite data.

```json
{
  "rom_path": "/path/to/game.gb",
  "savestate_path": "/path/to/save.ss0",
  "frames": 60
}
```

### mgba_dump_entities
Dump entity/actor data from WRAM.

```json
{
  "rom_path": "/path/to/game.gb",
  "entity_base": 49664,
  "entity_size": 24,
  "entity_count": 10,
  "frames": 60
}
```

### mgba_run_lua
Execute a custom Lua script in the emulator.

```json
{
  "rom_path": "/path/to/game.gb",
  "script": "callbacks:add('frame', function() if emu:currentFrame() > 60 then emu:screenshot('screenshot.png'); emu:quit() end end)",
  "timeout": 30
}
```

## Claude Code Integration

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "mgba": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mgba-mcp", "mgba-mcp"]
    }
  }
}
```

## Usage Example

Once configured, Claude Code can use commands like:

```
Use mgba_dump_oam to check sprite palettes in rom/working/penta_dragon_dx_FIXED.gb
```

```
Use mgba_read_range to dump entity data at 0xC200 for 256 bytes
```

## Memory Addresses (Game Boy)

Common memory regions:
- `0x8000-0x9FFF` - VRAM (tile data)
- `0xC000-0xDFFF` - WRAM (work RAM)
- `0xFE00-0xFE9F` - OAM (sprite attributes)
- `0xFF00-0xFF7F` - I/O registers
- `0xFF80-0xFFFE` - HRAM (high RAM)

## License

MIT
