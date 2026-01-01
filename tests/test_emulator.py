"""Test the MGBAEmulator wrapper."""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mgba_mcp.emulator import MGBAEmulator


def test_run_frames():
    """Test running for a fixed number of frames."""
    rom_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.gb"
    if not rom_path.exists():
        print(f"ROM not found: {rom_path}")
        return False

    emu = MGBAEmulator()
    try:
        print(f"Testing run_frames with {rom_path}...")
        result = emu.run_frames(str(rom_path), frames=30, screenshot=True)

        print(f"  Success: {result.success}")
        print(f"  Screenshot: {len(result.screenshot) if result.screenshot else 0} bytes")
        print(f"  Error: {result.error}")

        if result.screenshot:
            # Save for inspection
            out_path = Path(__file__).parent.parent.parent / "tmp/test_screenshot.png"
            out_path.write_bytes(result.screenshot)
            print(f"  Saved screenshot to {out_path}")

        return result.success and result.screenshot is not None
    finally:
        emu.cleanup()


def test_dump_oam():
    """Test OAM dump with savestate."""
    rom_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.gb"
    ss_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.ss1"

    if not rom_path.exists():
        print(f"ROM not found: {rom_path}")
        return False
    if not ss_path.exists():
        print(f"Savestate not found (optional): {ss_path}")
        ss_path = None
    else:
        ss_path = str(ss_path)

    emu = MGBAEmulator()
    try:
        print(f"Testing dump_oam...")
        result = emu.dump_oam(str(rom_path), savestate_path=ss_path, frames_before_dump=30)

        print(f"  Success: {result.success}")
        print(f"  Data: {result.data is not None}")
        print(f"  Error: {result.error}")

        if result.data and "oam" in result.data:
            visible_sprites = [s for s in result.data["oam"] if s["visible"]]
            print(f"  Visible sprites: {len(visible_sprites)}")

        return result.success
    finally:
        emu.cleanup()


def test_read_memory():
    """Test memory reading."""
    rom_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.gb"

    if not rom_path.exists():
        print(f"ROM not found: {rom_path}")
        return False

    emu = MGBAEmulator()
    try:
        print(f"Testing read_memory...")
        # Read boss flag and some OAM
        result = emu.read_memory(str(rom_path), addresses=[0xFFBF, 0xFE00, 0xFE01], frames_before_read=30)

        print(f"  Success: {result.success}")
        print(f"  Data: {result.data}")
        print(f"  Error: {result.error}")

        return result.success and result.data is not None
    finally:
        emu.cleanup()


if __name__ == "__main__":
    print("=" * 50)
    print("mGBA Emulator Wrapper Tests")
    print("=" * 50)

    tests = [
        ("run_frames", test_run_frames),
        ("dump_oam", test_dump_oam),
        ("read_memory", test_read_memory),
    ]

    results = []
    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("Results:")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(p for _, p in results)
    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    sys.exit(0 if all_passed else 1)
