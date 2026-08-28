"""The EXE label run is the naming authority for the binary tables, so the
enumerations in labels.py must stay in sync with the bytes in the file."""
import labels as L


def test_every_declared_label_is_in_the_exe(directory):
    assert L.verify(directory.exe) == []


def test_effect_bit_names_are_the_documented_twelve(directory):
    assert len(L.EFFECTS) == 12
    assert L.EFFECTS[0] == "POISON"
    assert L.EFFECTS[-1] == "PHYSICAL DAMAGE"


def test_effects_appear_in_the_exe_in_declared_order(directory):
    """The bit order of the immunity masks is the order the captions appear in
    the executable, so their offsets must ascend in the same sequence."""
    idx = L.label_index(directory.exe)
    offs = []
    for name in L.EFFECTS:
        hit = next(o for text, o in idx.items() if text.rstrip(":-") == name)
        offs.append(hit)
    assert offs == sorted(offs)


def test_class_tiers(directory):
    assert len(L.CLASS_TIERS) == 6
    assert all(len(t) == 3 for t in L.CLASS_TIERS)
    assert ("MAGE", "WIZARD", "SORCERER") in L.CLASS_TIERS


def test_menu_has_six_restoration_sections(directory):
    assert len(L.RESTORATION_MENU) == 6
    assert L.RESTORATION_MENU[1].endswith("MONSTER STATISTICS")
