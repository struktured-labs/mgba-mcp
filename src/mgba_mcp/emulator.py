"""mGBA emulator wrapper for headless operation.

Uses a watchdog pattern since emu:quit() doesn't reliably terminate mGBA.
Scripts write a DONE marker file when complete, and we kill the process.
"""

import json
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def validate_and_normalize_png(data: bytes) -> tuple[bytes | None, str]:
    """Validate and normalize PNG data for Claude API compatibility.

    Returns:
        (normalized_png_bytes, error_message) - bytes is None if invalid

    Checks:
    1. PNG signature (8 bytes)
    2. IHDR chunk exists and is valid
    3. IEND chunk exists at the end
    4. Image can be decoded by PIL (catches corruption)
    5. Dimensions are within expected Game Boy bounds

    Normalization:
    - Converts palette/grayscale to RGB for consistent API handling
    - Re-encodes to ensure clean PNG structure
    """
    if len(data) < 57:  # Minimum PNG: 8 (sig) + 25 (IHDR) + 12 (IEND) + some IDAT
        return None, f"PNG too small: {len(data)} bytes"

    # Check PNG signature
    png_signature = b'\x89PNG\r\n\x1a\n'
    if data[:8] != png_signature:
        return None, "Invalid PNG signature"

    # Check for IEND chunk at end (last 12 bytes: 4 length + 4 type + 4 CRC)
    # IEND has 0 length, so last 12 bytes should be: 00 00 00 00 IEND <crc>
    if data[-12:-8] != b'\x00\x00\x00\x00' or data[-8:-4] != b'IEND':
        return None, "Missing or invalid IEND chunk"

    # Try to actually decode and normalize the image with PIL
    try:
        from io import BytesIO
        from PIL import Image

        img = Image.open(BytesIO(data))
        img.load()  # Force full decode

        # Check dimensions - GB/GBC is 160x144, GBA is 240x160
        width, height = img.size
        if width < 10 or height < 10:
            return None, f"Image too small: {width}x{height}"
        if width > 500 or height > 500:
            return None, f"Image too large: {width}x{height}"

        # Convert to RGB to ensure Claude API compatibility
        # (handles palette mode, grayscale, etc.)
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Re-encode as PNG
        output = BytesIO()
        img.save(output, format='PNG', optimize=True)
        return output.getvalue(), ""

    except ImportError:
        # PIL not available, return original data with warning
        import sys
        print("Warning: PIL not available for PNG normalization", file=sys.stderr)
        return data, ""
    except Exception as e:
        return None, f"PIL decode/normalize failed: {e}"


@dataclass
class EmulatorResult:
    """Result from running the emulator."""
    success: bool
    screenshot: Optional[bytes] = None
    output: Optional[str] = None
    error: Optional[str] = None
    data: Optional[dict] = None


class MGBAEmulator:
    """Wrapper for mGBA-qt headless operation via Lua scripts.

    Uses watchdog pattern: scripts write a DONE file when complete,
    then we forcefully terminate the process since emu:quit() is unreliable.
    """

    def __init__(self, mgba_path: str = "mgba-qt", use_xvfb: bool = True):
        self.mgba_path = mgba_path
        self.use_xvfb = use_xvfb
        self.temp_dir = Path(tempfile.mkdtemp(prefix="mgba_mcp_"))
        self._done_marker = "MGBA_SCRIPT_DONE"

    def _kill_process_tree(self, proc: subprocess.Popen):
        """Kill process and all children (handles xvfb-run wrapper)."""
        try:
            # Try SIGTERM first
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(0.2)
        except (ProcessLookupError, PermissionError):
            pass

        try:
            # Force kill if still running
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

        # Also try direct kill
        try:
            proc.kill()
        except (ProcessLookupError, PermissionError):
            pass

    def _run_with_lua(
        self,
        rom_path: str,
        lua_script: str,
        savestate_path: Optional[str] = None,
        timeout: int = 30,
    ) -> EmulatorResult:
        """Run mGBA with a Lua script and return results.

        Uses watchdog pattern: polls for DONE marker file, then kills process.
        """
        # Convert paths to absolute (subprocess runs in temp_dir)
        rom_path = str(Path(rom_path).resolve())
        if savestate_path:
            savestate_path = str(Path(savestate_path).resolve())

        # Clean up any previous run
        done_file = self.temp_dir / "DONE"
        if done_file.exists():
            done_file.unlink()
        for f in ["screenshot.png", "output.json"]:
            p = self.temp_dir / f
            if p.exists():
                p.unlink()

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

        try:
            # Disable audio to prevent sound leakage in headless mode
            env = os.environ.copy()
            env["SDL_AUDIODRIVER"] = "dummy"

            # Start process in new process group for clean kill
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.temp_dir),
                start_new_session=True,
                env=env,
            )

            # Poll for DONE file or timeout
            start_time = time.time()
            poll_interval = 0.1  # 100ms

            while time.time() - start_time < timeout:
                # Check if script wrote DONE marker
                if done_file.exists():
                    # Give script time to finish writing and flushing files
                    # mGBA screenshot can be slow to flush
                    time.sleep(0.5)
                    # Double-check screenshot file is stable (not still being written)
                    screenshot_path = self.temp_dir / "screenshot.png"
                    if screenshot_path.exists():
                        size1 = screenshot_path.stat().st_size
                        time.sleep(0.1)
                        size2 = screenshot_path.stat().st_size
                        if size1 != size2:
                            # File still growing, wait more
                            time.sleep(0.5)
                    break

                # Check if process died
                if proc.poll() is not None:
                    break

                time.sleep(poll_interval)

            # Kill the process (emu:quit() doesn't work reliably)
            self._kill_process_tree(proc)

            # Collect output files
            screenshot_path = self.temp_dir / "screenshot.png"
            output_path = self.temp_dir / "output.json"

            screenshot = None
            if screenshot_path.exists():
                screenshot_data = screenshot_path.read_bytes()
                # Validate and normalize PNG for Claude API compatibility
                normalized_data, error_msg = validate_and_normalize_png(screenshot_data)
                if normalized_data:
                    screenshot = normalized_data
                else:
                    # Log validation failure for debugging
                    import sys
                    print(f"PNG validation failed: {error_msg} (size={len(screenshot_data)})", file=sys.stderr)

            output_data = None
            if output_path.exists():
                try:
                    output_data = json.loads(output_path.read_text())
                except json.JSONDecodeError:
                    pass

            # Success if we got expected output
            if screenshot or output_data or done_file.exists():
                return EmulatorResult(
                    success=True,
                    screenshot=screenshot,
                    data=output_data,
                )

            return EmulatorResult(
                success=False,
                error=f"Emulator timed out after {timeout}s without producing output",
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
        -- Write DONE marker (emu:quit() is unreliable)
        local f = io.open("DONE", "w")
        if f then f:write("OK"); f:close() end
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
        -- Write DONE marker
        local done = io.open("DONE", "w")
        if done then done:write("OK"); done:close() end
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
        -- Write DONE marker
        local done = io.open("DONE", "w")
        if done then done:write("OK"); done:close() end
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
        -- Write DONE marker
        local done = io.open("DONE", "w")
        if done then done:write("OK"); done:close() end
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
        -- Write DONE marker
        local done = io.open("DONE", "w")
        if done then done:write("OK"); done:close() end
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
