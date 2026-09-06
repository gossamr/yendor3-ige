"""The people the maps place, what they say, and what they sell.

Three tables in `WORLD.DAT`, which the section directory lists as five because
two of them straddle a boundary ([shops.md](../docs/shops.md)):

* **section 21**, 141 NPC records of 40 bytes. A record names a portrait, the
  block of conversation topics and the block of prose lines that belong to it,
  and the parameters of whatever service it offers.
* **sections 22 and 23**, 1,073 conversation topics of 60 bytes. A topic is a
  keyword, an action word naming the service it opens, and the bookkeeping that
  decides when it is offered and what picking it changes.
* **sections 24 to 26**, 4,090 prose lines of 34 bytes: 33 characters and a
  NUL. A topic names a byte offset into its NPC's block and how many lines the
  response runs to.

A cell event of kind `0x1000` puts an NPC on a cell, and its argument is the
record's own index ([map.md](../docs/map.md)). That is the only placement.

    python tools/npcs.py                  # a summary of all three tables
    python tools/npcs.py --npc 31         # one NPC, its topics and its prose
    python tools/npcs.py --shops          # every shop, with what it stocks
    python tools/npcs.py --services       # every NPC by the service it offers
    python tools/npcs.py --flags          # which topic sets or tests which flag
"""

from __future__ import annotations

import argparse
import struct
from collections import defaultdict

import items as IT
import labels as LB
import loot as LO
import saves as SV
import sections as S
from links import events

NPCS, NPC_RECORD, NPC_COUNT = 21, 40, 141
TOPICS, TOPIC_RECORD, TOPIC_COUNT = 22, 60, 1073
PROSE, PROSE_RECORD, PROSE_COUNT = 24, 34, 4090

# The keyword, NUL padded, and the line of prose, the same way.
KEYWORD = 13
PROSE_COLS = 33

# The NPC record. Every field is a word.
#
# `+0x0C` and `+0x0E` pick which topic a conversation opens on: image 0x0A31A
# tests each as a quest flag, highest first, and takes topic 3 or 2 where one
# holds, otherwise topic 1. `+0x10` would name topic 4 and is zero on all 141.
#
# `+0x14` and `+0x16` are read differently per service, which is why they are
# carried raw and interpreted under `service` below.
NPC_PORTRAIT_AT = 0x00
KIND_AT = 0x02
TOPIC_COUNT_AT = 0x04
PROSE_COUNT_AT = 0x06
FIRST_TOPIC = 0x08
FIRST_PROSE = 0x0A
OPENS_ON = (0x0C, 0x0E, 0x10)
ONE_SHOT = 0x12
SERVICE_WORDS = (0x14, 0x16)
PRICE_FACTOR = 0x18
CHALLENGE_BIT_AT = 0x1A
FLAT_PRICE = 0x1C
WANTS_ITEM = 0x20
GONE_IF = 0x22

# The topic record.
ACTION_WORD = 0x0E
GOLD_PRICE = 0x10
SELECTOR = 0x12
PROSE_AT = 0x14
PROSE_LINES = 0x16
# `+0x14` is a prose offset on 1,055 of the 1,073 records and a flight's own bit
# on the other 18, which are the three stables' BUY and SELL topics. Image
# 0x19338 walks the transport table by that bit, and a bit is not a multiple of
# 34, so the two readings cannot be confused.
FLIGHT_BITS = (0x8000, 0x4000, 0x2000, 0x1000)
SHOWN_IF = (0x18, 0x1A)
TURNS_ON = (0x1C, 0x1E)
TURNS_OFF = (0x20, 0x22)
# Six signed flag numbers the topic is conditional on, and six it writes.
TESTS_AT, WRITES_AT, FLAG_SLOTS = 0x24, 0x30, 6

