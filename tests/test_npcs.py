"""The three conversation tables, and what fixes each reading.

None of this is on a clue-book page, so the checks here are the data's own
arithmetic and the prose the reading makes an NPC speak. Three things hold the
record sizes: 141 x 40, 1,073 x 60 and 4,090 x 34 each divide a run of
sections exactly. Two more hold the field meanings: an NPC's topic and prose
blocks are running totals, so the blocks tile with nothing between them, and
every block opens on a greeting and closes on a farewell while the prose read at
the offset a topic names has its quotation marks paired on 953 of the 955
responses that carry any.
"""
import collections
import struct

import items as IT
import labels as L
import npcs as N


def _w(buf, at):
    return struct.unpack_from("<H", buf, at)[0]


def test_the_three_tables_divide_their_sections_exactly(directory):
    """The section directory lists five, and two of the three tables straddle a
    boundary: 47,400 + 16,980 is 1,073 x 60 and 51,034 + 51,000 + 37,026 is
    4,090 x 34."""
    s = directory.sections
    assert s[N.NPCS].size == N.NPC_COUNT * N.NPC_RECORD
    assert s[22].size + s[23].size == N.TOPIC_COUNT * N.TOPIC_RECORD
    assert s[24].size + s[25].size + s[26].size == N.PROSE_COUNT * N.PROSE_RECORD


def test_the_blocks_each_record_names_are_running_totals(people):
    """`+0x08` and `+0x0A` are the first topic and the first prose line, and
    `+0x04` and `+0x06` are the counts. Adding a record's count to its start
    gives the next record's start on 139 of the 140 consecutive pairs."""
    for field, count in ((N.FIRST_TOPIC, N.TOPIC_COUNT_AT),
                         (N.FIRST_PROSE, N.PROSE_COUNT_AT)):
        runs = sum(1 for a, b in zip(people.npcs, people.npcs[1:])
                   if _w(a, field) + _w(a, count) == _w(b, field))
        assert runs == 139


def test_every_topic_belongs_to_one_npc(people):
    """The blocks partition the table: no topic is claimed twice and 1,072 of
    the 1,073 are claimed at all. The one left over is the first, which holds a
    blank keyword."""
    claimed = collections.Counter(t for n in range(N.NPC_COUNT)
                                  for t in people.topic_block(n))
    assert max(claimed.values()) == 1
    assert sorted(claimed) == list(range(2, N.TOPIC_COUNT + 1))
    assert not N._text(people.topics[0][:N.KEYWORD])


def test_both_blocks_are_0_based(people):
    """`+0x08` and `+0x0A` are both 0-based, so a topic is `first + 1 + n` and a
    response starts at `first + offset / 34 + 1`.

    Two counts fix that. Every one of the 140 topic blocks then opens on a topic
    no menu lists, which is the NPC's greeting, and closes on one carrying a
    close or a leave bit, which is its farewell; read a record earlier only 3
    and 35 of them do. And the quotation marks, which the game writes as `%`,
    pair on 953 of the 955 responses that carry any.
    """
    greeted = parted = 0
    for n in range(1, N.NPC_COUNT):
        block = list(people.topic_block(n))
        if not block:
            continue
        head, tail = people.topics[block[0] - 1], people.topics[block[-1] - 1]
        greeted += not any(_w(head, off) for off in N.SHOWN_IF)
        parted += bool(_w(tail, N.ACTION_WORD) & 0x0005)
    assert (greeted, parted) == (140, 140)

    paired = total = 0
    for t in range(1, N.TOPIC_COUNT + 1):
        lines = people.response_lines(t)
        if not lines:
            continue
        total += 1
        paired += "".join(lines).count(L.QUOTE) % 2 == 0
    assert (paired, total) == (953, 955)


def test_the_armorer_block_tiles(people):
    """NPC 31's seven responses: each ends where the next begins."""
    runs = sorted((_w(people.topics[t - 1], N.PROSE_AT) // N.PROSE_RECORD,
                   _w(people.topics[t - 1], N.PROSE_LINES))
                  for t in people.topic_block(31)
                  if _w(people.topics[t - 1], N.PROSE_LINES))
    assert runs == [(0, 2), (2, 5), (7, 2), (9, 3), (12, 3), (15, 2), (17, 3)]
    assert all(a[0] + a[1] == b[0] for a, b in zip(runs, runs[1:]))


def test_every_shop_and_reward_names_a_real_bundle(people):
    """A buy or a reward topic's selector is a 1-based bundle in section 10,
    the same table a container on a cell names. All 48 land in range and every
    one holds at least one item or one count."""
    found = [people.stock_bundle(t) for t in range(1, N.TOPIC_COUNT + 1)]
    held = [b for b in found if b]
    assert len(held) == 48
    for bundle in held:
        assert any(bundle["items"]) or any(bundle["counts"].values())


