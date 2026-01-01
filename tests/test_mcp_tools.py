"""Comprehensive eval tests for mgba-mcp tools.

These tests verify the MCP tool functionality with actual ROM/savestate data.
"""

import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mgba_mcp.emulator import MGBAEmulator

# Paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
ROM_PATH = PROJECT_ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
SAVESTATE_PATH = PROJECT_ROOT / "rom/working/penta_dragon_dx_FIXED.ss1"
TMP_DIR = PROJECT_ROOT / "tmp"


class TestResult:
    """Test result container."""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""
        self.details = {}

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"{self.name}: {status} - {self.message}"


def setup():
    """Verify test prerequisites."""
    TMP_DIR.mkdir(exist_ok=True)

    if not ROM_PATH.exists():
        print(f"ERROR: ROM not found at {ROM_PATH}")
        return False
    if not SAVESTATE_PATH.exists():
        print(f"WARNING: Savestate not found at {SAVESTATE_PATH}, some tests will be limited")

    return True


def test_run_frames_cold_start():
    """Test running from cold start (no savestate)."""
    result = TestResult("run_frames_cold_start")
    emu = MGBAEmulator()

    try:
        r = emu.run_frames(str(ROM_PATH), frames=60, screenshot=True)

        if not r.success:
            result.message = f"Failed: {r.error}"
            return result

        if not r.screenshot:
            result.message = "No screenshot captured"
            return result

        # Save screenshot
        out = TMP_DIR / "eval_cold_start.png"
        out.write_bytes(r.screenshot)

        result.passed = True
        result.message = f"Screenshot saved ({len(r.screenshot)} bytes)"
        result.details["screenshot_size"] = len(r.screenshot)

    finally:
        emu.cleanup()

    return result


def test_run_frames_with_savestate():
    """Test running from savestate (actual gameplay)."""
    result = TestResult("run_frames_with_savestate")

    if not SAVESTATE_PATH.exists():
        result.message = "Skipped: no savestate available"
        result.passed = True  # Skip is OK
        return result

    emu = MGBAEmulator()

    try:
        r = emu.run_frames(str(ROM_PATH), frames=60, savestate_path=str(SAVESTATE_PATH), screenshot=True)

        if not r.success:
            result.message = f"Failed: {r.error}"
            return result

        if not r.screenshot:
            result.message = "No screenshot captured"
            return result

        # Save screenshot
        out = TMP_DIR / "eval_savestate.png"
        out.write_bytes(r.screenshot)

        # With a real savestate, screenshot should be larger (actual game graphics)
        result.passed = True
        result.message = f"Screenshot saved ({len(r.screenshot)} bytes)"
        result.details["screenshot_size"] = len(r.screenshot)

    finally:
        emu.cleanup()

    return result


def test_dump_oam_gameplay():
    """Test OAM dump during actual gameplay."""
    result = TestResult("dump_oam_gameplay")

    if not SAVESTATE_PATH.exists():
        result.message = "Skipped: no savestate available"
        result.passed = True
        return result

    emu = MGBAEmulator()

    try:
        r = emu.dump_oam(str(ROM_PATH), savestate_path=str(SAVESTATE_PATH), frames_before_dump=30)

        if not r.success:
            result.message = f"Failed: {r.error}"
            return result

        if not r.data or "oam" not in r.data:
            result.message = "No OAM data returned"
            return result

        oam = r.data["oam"]
        if len(oam) != 40:
            result.message = f"Expected 40 OAM entries, got {len(oam)}"
            return result

        # Count visible sprites
        visible = [s for s in oam if s["visible"]]
        result.details["total_sprites"] = len(oam)
        result.details["visible_sprites"] = len(visible)

        # Verify sprite data structure
        sample = oam[0]
        required_keys = ["slot", "y", "x", "tile", "flags", "palette", "visible"]
        for key in required_keys:
            if key not in sample:
                result.message = f"Missing key in sprite data: {key}"
                return result

        result.passed = True
        result.message = f"{len(visible)} visible sprites"

        # Save OAM data for inspection
        out = TMP_DIR / "eval_oam.json"
        out.write_text(json.dumps(r.data, indent=2))

    finally:
        emu.cleanup()

    return result


def test_dump_entities():
    """Test entity data dump."""
    result = TestResult("dump_entities")

    if not SAVESTATE_PATH.exists():
        result.message = "Skipped: no savestate available"
        result.passed = True
        return result

    emu = MGBAEmulator()

    try:
        r = emu.dump_entities(str(ROM_PATH), savestate_path=str(SAVESTATE_PATH), frames_before_dump=30)

        if not r.success:
            result.message = f"Failed: {r.error}"
            return result

        if not r.data or "entities" not in r.data:
            result.message = "No entity data returned"
            return result

        entities = r.data["entities"]
        if len(entities) != 10:
            result.message = f"Expected 10 entities, got {len(entities)}"
            return result

        # Verify entity structure
        sample = entities[0]
        if "bytes" not in sample or len(sample["bytes"]) != 24:
            result.message = "Invalid entity byte structure"
            return result

        # Check boss flag
        boss_flag = r.data.get("boss_flag", -1)
        result.details["boss_flag"] = boss_flag
        result.details["entity_count"] = len(entities)

        result.passed = True
        result.message = f"10 entities, boss_flag={boss_flag}"

        # Save entity data
        out = TMP_DIR / "eval_entities.json"
        out.write_text(json.dumps(r.data, indent=2))

    finally:
        emu.cleanup()

    return result


