"""mGBA emulator wrapper for headless operation."""

import base64
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class EmulatorResult:
    """Result from running the emulator."""
    success: bool
    screenshot: Optional[bytes] = None
    output: Optional[str] = None
    error: Optional[str] = None
    data: Optional[dict] = None


class MGBAEmulator:
    """Wrapper for mGBA-qt headless operation via Lua scripts."""

    def __init__(self, mgba_path: str = "mgba-qt", use_xvfb: bool = True):
        self.mgba_path = mgba_path
        self.use_xvfb = use_xvfb
        self.temp_dir = Path(tempfile.mkdtemp(prefix="mgba_mcp_"))

    def _run_with_lua(
        self,
        rom_path: str,
        lua_script: str,
        savestate_path: Optional[str] = None,
        timeout: int = 30,
    ) -> EmulatorResult:
        """Run mGBA with a Lua script and return results."""
        # Convert paths to absolute (subprocess runs in temp_dir)
        rom_path = str(Path(rom_path).resolve())
        if savestate_path:
            savestate_path = str(Path(savestate_path).resolve())

        # Write Lua script to temp file
        lua_file = self.temp_dir / "script.lua"
        lua_file.write_text(lua_script)

        # Build command
        cmd = []
        if self.use_xvfb:
            cmd.extend(["xvfb-run", "-a"])

        cmd.extend([self.mgba_path, rom_path])

        if savestate_path:
            cmd.extend(["-t", savestate_path])

        cmd.extend(["--script", str(lua_file), "-l", "0"])

        # Disable audio to prevent sound during headless testing
        env = os.environ.copy()
        env["SDL_AUDIODRIVER"] = "dummy"

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.temp_dir),
                env=env,
            )

            # Check for output files
            screenshot_path = self.temp_dir / "screenshot.png"
            output_path = self.temp_dir / "output.json"

            screenshot = None
            if screenshot_path.exists():
                screenshot = screenshot_path.read_bytes()

            output_data = None
            if output_path.exists():
                try:
                    output_data = json.loads(output_path.read_text())
                except json.JSONDecodeError:
                    pass

            return EmulatorResult(
                success=result.returncode == 0,
                screenshot=screenshot,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None,
                data=output_data,
            )

        except subprocess.TimeoutExpired:
            # mGBA often doesn't exit cleanly under xvfb, but may have produced output
            # Check for output files anyway
            screenshot_path = self.temp_dir / "screenshot.png"
            output_path = self.temp_dir / "output.json"

            screenshot = None
            if screenshot_path.exists():
                screenshot = screenshot_path.read_bytes()

            output_data = None
            if output_path.exists():
                try:
                    output_data = json.loads(output_path.read_text())
                except json.JSONDecodeError:
                    pass

            # If we got output, consider it a success despite timeout
            if screenshot or output_data:
                return EmulatorResult(
                    success=True,
                    screenshot=screenshot,
                    data=output_data,
                )

            return EmulatorResult(
                success=False,
                error=f"Emulator timed out after {timeout}s",
            )
        except Exception as e:
            return EmulatorResult(
                success=False,
                error=str(e),
            )

    def run_frames(
        self,
        rom_path: str,
        frames: int = 60,
        savestate_path: Optional[str] = None,
        screenshot: bool = True,
    ) -> EmulatorResult:
        """Run emulator for specified number of frames."""
        lua_script = f"""
local frame = 0
local target_frames = {frames}
local take_screenshot = {'true' if screenshot else 'false'}

callbacks:add("frame", function()
    frame = frame + 1
    if frame >= target_frames then
        if take_screenshot then
            emu:screenshot("screenshot.png")
        end
        emu:quit()
    end
end)
"""
        return self._run_with_lua(rom_path, lua_script, savestate_path)

    def read_memory(
        self,
        rom_path: str,
        addresses: list[int],
        savestate_path: Optional[str] = None,
        frames_before_read: int = 60,
    ) -> EmulatorResult:
        """Read memory at specified addresses."""
        addr_list = ", ".join(f"0x{a:04X}" for a in addresses)
        lua_script = f"""
local frame = 0
local addresses = {{{addr_list}}}

callbacks:add("frame", function()
    frame = frame + 1
    if frame >= {frames_before_read} then
        local f = io.open("output.json", "w")
        if f then
            f:write('{{')
            for i, addr in ipairs(addresses) do
                if i > 1 then f:write(',') end
                f:write(string.format('"0x%04X":%d', addr, emu:read8(addr)))
            end
            f:write('}}')
            f:close()
        end
        emu:screenshot("screenshot.png")
        emu:quit()
    end
end)
"""
        return self._run_with_lua(rom_path, lua_script, savestate_path)

    def read_memory_range(
        self,
        rom_path: str,
        start_addr: int,
        length: int,
        savestate_path: Optional[str] = None,
        frames_before_read: int = 60,
    ) -> EmulatorResult:
        """Read a range of memory addresses."""
        lua_script = f"""
local frame = 0

callbacks:add("frame", function()
    frame = frame + 1
    if frame >= {frames_before_read} then
        local f = io.open("output.json", "w")
        if f then
            f:write('{{"start": {start_addr}, "length": {length}, "data": [')
            for i = 0, {length - 1} do
                if i > 0 then f:write(',') end
                f:write(tostring(emu:read8({start_addr} + i)))
            end
            f:write(']}}')
            f:close()
        end
        emu:screenshot("screenshot.png")
        emu:quit()
    end
end)
"""
        return self._run_with_lua(rom_path, lua_script, savestate_path)

    def dump_oam(
        self,
        rom_path: str,
        savestate_path: Optional[str] = None,
        frames_before_dump: int = 60,
    ) -> EmulatorResult:
        """Dump OAM (sprite) data."""
        lua_script = f"""
local frame = 0

callbacks:add("frame", function()
    frame = frame + 1
    if frame >= {frames_before_dump} then
        local f = io.open("output.json", "w")
        if f then
            f:write('{{"oam": [')
            for slot = 0, 39 do
                local addr = 0xFE00 + slot * 4
                local y = emu:read8(addr)
                local x = emu:read8(addr + 1)
                local tile = emu:read8(addr + 2)
                local flags = emu:read8(addr + 3)
                if slot > 0 then f:write(',') end
                f:write(string.format(
                    '{{"slot":%d,"y":%d,"x":%d,"tile":%d,"flags":%d,"palette":%d,"visible":%s}}',
                    slot, y, x, tile, flags, flags % 8,
                    (y > 0 and y < 160) and "true" or "false"
                ))
            end
            f:write(']}}')
            f:close()
        end
        emu:screenshot("screenshot.png")
        emu:quit()
    end
end)
"""
        return self._run_with_lua(rom_path, lua_script, savestate_path)

    def dump_entities(
        self,
        rom_path: str,
        entity_base: int = 0xC200,
        entity_size: int = 24,
        entity_count: int = 10,
        savestate_path: Optional[str] = None,
        frames_before_dump: int = 60,
    ) -> EmulatorResult:
        """Dump entity data from WRAM."""
        lua_script = f"""
local frame = 0

callbacks:add("frame", function()
    frame = frame + 1
    if frame >= {frames_before_dump} then
        local f = io.open("output.json", "w")
        if f then
            f:write('{{"boss_flag":' .. emu:read8(0xFFBF) .. ',"entities":[')
            for ent = 0, {entity_count - 1} do
                local base = {entity_base} + ent * {entity_size}
                if ent > 0 then f:write(',') end
                f:write('{{"index":' .. ent .. ',"address":' .. base .. ',"bytes":[')
                for i = 0, {entity_size - 1} do
                    if i > 0 then f:write(',') end
                    f:write(tostring(emu:read8(base + i)))
                end
                f:write(']}}')
            end
            f:write(']}}')
            f:close()
        end
        emu:screenshot("screenshot.png")
        emu:quit()
    end
end)
"""
        return self._run_with_lua(rom_path, lua_script, savestate_path)

    def run_lua_script(
        self,
        rom_path: str,
        script: str,
        savestate_path: Optional[str] = None,
        timeout: int = 30,
    ) -> EmulatorResult:
        """Run a custom Lua script."""
        return self._run_with_lua(rom_path, script, savestate_path, timeout)

    def cleanup(self):
        """Clean up temporary files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