# The action word's bits, as the dispatch from image 0x02B26 to 0x02C8F reads
# them. The first eleven name a service and the rest are flow.
SERVICES = {
    0x8000: "buy",          # 0x06082, stock is a bundle the selector names
    0x4000: "sell",         # 0x063CF, the selector is a merchant class mask
    0x2000: "pay",          # 0x0931E, hand over gold or an item
    0x1000: "reward",       # 0x0A548, a bundle handed over for nothing
    0x0800: "body",         # 0x0A3B9, acts on one character
    0x0400: "experience",   # 0x08E79, a BCD award to every able character
    0x0200: "attribute",    # 0x08D3E, raises one word of the live block
    0x0100: "enhance",      # 0x06259, one step along an item's own series
    0x0080: "commodity",    # 0x060D3, food or nuore by the unit
    0x0040: "repair",       # 0x0631E, a broken weapon or shield made whole
    0x0008: "transport",    # 0x09F4E, selling the party a flight
}
# The five flow bits. `leaves` ends the conversation: image 0x02BD8 sends a
# topic carrying it to 0x02E89, which frees the NPC's two buffers and returns.
# `closes` and `shuts` are the pair that close a screen inside one instead.
FLOW = {
    0x0020: "opens",        # a list beside a buy, a sell or a reward
    0x0010: "closes",       # restores the state the matching `opens` saved
    0x0004: "shuts",        # DONE, FINISHED, CLOSE
    # Its flags are written only where the last service did what it was asked:
    # image 0x09442 tests this bit and then DS:0x536C's 0x40, which a payment,
    # an item handed over and a right answer each set. 104 topics carry it.
    0x0002: "flagsOnSuccess",
    0x0001: "leaves",       # GOODBYE, BYE, LEAVE, and every greeting
}

# The riddle a portal guard asks, and the two things it answers.
#
# A commodity topic whose keyword does not begin "BUY " is not an order at all:
# image 0x02B3E tests those four characters and sends the rest to image 0x05738,
# which prints the topic's prose as a question, takes 34 characters (image
# 0x0BDAC) and compares them against this table, indexed by the topic's own
# selector. A match sets DS:0x536C's 0x40, which is what lets the topic write
# its quest flag.
ANSWERS_AT = 0xA8C6
ANSWER_RIGHT_AT = 0x8743
ANSWER_WRONG_AT = 0x8730
ANSWER_LENGTH = 0x22

# The four screens a service opens, and the mode bit each sets in DS:0x536C.
# Image 0x11172 reads those bits to caption the price.
PANEL_MODES = {"buy": 0x20, "sell": 0x10, "enhance": 0x08, "repair": 0x04}

# What a merchant class is worth as a name. The mask is the item record's word
# 16, which partitions all 631 items and which a sell topic's selector is
# tested against at image 0x047D3. Named for what the class holds.
MERCHANT_CLASSES = {
    0x8000: "gear", 0x4000: "potions", 0x2000: "tools", 0x0800: "jewels",
    0x0200: "dwarf goods", 0x0100: "elf goods", 0x0080: "the Order's plate",
    0x0020: "ore",
}
CLASS_AT = 16

# The body service's own selector, at image 0x09825 and 0x099B4. A service
# topic carries one of the first four and a follow-up carries `agrees` or
# `declines`, which is how a quote becomes a purchase.
BODY_SERVICES = {0x8000: "health", 0x4000: "conditions", 0x2000: "life",
        0x1000: "everything", 0x0800: "stat"}
BODY_STAT = 0x0800
AGREES, DECLINES = 0x02, 0x04

# What each service charges per unit, at the four quote sites the handlers
# reach. A condition price is the sum over the bits set, below.
HEAL_PER_LEVEL = 0x14           # image 0x099A9
RESURRECT_PER_LEVEL = 0x64      # image 0x09992
RESTORE_HEALTH = 0x14           # image 0x0997C, on top of the conditions
RESTORE_HELD = 0x64             # image 0x09987
# A unit of food or a unit of nuore, and the smallest order the screen takes.
# Both are in the prompts at DS:0x84B3 and DS:0x8372 rather than in a table.
COMMODITY_EACH, COMMODITY_LEAST = 10, 10