def test_seven_rewards_hand_over_a_door_key(people):
    """The seven metals have one DOOR KEY each, and seven reward bundles hand
    one over. That is what ties a reward to the gates it opens."""
    keys = set(range(N.LO.DOOR_KEY, N.LO.DOOR_KEY + len(N.LO.METALS)))
    given = set()
    for t in range(1, N.TOPIC_COUNT + 1):
        bundle = people.stock_bundle(t)
        if bundle:
            given |= keys & set(bundle["items"])
    assert given == keys


def test_the_sell_masks_are_the_item_records_word_16(directory, people):
    """Image 0x047D3 tests a sell topic's selector against the item record's
    word 16. That word partitions all 631 items into eight classes plus the
    163 no shop deals in, and the 17 sell topics name exactly those eight."""
    items = IT.Items(directory)
    classes = collections.Counter(_w(r, N.CLASS_AT) for r in items.records)
    assert set(classes) - {0} == set(N.MERCHANT_CLASSES)
    assert classes[0] == 163
    named = {_w(people.topics[t - 1], N.SELECTOR)
             for t in range(1, N.TOPIC_COUNT + 1)
             if "sell" in people.action_of(t)[0]}
    assert named == set(N.MERCHANT_CLASSES)


def test_a_commodity_topic_names_food_or_nuore(people):
    """The selector is the item id, and the two a shop sells by the unit are
    FOOD and NUORE. The other thirteen carry a quantity's own item."""
    sold = collections.Counter(people.commodity_item(t)
                              for t in range(1, N.TOPIC_COUNT + 1)
                              if people.commodity_item(t))
    assert sold[2] == 3 and sold[3] == 3
    assert max(sold) <= len(people.items.names)


def test_the_flag_numbers_fit_the_bank(people):
    """The 14 words from DS:0xCFAF are 224 bits, numbered from 1. Every flag a
    topic tests or writes falls inside that, and 383 topics carry one."""
    carried = 0
    for t in range(1, N.TOPIC_COUNT + 1):
        flags = people.flags_tested(t) + people.flags_written(t)
        carried += bool(flags)
        for f in flags:
            assert 1 <= abs(f) <= N.FLAG_BITS
    assert carried == 383


def test_the_armorer_gates_his_shop_on_one_flag(people):
    """PAY 3,000 is offered while flag 63 is clear and sets it. BUY ARMOR, SELL
    ITEMS and FINISHED each want it set. That is the whole of hiring a
    blacksmith, and the prose says the same. Which greeting opens the
    conversation is a flag too: `+0x0C` is 51 and `+0x0E` is 63, so the three
    are before the offer, at it, and after it."""
    by_name = {N._text(people.topics[t - 1][:N.KEYWORD]): t
               for t in people.topic_block(31)}
    assert people.flags_tested(by_name["PAY 3,000"]) == [-63]
    assert people.flags_written(by_name["PAY 3,000"]) == [63]
    for name in ("BUY ARMOR", "SELL ITEMS", "FINISHED"):
        assert people.flags_tested(by_name[name]) == [63]
    assert "3,000 GOLD COINS" in people.said_line(by_name["HELLO-2"])
    assert people.npc_record(31)["opensOnFlags"] == [51, 63, 0]


def test_a_topic_is_shown_under_one_bit(people):
    """`+0x18` and `+0x1A` are a 32-bit pair, and a topic carries at most one
    bit in each word: image 0x090AE tests the two separately and a topic with
    neither is never listed."""
    for t in range(1, N.TOPIC_COUNT + 1):
        for off in N.SHOWN_IF:
            word = _w(people.topics[t - 1], off)
            assert word & (word - 1) == 0, f"topic {t} shows under {word:#06x}"


def test_139_of_the_141_records_stand_on_a_cell(people):
    """A cell event of kind 0x1000 is the only placement, and each NPC stands
    in one place. Records 0 and 140 stand nowhere."""
    assert len(people.placed) == 139
    assert all(len(where) == 1 for where in people.placed.values())
    assert 0 not in people.placed and 140 not in people.placed


def test_the_wishing_well_raises_mapping_for_the_party(people):
    """NPC 7: 100 gold sets flag 3, which offers ENHANCEMENT, which adds 3 to
    MAPPING. Its own prose says everyone is better able to find their way
    around, which is what fixes `+0x14` as a live-block offset."""
    info = people.npc_record(7)
    assert (info["raisesWordName"], info["raisesBy"]) == ("MAPPING", 3)
    by_name = {N._text(people.topics[t - 1][:N.KEYWORD]): t
               for t in people.topic_block(7)}
    assert people.flags_written(by_name["GIVE 100 GOLD"]) == [3]
    assert people.flags_tested(by_name["ENHANCEMENT"]) == [3]
    assert _w(people.topics[by_name["GIVE 100 GOLD"] - 1], N.GOLD_PRICE) == 100
    assert "FIND THEIR WAY AROUND" in people.said_line(by_name["ENHANCEMENT"])


