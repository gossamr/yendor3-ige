"""Patch safety.

REGISTER.EXE has no integrity protection: `e_csum` is 0 and DOS ignores it
regardless, the file is not packed, and its length matches the MZ header
exactly. The one real hazard is the relocation table: the loader rewrites 4000
words at load, so a patch landing on one would simply be overwritten. These
tests hold the patch definitions to that, and to the exact bytes they claim to
find.
"""
import struct

import patch
from disasm import HEADER, Exe


def test_the_format_has_no_checksum_to_invalidate(directory):
    e_csum = struct.unpack_from("<H", directory.exe, 0x12)[0]
    assert e_csum == 0

    e_cblp, e_cp = struct.unpack_from("<HH", directory.exe, 2)
    described = (e_cp - 1) * 512 + (e_cblp or 512)
    assert described == len(directory.exe), "header length must match the file"


def test_every_patch_site_is_outside_the_relocation_table():
    exe = Exe()
    for p in patch.PATCHES.values():
        assert not exe.touches_reloc(p.file_offset, len(p.original)), p.name


def test_every_patch_finds_the_bytes_it_expects():
    exe = Exe()
    for p in patch.PATCHES.values():
        at = p.file_offset
        assert exe.data[at:at + len(p.original)] == p.original, p.name
        assert p.replacement != p.original, p.name


def test_no_patch_changes_the_length_of_what_it_replaces():
    # The MZ header records the file size, the relocation table is indexed by
    # offset, and every near jump is a displacement. Nothing may move.
    for p in patch.PATCHES.values():
        assert len(p.replacement) == len(p.original), p.name


def test_patch_sites_are_the_instructions_we_think_they_are():
    exe = Exe()
    # The dispatcher clearing the /P flag before initialization ever sees it.
    clear = next(i for i in exe.disasm(0x32, 1))
    assert clear.mnemonic == "and"
    assert "0x536a" in clear.op_str and "0x7fff" in clear.op_str

    # The intro-skip branch that tests the same flag.
    test = next(i for i in exe.disasm(0xEEC9, 1))
    assert test.mnemonic == "test"
    assert "0x536a" in test.op_str and "0x8000" in test.op_str
    jne = next(i for i in exe.disasm(0xEECF, 1))
    assert jne.mnemonic == "jne"


def test_no_attract_sits_on_the_menu_countdown():
    exe = Exe()
    # The countdown is reloaded, decremented on each tick, and compared; the
    # patched byte is the branch that skips the attract sequence while it is
    # still positive.
    reload_ = next(i for i in exe.disasm(0xBF32, 1))
    assert reload_.mnemonic == "mov"
    assert "0x53ee" in reload_.op_str and "0x4b" in reload_.op_str

    dec = next(i for i in exe.disasm(0xBF52, 1))
    assert dec.mnemonic == "dec" and "0x53ee" in dec.op_str

    jg = next(i for i in exe.disasm(0xBF5B, 1))
    assert jg.mnemonic == "jg"


def test_no_attract_makes_the_countdown_branch_unconditional(tmp_path):
    out = tmp_path / "REGISTER.EXE"
    patch.apply(["no-attract"], patch.Path("game/REGISTER.EXE"), out)
    patched = Exe(out)

    ins = next(i for i in patched.disasm(0xBF5B, 1))
    assert ins.mnemonic == "jmp"
    assert ins.size == 2, "same encoding length, so nothing downstream shifts"


def test_enable_p_switch_turns_the_mask_into_a_no_op(tmp_path):
    out = tmp_path / "REGISTER.EXE"
    patch.apply(["enable-p-switch"], patch.Path("game/REGISTER.EXE"), out)
    patched = Exe(out)

    ins = next(i for i in patched.disasm(0x32, 1))
    assert ins.mnemonic == "and"
    assert "0xffff" in ins.op_str, "the AND must no longer clear the /P bit"


def test_force_skip_intro_makes_the_branch_unconditional(tmp_path):
    out = tmp_path / "REGISTER.EXE"
    patch.apply(["force-skip-intro"], patch.Path("game/REGISTER.EXE"), out)
    patched = Exe(out)

    ins = next(i for i in patched.disasm(0xEECF, 1))
    assert ins.mnemonic == "jmp"
    # Same encoding length, so nothing downstream shifts.
    assert ins.size == 2


def test_patching_changes_only_the_named_bytes(tmp_path):
    out = tmp_path / "REGISTER.EXE"
    names = list(patch.PATCHES)
    applied = patch.apply(names, patch.Path("game/REGISTER.EXE"), out)
    before = Exe().data
    after = out.read_bytes()

    assert len(after) == len(before), "length must not change"
    differing = {i for i in range(len(before)) if before[i] != after[i]}
    allowed = {p.file_offset + n for p in applied for n in range(len(p.original))}
    assert differing <= allowed
    # And every patch must actually have changed something.
    for p in applied:
        at = p.file_offset
        assert after[at:at + len(p.original)] == p.replacement, p.name


# --- the class-change reroll ------------------------------------------------