# What removing one condition costs, by the bit in the character record's word
# 28, at image 0x092B1. The nine are in the order [monsters.md](monsters.md)
# lists them.
CONDITION_PRICE = {0x8000: 5, 0x4000: 10, 0x2000: 20, 0x1000: 40, 0x0800: 50,
                   0x0400: 60, 0x0200: 20, 0x0100: 30, 0x0080: 40}
# The condition a restoration charges RESTORE_HELD for, and the nine a cure
# prices. Image 0x08FC6 reads both.
HELD = 0x0040
CURABLE = 0xFF80

# How far a price moves for the haggling, by the barterer's bartering skill at
# character record offset 104. Image 0x0A692 walks the bands and the margin it
# lands on is added for a purchase and taken off for a sale. The last band is
# the first one's figure again, so a skill over 999 haggles as badly as a
# beginner.
HAGGLE = ((0x36, 55), (0x40, 45), (0x4F, 35), (0x64, 25), (0x7C, 15),
          (0x95, 8), (0x3E7, 2))
HAGGLE_OVER = 55
BARTERING_AT = 104

# The live block's 26 words, named by the table of 13-byte strings at
# DS:0x80F4, which image 0x08D85 indexes by `(offset - 60) / 2`. An attribute
# service names one of these at `+0x14` of its record.
LIVE_NAMES = 0x80F4
LIVE_NAME_LEN = 13
LIVE_AT, LIVE_WORDS = 60, 26
# The same words again, holding the maximum. A stat service names one of these,
# and the table at DS:0x5708 gives it a name: (record offset, string) pairs,
# ending at a zero key.
MAX_AT = 124
STAT_NAMES_AT = 0x5708
STAT_NAME_RECORD = 4

# What a raised word is clamped to, at image 0x08E56: health and magic take
# four digits and everything else takes three.
CAP, CAP_POOL = 999, 9999
POOL_WORDS_AT = (0x52, 0x54)

# The quest flags a topic sets, tests and clears. Image 0x17AFE resolves a
# 1-based bit number against the 14 words from DS:0xCFAF, high bit first, and
# the roster carries the last thirteen of them at header 212
# ([saves.md](../docs/saves.md)).
FLAG_WORDS, FLAG_BITS = 14, 14 * 16

# The cell event kind that stands an NPC on a cell. Records 0 and 140 stand
# nowhere, so 139 of the 141 are reachable.
PERSON = "person"


def _w(buf: bytes, at: int) -> int:
    return struct.unpack_from("<H", buf, at)[0]


def _sw(buf: bytes, at: int) -> int:
    return struct.unpack_from("<h", buf, at)[0]


def _text(buf: bytes) -> str:
    return LB.text(buf)


def _ds(exe: bytes, at: int, length: int) -> bytes:
    return IT._ds(exe, at, length)