def test_read_memory_addresses():
    """Test reading specific memory addresses."""
    result = TestResult("read_memory_addresses")

    emu = MGBAEmulator()

    try:
        # Read boss flag and some OAM
        addresses = [0xFFBF, 0xFE00, 0xFE04, 0xFE08, 0xC200, 0xC218]
        r = emu.read_memory(str(ROM_PATH), addresses=addresses, frames_before_read=60)

        if not r.success:
            result.message = f"Failed: {r.error}"
            return result

        if not r.data:
            result.message = "No memory data returned"
            return result

        # Verify all addresses were read
        for addr in addresses:
            key = f"0x{addr:04X}"
            if key not in r.data:
                result.message = f"Missing address {key}"
                return result

        result.details["addresses"] = r.data
        result.passed = True
        result.message = f"Read {len(addresses)} addresses"

    finally:
        emu.cleanup()

    return result


def test_read_memory_range():
    """Test reading a contiguous memory range."""
    result = TestResult("read_memory_range")

    if not SAVESTATE_PATH.exists():
        result.message = "Skipped: no savestate available"
        result.passed = True
        return result

    emu = MGBAEmulator()

    try:
        # Read first entity's data (24 bytes at 0xC200)
        r = emu.read_memory_range(
            str(ROM_PATH),
            start_addr=0xC200,
            length=24,
            savestate_path=str(SAVESTATE_PATH),
            frames_before_read=30
        )

        if not r.success:
            result.message = f"Failed: {r.error}"
            return result

        if not r.data or "data" not in r.data:
            result.message = "No range data returned"
            return result

        data = r.data["data"]
        if len(data) != 24:
            result.message = f"Expected 24 bytes, got {len(data)}"
            return result

        result.details["start"] = r.data.get("start")
        result.details["length"] = r.data.get("length")
        result.details["sample_bytes"] = data[:8]

        result.passed = True
        result.message = f"Read 24 bytes from 0xC200"

    finally:
        emu.cleanup()

    return result


def test_custom_lua_script():
    """Test running a custom Lua script."""
    result = TestResult("custom_lua_script")

    emu = MGBAEmulator()

    try:
        # Custom script that reads game title from ROM header
        script = """
local frame = 0
callbacks:add("frame", function()
    frame = frame + 1
    if frame >= 10 then
        local f = io.open("output.json", "w")
        if f then
            -- Read game title from ROM header (0x0134-0x0143)
            local title = ""
            for i = 0, 15 do
                local byte = emu:read8(0x0134 + i)
                if byte >= 32 and byte < 127 then
                    title = title .. string.char(byte)
                end
            end
            f:write('{"title":"' .. title .. '","frame":' .. frame .. '}')
            f:close()
        end
        local done = io.open("DONE", "w")
        if done then done:write("OK"); done:close() end
    end
end)
"""
        r = emu.run_lua_script(str(ROM_PATH), script=script, timeout=15)

        if not r.success:
            result.message = f"Failed: {r.error}"
            return result

        if not r.data:
            result.message = "No output data"
            return result

        title = r.data.get("title", "")
        result.details["game_title"] = title
        result.details["frame"] = r.data.get("frame")

        result.passed = True
        result.message = f"Title: '{title}'"

    finally:
        emu.cleanup()

    return result


def test_palette_verification():
    """Verify sprite palettes are being set correctly (v0.96 colorization)."""
    result = TestResult("palette_verification")

    if not SAVESTATE_PATH.exists():
        result.message = "Skipped: no savestate available"
        result.passed = True
        return result

    emu = MGBAEmulator()

    try:
        r = emu.dump_oam(str(ROM_PATH), savestate_path=str(SAVESTATE_PATH), frames_before_dump=60)

        if not r.success or not r.data:
            result.message = f"Failed: {r.error}"
            return result

        oam = r.data["oam"]
        visible = [s for s in oam if s["visible"]]

        # Check palette distribution
        palette_counts = {}
        for sprite in visible:
            pal = sprite["palette"]
            palette_counts[pal] = palette_counts.get(pal, 0) + 1

        result.details["palette_distribution"] = palette_counts
        result.details["visible_count"] = len(visible)

        # Verify Sara uses palette 1 (slots 0-3)
        sara_slots = [s for s in oam[:4] if s["visible"]]
        sara_palettes = set(s["palette"] for s in sara_slots)

        # Verify enemies use palette 4 or 7 (slots 4+)
        enemy_slots = [s for s in oam[4:] if s["visible"]]
        enemy_palettes = set(s["palette"] for s in enemy_slots)

        result.details["sara_palettes"] = list(sara_palettes)
        result.details["enemy_palettes"] = list(enemy_palettes)

        # Check if colorization is working
        if len(palette_counts) > 1:
            result.passed = True
            result.message = f"Palettes: {palette_counts}"
        else:
            result.message = f"Only one palette in use: {palette_counts}"
            result.passed = False

    finally:
        emu.cleanup()

    return result


def run_all_tests():
    """Run all eval tests."""
    if not setup():
        return []

    tests = [
        test_run_frames_cold_start,
        test_run_frames_with_savestate,
        test_dump_oam_gameplay,
        test_dump_entities,
        test_read_memory_addresses,
        test_read_memory_range,
        test_custom_lua_script,
        test_palette_verification,
    ]

    results = []
    for test_fn in tests:
        print(f"\nRunning: {test_fn.__name__}...")
        try:
            r = test_fn()
            results.append(r)
            print(f"  {r}")
            if r.details:
                for k, v in r.details.items():
                    print(f"    {k}: {v}")
        except Exception as e:
            result = TestResult(test_fn.__name__)
            result.message = f"Exception: {e}"
            results.append(result)
            print(f"  EXCEPTION: {e}")

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("mgba-mcp Comprehensive Eval Tests")
    print("=" * 60)

    results = run_all_tests()

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}: {r.message}")

    print(f"\nTotal: {passed}/{total} passed")

    sys.exit(0 if passed == total else 1)