ROLL = 0x14E20      # rolls the attributes, then derives health and magic
DERIVE = 0x14EAF    # where the derivation starts, past the dice
RNG = "0x174a"      # lcall 0x174a:0xc, 0..n inclusive


def rng_calls(exe, start, stop):
    """How many times the random helper is called in [start, stop)."""
    n = 0
    for ins in exe.disasm(start, 400):
        if ins.address >= stop:
            break
        if ins.mnemonic == "lcall" and ins.op_str.startswith(RNG):
            n += 1
    return n


def test_the_roll_routine_is_dice_then_derivation():
    # The patch retargets a call into the middle of this routine, so the split
    # has to be where we think: six rolls before it, none after.
    exe = Exe()
    assert rng_calls(exe, ROLL, DERIVE) == 6, "six attributes are rolled"

    end = next(i.address for i in exe.disasm(DERIVE, 300) if i.mnemonic == "ret")
    assert rng_calls(exe, DERIVE, end) == 0, "the derivation must roll nothing"

    # It opens with health, 25% of stamina, with no class test; the class
    # dispatch that follows is the magic points, which is the part that has to
    # be rerun when the class changes.
    first = next(iter(exe.disasm(DERIVE, 1)))
    assert first.mnemonic == "mov" and "si + 0x40" in first.op_str

    dispatch = next(i for i in exe.disasm(DERIVE, 20)
                    if i.mnemonic == "cmp" and "si + 0xe" in i.op_str)
    stored_health = next(i for i in exe.disasm(DERIVE, 20)
                         if i.mnemonic == "mov" and i.op_str.startswith("word ptr [si + 0x52]"))
    assert stored_health.address < dispatch.address, "health does not depend on class"


def test_keep_roll_sits_on_the_class_pick_handler():
    exe = Exe()
    # The class is stored just above the call: [si+0x0e] is the class field.
    store = next(i for i in exe.disasm(0x140E2, 1))
    assert store.mnemonic == "mov" and "si + 0xe" in store.op_str

    call = next(i for i in exe.disasm(0x140FB, 1))
    assert call.mnemonic == "call" and call.op_str == hex(ROLL)


def test_keep_roll_retargets_the_call_past_the_dice(tmp_path):
    out = tmp_path / "REGISTER.EXE"
    patch.apply(["keep-roll-on-class-change"], patch.Path("game/REGISTER.EXE"), out)
    patched = Exe(out)

    ins = next(i for i in patched.disasm(0x140FB, 1))
    assert ins.mnemonic == "call"
    assert ins.op_str == hex(DERIVE), "must enter the routine past the rolls"
    assert ins.size == 3, "same encoding length, so nothing downstream shifts"

    # The derivation call that follows has to survive: it is what recomputes
    # the twelve skills for the new class.
    after = next(i for i in patched.disasm(0x140FE, 1))
    assert after.mnemonic == "call" and after.op_str == "0x13af3"


def test_the_other_two_callers_still_roll(tmp_path):
    # Roll Attributes, and setting up a new character, must be left alone --
    # a character that can never be rolled at all would be a worse bug.
    out = tmp_path / "REGISTER.EXE"
    patch.apply(["keep-roll-on-class-change"], patch.Path("game/REGISTER.EXE"), out)
    patched = Exe(out)

    for site in (0x14751, 0x14DA3):
        ins = next(i for i in patched.disasm(site, 1))
        assert ins.mnemonic == "call" and ins.op_str == hex(ROLL), hex(site)


def test_apply_refuses_when_the_original_byte_is_wrong(tmp_path):
    import pytest

    src = tmp_path / "wrong.exe"
    data = bytearray(Exe().data)
    data[HEADER + 0x37] = 0x00
    src.write_bytes(bytes(data))
    # expect_src_md5=None so this reaches the check it is about: a corrupted
    # source fails the digest first, which is a different guard.
    with pytest.raises(SystemExit, match="expected 7f"):
        patch.patched_bytes(["enable-p-switch"], src, expect_src_md5=None)


# --- rebuilding ------------------------------------------------------------
#
# `make serve` builds the patched game directory every time it serves, so the
# build has to be cheap and repeatable: confirm the patches are already in
# place and do nothing, rather than rewrite the executable and re-copy 17 MB of
# artwork. These hold that behavior, and the property it depends on, that
# patching does not need a disassembler.

DEFAULTS = ["force-skip-intro", "no-attract", "keep-roll-on-class-change"]


def test_verify_recognizes_a_build_it_just_made(tmp_path):
    out = tmp_path / "REGISTER.EXE"
    assert patch.verify(DEFAULTS, out) is False, "nothing there yet"
    patch.apply(DEFAULTS, patch.Path("game/REGISTER.EXE"), out)
    assert patch.verify(DEFAULTS, out) is True


def test_verify_rejects_a_build_missing_one_of_the_patches(tmp_path):
    out = tmp_path / "REGISTER.EXE"
    patch.apply(["no-attract", "keep-roll-on-class-change"], patch.Path("game/REGISTER.EXE"), out)
    assert patch.verify(DEFAULTS, out) is False
    assert patch.verify(["no-attract", "keep-roll-on-class-change"], out) is True