def test_fourteen_npcs_raise_one_stat_once_per_character(people):
    """`+0x1A` is a per-character bit index into the character record at offset
    202, and the fourteen that carry one hold 1 to 14 with no repeat. Each
    names a maximum-block stat at `+0x14`, a ceiling at `+0x16` and a flat
    price at `+0x1C`."""
    found = [people.npc_record(n) for n in range(N.NPC_COUNT)]
    once = [i for i in found if i["challengeBit"]]
    assert sorted(i["challengeBit"] for i in once) == list(range(1, 15))
    for info in once:
        assert info["challengeWordName"], f"NPC {info['npcNumber']} names no stat"
        assert info["challengeRaisesTo"] > 0 and info["flatPrice"] > 0


def test_the_attribute_service_names_a_live_block_word(people):
    """The table of 13-byte strings at DS:0x80F4 has one name per word of the
    live block, and every attribute NPC's `+0x14` indexes a named one."""
    assert people.live_names[0] == "STRENGTH"
    assert people.live_names[22] == "BARTERING"
    assert len(people.live_names) == N.LIVE_WORDS
    for n in range(N.NPC_COUNT):
        info = people.npc_record(n)
        if "attribute" in info["servicesOffered"]:
            assert info["raisesWordName"], f"NPC {n} raises {info['serviceWords'][0]}"


def test_the_five_trainers_cover_the_ladder(people):
    """The ceilings are 10, 20, 25, 30 and 40 against factors of 5 and 10."""
    through = sorted(people.trains_through(n) for n in range(N.NPC_COUNT)
                     if people.trains_through(n))
    assert through == [10, 20, 25, 30, 40]


def test_the_haggle_bands(people):
    """Image 0x0A692 picks a margin from the barterer's bartering skill, and a
    skill over 999 haggles as badly as one under 55."""
    assert [people.haggle_margin(s) for s in (0, 54, 55, 64, 79, 100, 124, 149, 999)] \
        == [55, 55, 45, 45, 35, 25, 15, 8, 2]
    assert people.haggle_margin(1000) == 55


def test_a_price_is_the_items_own_value_scaled(people):
    """KNIFE is 45 and RING OF INVISIBILITY is 3,000, both packed BCD at record
    offset 5. A buy adds the margin and a sale takes it off, rounded half up."""
    knife = people.items.names.index("KNIFE") + 1
    assert people.items.value(people.items.records[knife - 1]) == 45
    assert people.shop_buy_price(knife, 0) == 70        # 45 x 155% = 69.75
    assert people.shop_sell_price(knife, 0) == 20       # 45 x 45% = 20.25
    assert people.shop_buy_price(knife, 999) == 46      # 45 x 102% = 45.9
    assert people.shop_sell_price(knife, 999) == 44     # 45 x 98% = 44.1


def test_an_enhancement_is_the_next_item_id(people):
    """Image 0x045A8 writes `id + 1` into the place, so a series runs
    consecutively and the price is the next form's own worth."""
    base = people.items.names.index("CLOTHES") + 1
    assert people.items.names[base] == "CLOTHES +1"
    value = people.items.value(people.items.records[base])
    assert people.enhance_price(base, 50) == people.scale_by_percent(value, 50)


def test_the_condition_prices_sum_over_the_bits(people):
    """Image 0x092B1 adds one figure per condition bit set in word 28."""
    assert people.cure_price(0) == 0
    assert people.cure_price(0x8000) == 5
    assert people.cure_price(0x8000 | 0x0400) == 65
    assert people.cure_price(N.CURABLE) == 275


def test_a_body_service_is_priced_per_level(people):
    """Image 0x091EB multiplies the unit price by the NPC's factor and then by
    the character's level."""
    who = {"level": 5, "conditions": 0x8000, "health": 10, "most_health": 20}
    assert people.body_price("health", who, 4) == 20 * 4 * 5
    assert people.body_price("life", who, 4) == 100 * 4 * 5
    assert people.body_price("conditions", who, 4) == 5 * 4 * 5
    assert people.body_price("everything", who, 4) == (5 + 20) * 4 * 5


def test_a_portal_guard_asks_rather_than_sells(people):
    """Eleven commodity topics are questions: image 0x02B3E sends a keyword that
    does not begin "BUY " to the riddle at 0x05738, which answers against the
    table at DS:0xA8C6. Each guard is gated on the flag his own question writes."""
    answers = people.riddle_answers()
    assert answers[0] == "PEACEFUL"
    asking = [t for t in range(1, N.TOPIC_COUNT + 1)
              if "commodity" in N.People.action_of(people, t)[0]
              and not N._text(people.topics[t - 1][:N.KEYWORD]).startswith("BUY ")]
    assert len(asking) == len(answers)
    assert [N._w(people.topics[t - 1], N.SELECTOR) for t in asking] == \
        list(range(1, len(answers) + 1))
    guard = people.npc_record(86)
    assert guard["goneIfFlag"] == people.flags_written(asking[0])[0] == 128