class People:
    """All three tables, plus what the placements and the items say about them."""

    def __init__(self, d: S.Directory):
        self.d = d
        self.items = IT.Items(d)
        self.npcs = self._records(NPCS, NPC_RECORD, NPC_COUNT)
        self.topics = self._records(TOPICS, TOPIC_RECORD, TOPIC_COUNT)
        self.prose = self._records(PROSE, PROSE_RECORD, PROSE_COUNT)
        self.live_names = [
            _text(_ds(d.exe, LIVE_NAMES + i * LIVE_NAME_LEN, LIVE_NAME_LEN))
            for i in range(LIVE_WORDS)]
        self.stat_names = self._stat_names()
        self.placed = self._placed()
        self.verify()

    def _records(self, section: int, size: int, count: int) -> list[bytes]:
        """One section's records, whatever later sections the run spills into."""
        at = self.d.sections[section].offset
        assert at + size * count <= len(self.d.world)
        return [self.d.world[at + n * size: at + (n + 1) * size]
                for n in range(count)]

    def _stat_names(self) -> dict[int, str]:
        """Record offset to stat name, off the table at DS:0x5708."""
        out, at = {}, STAT_NAMES_AT
        while (key := _w(_ds(self.d.exe, at, 2), 0)):
            out[key] = _text(_ds(self.d.exe, _w(_ds(self.d.exe, at + 2, 2), 0), 24))
            at += STAT_NAME_RECORD
        return out

    def _placed(self) -> dict[int, list[tuple[int, int]]]:
        """Every cell each NPC stands on."""
        out: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for e in events(self.d):
            if e["kind"] == PERSON:
                out[e["arg"]].append((e["x"], e["y"]))
        return dict(out)

    def verify(self) -> None:
        """The arithmetic the three readings rest on."""
        for section, size, count, span in ((NPCS, NPC_RECORD, NPC_COUNT, 1),
                                           (TOPICS, TOPIC_RECORD, TOPIC_COUNT, 2),
                                           (PROSE, PROSE_RECORD, PROSE_COUNT, 3)):
            held = sum(self.d.sections[section + n].size for n in range(span))
            assert held == size * count, (
                f"section {section} holds {held} bytes, not {size} x {count}")
        # The two blocks each record names are running totals of the two counts
        # it holds, so the blocks tile with nothing between them. It holds on
        # 139 of the 140 consecutive pairs; record 17 has no topics and its
        # successor restarts the run.
        for field, count in ((FIRST_TOPIC, TOPIC_COUNT_AT),
                             (FIRST_PROSE, PROSE_COUNT_AT)):
            runs = sum(1 for a, b in zip(self.npcs, self.npcs[1:])
                       if _w(a, field) + _w(a, count) == _w(b, field))
            assert runs >= len(self.npcs) - 2, f"{runs} running totals at {field:#x}"
        for n in self.placed:
            assert 0 < n < NPC_COUNT, f"cell event names NPC {n}"

    # -- one record at a time --

    def topic_block(self, n: int) -> range:
        """The 1-based topic numbers NPC `n` owns.

        `+0x08` is a 0-based index, the same as `+0x0A`, so the block runs from
        one past it. Read that way every one of the 140 blocks opens on a topic
        no menu lists, which is its greeting, and closes on one carrying a close
        or a leave bit, which is its farewell. Read a record earlier only 3 and
        35 of them do.
        """
        first, count = _w(self.npcs[n], FIRST_TOPIC), _w(self.npcs[n], TOPIC_COUNT_AT)
        return range(first + 1, first + 1 + count)

    def npc_of_topic(self, topic: int) -> int | None:
        """Which NPC owns a 1-based topic number."""
        return self._npc_by_topic.get(topic)

    @property
    def _npc_by_topic(self) -> dict[int, int]:
        if not hasattr(self, "_owner_map"):
            self._owner_map = {t: n for n in range(NPC_COUNT)
                               for t in self.topic_block(n)}
        return self._owner_map

    def response_lines(self, topic: int) -> list[str]:
        """The prose a topic answers with, as lines.

        The offset is a byte count into the owner's own block and the record it
        names is `first prose + offset / 34`, counted from one past the record
        `+0x0A` holds: the field is a 0-based index where `+0x08`, the topic
        block, is 1-based. The blocks then tile exactly. For the armorer at NPC
        31 the offsets are 0, 68, 238, 306, 408 and 510 against line counts of
        2, 5, 2, 3, 3 and 2, so each response ends where the next begins, and
        the quotation marks pair on 906 of the 954 responses that have any.
        """
        rec = self.topics[topic - 1]
        at, lines = _w(rec, PROSE_AT), _w(rec, PROSE_LINES)
        owner = self.npc_of_topic(topic)
        if owner is None or at % PROSE_RECORD or not lines:
            return []
        first = _w(self.npcs[owner], FIRST_PROSE) + at // PROSE_RECORD + 1
        if first < 1 or first + lines - 1 > PROSE_COUNT:
            return []
        return [_text(self.prose[n - 1]).ljust(PROSE_COLS)[:PROSE_COLS]
                for n in range(first, first + lines)]

    def said_line(self, topic: int) -> str:
        """A topic's response as one paragraph, the quote marks put back.

        The game draws each 33-character line on its own row and ends every row
        at a word boundary, so reflowing into a paragraph puts a space between
        rows. `%` becomes a quotation mark, opening and closing in turn
        (tools/labels.py).
        """
        joined = " ".join(self.response_lines(topic))
        return " ".join(LB.quoted(joined).split())

    def flags_tested(self, topic: int) -> list[int]:
        """The signed flag numbers a topic is conditional on.

        Image 0x090CA walks six words from `+0x24`: a positive number is a flag
        that has to be set and a negative one a flag that has to be clear.
        """
        return self._flag_slots(topic, TESTS_AT)

    def flags_written(self, topic: int) -> list[int]:
        """The signed flag numbers picking a topic writes, at image 0x09452."""
        return self._flag_slots(topic, WRITES_AT)

    def _flag_slots(self, topic: int, at: int) -> list[int]:
        rec = self.topics[topic - 1]
        found = [_sw(rec, at + 2 * i) for i in range(FLAG_SLOTS)]
        return [f for f in found if f]

    def action_of(self, topic: int) -> tuple[list[str], list[str]]:
        """A topic's services and its flow bits, by name."""
        word = _w(self.topics[topic - 1], ACTION_WORD)
        return ([name for bit, name in SERVICES.items() if word & bit],
                [name for bit, name in FLOW.items() if word & bit])

    def stock_bundle(self, topic: int) -> dict | None:
        """What a buy or a reward topic hands over.

        Both reach image 0x0252E with the topic's selector, which is the same
        1-based bundle in section 10 that a container on a cell names. So a
        shop's stock and a chest's contents are one table
        ([map.md](../docs/map.md)).
        """
        services, _ = self.action_of(topic)
        if not {"buy", "reward"} & set(services):
            return None
        n = _w(self.topics[topic - 1], SELECTOR)
        if not 1 <= n <= LO.BUNDLE_COUNT:
            return None
        return LO.bundle(self.d, n - 1)

    def buys_classes(self, topic: int) -> list[str]:
        """The merchant classes a sell topic deals in."""
        if "sell" not in self.action_of(topic)[0]:
            return []
        mask = _w(self.topics[topic - 1], SELECTOR)
        return [name for bit, name in MERCHANT_CLASSES.items() if mask & bit]

    def flight_index(self, topic: int) -> int:
        """Which flight a stable's topic is for, 0-based, or -1 for the rest."""
        at = _w(self.topics[topic - 1], PROSE_AT)
        return FLIGHT_BITS.index(at) if at in FLIGHT_BITS else -1

    def commodity_item(self, topic: int) -> int:
        """The item id a commodity topic sells by the unit, 0 for none."""
        if "commodity" not in self.action_of(topic)[0]:
            return 0
        return _w(self.topics[topic - 1], SELECTOR)

    # -- what an NPC does --

    def npc_record(self, n: int) -> dict:
        """One NPC's parameters, read the way the service it offers reads them.

        `+0x14` and `+0x16` hold different things per service, so the raw pair
        goes out alongside whichever reading applies.
        """
        rec = self.npcs[n]
        offered = sorted({s for t in self.topic_block(n)
                          for s in self.action_of(t)[0]})
        out = {
            "npcNumber": n,
            "portrait": _w(rec, NPC_PORTRAIT_AT),
            "kind": _w(rec, KIND_AT),
            "topicNumbers": list(self.topic_block(n)),
            "servicesOffered": offered,
            "priceFactor": _w(rec, PRICE_FACTOR),
            "serviceWords": [_w(rec, off) for off in SERVICE_WORDS],
            "oncePerGameFlag": _w(rec, ONE_SHOT) or None,
            "challengeBit": _w(rec, CHALLENGE_BIT_AT) or None,
            "goneIfFlag": _w(rec, GONE_IF) or None,
            "wantsItemId": _w(rec, WANTS_ITEM) or None,
            "opensOnFlags": [_w(rec, off) for off in OPENS_ON],
            "flatPrice": self.read_bcd(rec, FLAT_PRICE) or None,
            "standsAt": self.placed.get(n, []),
        }
        if "attribute" in offered:
            out["raisesWordName"] = self.live_name(_w(rec, SERVICE_WORDS[0]))
            out["raisesColumnKey"] = self.column_key(_w(rec, SERVICE_WORDS[0]), LIVE_AT)
            out["raisesBy"] = _w(rec, SERVICE_WORDS[1])
        if "enhance" in offered:
            out["enchantmentRange"] = [_w(rec, off) for off in SERVICE_WORDS]
        if "experience" in offered:
            out["experienceAwarded"] = self.read_bcd(rec, SERVICE_WORDS[0])
        if out["challengeBit"]:
            out["challengeWordName"] = self.stat_names.get(_w(rec, SERVICE_WORDS[0]))
            out["raisesColumnKey"] = self.column_key(_w(rec, SERVICE_WORDS[0]), MAX_AT)
            out["challengeRaisesTo"] = _w(rec, SERVICE_WORDS[1])
        train = self.trains_through(n)
        if train:
            out["trainsThroughLevel"] = train
        return out

    def riddle_answers(self) -> list[str]:
        """The eleven answers, in the order the selectors name them.

        The table is pointers and the strings sit behind it, so the first
        pointer is where the table ends and how many there are.
        """
        first = _w(_ds(self.d.exe, ANSWERS_AT, 2), 0)
        count = (first - ANSWERS_AT) // 2
        out = []
        for i in range(count):
            at = _w(_ds(self.d.exe, ANSWERS_AT + 2 * i, 2), 0)
            out.append(_text(_ds(self.d.exe, at, 32)))
        return out

    def trains_through(self, n: int) -> int:
        """The level this NPC will train a character through, 0 for none.

        A trainer is found by its topic's selector rather than its keyword:
        image 0x09059 turns on the bit a TRAIN topic is shown under whenever
        the character has a level owed, and `+0x16` of the record is the
        ceiling image 0x09D80 refuses above ([leveling.md](../docs/leveling.md)).
        """
        for t in self.topic_block(n):
            rec = self.topics[t - 1]
            if not _w(rec, ACTION_WORD) and _w(rec, SELECTOR) == BODY_STAT:
                return _w(self.npcs[n], SERVICE_WORDS[1])
        return 0

    @staticmethod
    def column_key(offset: int, base: int) -> str | None:
        """Which word of a stat column a record offset names.

        The two blocks hold the same 26 words, so the name is the offset less
        whichever block it is in ([saves.md](../docs/saves.md)).
        """
        return SV.column_fields().get(offset - base)

    def live_name(self, offset: int) -> str | None:
        """What the live-block word at a record offset is called."""
        if not LIVE_AT <= offset < LIVE_AT + 2 * LIVE_WORDS or offset % 2:
            return None
        return self.live_names[(offset - LIVE_AT) // 2] or None

    # -- prices --

    @staticmethod
    def read_bcd(rec: bytes, at: int) -> int:
        """The four packed BCD bytes at a record offset, most significant first.

        The game's money is this shape everywhere: the purse at DS:0xCF91, an
        item's value at record `+4`, and the flat price an NPC quotes.
        """
        digits = 0
        for byte in rec[at:at + 4]:
            digits = digits * 100 + (byte >> 4) * 10 + (byte & 0xF)
        return digits

    @staticmethod
    def haggle_margin(bartering: int) -> int:
        """How far off the item's own value a haggled price lands, as a percent."""
        for limit, percent in HAGGLE:
            if bartering <= limit:
                return percent
        return HAGGLE_OVER

    def scale_by_percent(self, value: int, percent: int) -> int:
        """`value x percent / 100`, rounded the way image 0x0AA1D rounds it.

        The routine multiplies each BCD digit by the percentage, adds 50 to the
        units digit's product, and shifts the total right two digits. That is
        round-half-up.
        """
        return (value * percent + 50) // 100

    def scaled_price(self, item_id: int, percent: int) -> int:
        """What an item costs at a given percentage of its own value."""
        return self.scale_by_percent(self.items.value(self.items.records[item_id - 1]), percent)

    def shop_buy_price(self, item_id: int, bartering: int) -> int:
        return self.scaled_price(item_id, 100 + self.haggle_margin(bartering))

    def shop_sell_price(self, item_id: int, bartering: int) -> int:
        return self.scaled_price(item_id, 100 - self.haggle_margin(bartering))

    def repair_price(self, whole_id: int, price_factor: int) -> int:
        """What mending a broken piece costs.

        Image 0x0A763 prices the *whole* form rather than the broken one, so a
        COPPER SHIELD +4 is mended on the +4's own worth, and scales it by the
        NPC's factor as a percentage.
        """
        return self.scaled_price(whole_id, price_factor)

    def enhance_price(self, item_id: int, price_factor: int) -> int:
        """What one step along a series costs, which is the next form's worth.

        Image 0x0A725 reads the record one past the one in hand, so the party
        pays for what it gets. Image 0x045A8 then writes that id into the
        place, which is the whole of what an enhancement does.
        """
        return self.scaled_price(item_id + 1, price_factor)

    @staticmethod
    def cure_price(conditions: int) -> int:
        """What clearing a character's conditions costs, before the factor."""
        return sum(price for bit, price in CONDITION_PRICE.items()
                   if conditions & bit)

    def body_price(self, what: str, who: dict, price_factor: int) -> int:
        """What one of the four services on a body costs.

        Image 0x091EB multiplies the unit price by the NPC's factor and then by
        the character's level, so all four are priced per level.
        """
        unit = 0
        if what == "health":
            unit = HEAL_PER_LEVEL
        elif what == "conditions":
            unit = self.cure_price(who["conditions"])
        elif what == "life":
            unit = RESURRECT_PER_LEVEL
        elif what == "everything":
            unit = self.cure_price(who["conditions"])
            if who["health"] < who["most_health"]:
                unit += RESTORE_HEALTH
            if who["conditions"] & HELD:
                unit += RESTORE_HELD
        return unit * price_factor * who["level"]



def summary(p: People) -> dict:
    """Counts over all three tables, for the command line and the tests."""
    services = defaultdict(int)
    for t in range(1, TOPIC_COUNT + 1):
        for name in p.action_of(t)[0]:
            services[name] += 1
    return {
        "npcs": NPC_COUNT,
        "placed": len(p.placed),
        "cells": sum(len(v) for v in p.placed.values()),
        "topics": TOPIC_COUNT,
        "prose": PROSE_COUNT,
        "services": dict(sorted(services.items())),
        "shops": sum(1 for t in range(1, TOPIC_COUNT + 1) if p.stock_bundle(t)),
        "flagged": sum(1 for t in range(1, TOPIC_COUNT + 1)
                       if p.flags_tested(t) or p.flags_written(t)),
    }


def load(game_dir: str = "game") -> People:
    return People(S.load(game_dir))


def _show_npc(p: People, n: int) -> None:
    info = p.npc_record(n)
    print(f"NPC {n}  portrait {info['portrait']}  "
          f"{len(info['topicNumbers'])} topics  {_w(p.npcs[n], PROSE_COUNT_AT)} lines")
    for key in ("servicesOffered", "priceFactor", "oncePerGameFlag",
                "challengeBit", "goneIfFlag", "wantsItemId", "flatPrice",
                "raisesWordName", "raisesBy", "challengeWordName",
                "challengeRaisesTo", "experienceAwarded", "enchantmentRange",
                "trainsThroughLevel", "standsAt"):
        if info.get(key):
            print(f"  {key:<14} {info[key]}")
    for t in info["topicNumbers"]:
        rec = p.topics[t - 1]
        services, flow = p.action_of(t)
        bits = ",".join(services + flow) or "-"
        show = "/".join(f"{_w(rec, off):#06x}" for off in SHOWN_IF)
        on = "/".join(f"{_w(rec, off):#06x}" for off in TURNS_ON)
        off = "/".join(f"{_w(rec, o):#06x}" for o in TURNS_OFF)
        print(f"\n  t{t} {_text(rec[:KEYWORD])!r}  {bits}")
        print(f"    shown {show}  on {on}  off {off}  select "
              f"{_w(rec, SELECTOR):#06x}")
        if _w(rec, GOLD_PRICE):
            print(f"    gold {_w(rec, GOLD_PRICE)}")
        if p.flags_tested(t):
            print(f"    needs flags {p.flags_tested(t)}")
        if p.flags_written(t):
            print(f"    writes flags {p.flags_written(t)}")
        held = p.stock_bundle(t)
        if held:
            names = [p.items.names[i - 1] for i in held["items"] if i]
            print(f"    bundle {held['bundle'] + 1}: {names}")
        if p.buys_classes(t):
            print(f"    buys {p.buys_classes(t)}")
        if p.commodity_item(t):
            print(f"    sells {p.items.names[p.commodity_item(t) - 1]} by the unit")
        said = p.said_line(t)
        if said:
            print(f"    {said}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--npc", type=int)
    ap.add_argument("--shops", action="store_true")
    ap.add_argument("--services", action="store_true")
    ap.add_argument("--flags", action="store_true")
    ap.add_argument("--game", default="game")
    a = ap.parse_args()
    p = load(a.game)

    if a.npc is not None:
        _show_npc(p, a.npc)
    elif a.shops:
        for t in range(1, TOPIC_COUNT + 1):
            held = p.stock_bundle(t)
            if not held:
                continue
            kind = "reward" if "reward" in p.action_of(t)[0] else "shop"
            names = [p.items.names[i - 1] for i in held["items"] if i]
            counts = {k: v for k, v in held["counts"].items() if v}
            owner = p.npc_of_topic(t)
            where = p.placed.get(owner, [])
            print(f"{kind:<7} npc {owner:>3} t{t:<5} bundle {held['bundle'] + 1:<4} "
                  f"{where}  {counts if counts else ''} {names}")
    elif a.services:
        for n in range(NPC_COUNT):
            info = p.npc_record(n)
            if not info["servicesOffered"]:
                continue
            extra = {k: info[k] for k in
                     ("raisesWordName", "raisesBy", "challengeWordName",
                      "challengeRaisesTo", "trainsThroughLevel", "flatPrice",
                      "experienceAwarded")
                     if info.get(k)}
            print(f"npc {n:>3} factor {info['priceFactor']:>3} "
                  f"{','.join(info['servicesOffered']):<40} {extra} "
                  f"{info['standsAt']}")
    elif a.flags:
        for t in range(1, TOPIC_COUNT + 1):
            tested, written = p.flags_tested(t), p.flags_written(t)
            if not (tested or written):
                continue
            print(f"t{t:<5} npc {p.npc_of_topic(t):>3} "
                  f"{_text(p.topics[t - 1][:KEYWORD]):<14} "
                  f"needs {tested} writes {written}")
    else:
        for key, value in summary(p).items():
            print(f"{key:<10} {value}")