def test_verify_rejects_the_stock_executable():
    assert patch.verify(DEFAULTS, patch.Path("game/REGISTER.EXE")) is False


def test_verify_rejects_damage_away_from_the_patch_sites(tmp_path):
    # The reason the whole file is hashed. All three patch sites are still
    # exactly right here; one unrelated byte is not.
    out = tmp_path / "REGISTER.EXE"
    patch.apply(DEFAULTS, patch.Path("game/REGISTER.EXE"), out)
    data = bytearray(out.read_bytes())
    elsewhere = 0x30000
    assert all(not (p.file_offset <= elsewhere < p.file_offset + len(p.original))
               for p in (patch.PATCHES[n] for n in DEFAULTS))
    data[elsewhere] ^= 0xFF
    out.write_bytes(bytes(data))

    assert patch.verify(DEFAULTS, out) is False


def test_verify_rejects_a_truncated_build(tmp_path):
    out = tmp_path / "REGISTER.EXE"
    patch.apply(DEFAULTS, patch.Path("game/REGISTER.EXE"), out)
    out.write_bytes(out.read_bytes()[:200_000])

    assert patch.verify(DEFAULTS, out) is False


def test_the_recorded_digests_match_what_patching_produces(tmp_path):
    # BUILD_MD5 is written down, so it can fall out of step with the patches.
    # This is what stops that: every recorded digest has to be the digest of
    # the build it names, computed from the executable in game/.
    for names, recorded in patch.BUILD_MD5.items():
        assert patch.expected_md5(list(names)) == recorded, names


def test_the_recorded_source_digest_is_the_executable_in_game():
    assert patch.md5(patch.SRC_EXE.read_bytes()) == patch.SRC_MD5


def test_patching_refuses_a_source_that_is_not_the_release(tmp_path):
    # The check a derived digest cannot make. Every patch site still holds the
    # byte it expects here: the file is simply not the one the offsets were
    # read from, and one byte elsewhere proves it.
    import pytest

    src = tmp_path / "other-release.exe"
    data = bytearray(Exe().data)
    data[0x30000] ^= 0xFF
    src.write_bytes(bytes(data))
    with pytest.raises(SystemExit, match="not safe to apply"):
        patch.apply(DEFAULTS, src, tmp_path / "out.exe")


def test_check_names_the_patch_that_is_missing(tmp_path):
    # What a digest on its own cannot say. Two of the three are in place.
    out = tmp_path / "REGISTER.EXE"
    patch.apply(["no-attract", "keep-roll-on-class-change"],
                patch.Path("game/REGISTER.EXE"), out)

    problems = patch.check(DEFAULTS, out)
    assert any("force-skip-intro" in p for p in problems), problems
    assert any("md5" in p for p in problems), problems
    assert not any("no-attract" in p for p in problems), problems


def test_an_unrecorded_combination_is_checked_on_its_patch_sites(tmp_path):
    # No digest is recorded for a one-patch build, so the byte check is all
    # there is, and it still has to work.
    out = tmp_path / "REGISTER.EXE"
    assert patch.recorded_md5(["no-attract"]) is None
    patch.apply(["no-attract"], patch.Path("game/REGISTER.EXE"), out)
    assert patch.verify(["no-attract"], out) is True
    assert patch.verify(["force-skip-intro"], out) is False


def test_rebuilding_leaves_the_executable_untouched(tmp_path):
    out = tmp_path / "game"
    patch.build_game_dir(DEFAULTS, patch.Path("game"), out)
    exe = out / "REGISTER.EXE"
    first = exe.read_bytes()
    stamp = exe.stat().st_mtime_ns

    patch.build_game_dir(DEFAULTS, patch.Path("game"), out)
    assert exe.read_bytes() == first
    assert exe.stat().st_mtime_ns == stamp, "the executable was rewritten"


def test_rebuilding_keeps_files_that_exist_only_in_the_build(tmp_path):
    out = tmp_path / "game"
    patch.build_game_dir(DEFAULTS, patch.Path("game"), out)
    save = out / "SAVGAME1"
    save.write_bytes(b"a save the game wrote")

    patch.build_game_dir(DEFAULTS, patch.Path("game"), out)
    assert save.read_bytes() == b"a save the game wrote"


def test_rebuilding_repairs_a_build_whose_executable_went_missing(tmp_path):
    out = tmp_path / "game"
    patch.build_game_dir(DEFAULTS, patch.Path("game"), out)
    (out / "REGISTER.EXE").unlink()

    patch.build_game_dir(DEFAULTS, patch.Path("game"), out)
    assert patch.verify(DEFAULTS, out / "REGISTER.EXE")


def test_patching_does_not_need_a_disassembler():
    # capstone is needed to read the game, not to patch it. Keeping it out of
    # this path is what lets `make serve` run on a machine that only has the
    # standard library.
    import subprocess
    import sys

    src = "import sys; sys.path.insert(0, 'tools'); import patch; " \
          "print('capstone' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr
