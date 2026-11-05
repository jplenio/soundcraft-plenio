"""Lyrics subtitles (owner's request 2026-10-15): times from what was heard - with a score, on its notes -,
whole lines and lines painted on note by note, SRT that every player reads."""

from __future__ import annotations

from plenio.core import subtitles as s
from plenio.core.alignment import AsrWord
from plenio.core.score import canonical, lyric_layout

HEAD = """X:1
T:
M:4/4
L:1/8
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
"""
# 120 BPM, L:1/8 = 0.25 s: a bar of rest, then two phrases of eight eighths with a bar's rest between
SCORE = (
    HEAD
    + "% intro\nV: Vocal\nz8|\nV: Ins\nC8|\n"
    + "% verse\nV: Vocal\nCDEF GABc|z8|cBAG FEDC|z8|\nV: Ins\nC8|C8|C8|C8|\n"
)
LYRICS = "[Verse]\nwalking down the river side\nsinging songs of yesterday"


def heard(words: list[tuple[str, float, float]], segment: int = 0) -> list[AsrWord]:
    return [AsrWord(start, end, word, 0.9, segment) for word, start, end in words]


def whisper_like(times: list[tuple[str, float]], length: float = 0.25) -> list[AsrWord]:
    """Words as Whisper times them: each starts where the one before ends (the first of a phrase takes the rest
    before it), so the starts are early."""
    found: list[AsrWord] = []
    previous_end = 0.0
    for word, start in times:
        found.append(AsrWord(previous_end, start + length, word, 0.9, 0))
        previous_end = start + length
    return found


def test_srt_format() -> None:
    assert s.srt_time(3723.4567) == "01:02:03,457"
    text = s.srt([(1.0, 2.5, "first line"), (3.0, 4.0, "second\nrow")])
    assert (
        text
        == "1\n00:00:01,000 --> 00:00:02,500\nfirst line\n\n2\n00:00:03,000 --> 00:00:04,000\nsecond\nrow\n"
    )
    assert s.srt([]) == ""


def test_long_lines_wrap_once_and_grow_in_their_rows() -> None:
    line = "When the morning comes, I will be standing at your door again"
    split = s.wrap_at(line)
    assert split is not None and line[split - 1] == ","  # a comma near the middle
    assert s.wrapped(line) == "When the morning comes,\nI will be standing at your door again"
    assert s.wrapped(line, 9) == "When the"  # still on the first row
    assert s.wrapped(line, 30) == "When the morning comes,\nI will"
    assert s.wrap_at("short line") is None


def test_sung_lines_and_plain_lyrics_leave_out_tags_and_directions() -> None:
    lyrics = "[Intro]\n(guitar)\n\n[Verse]\nOne line, sung\nTwo\n\n[Chorus]\nThree"
    lines = s.sung_lines(lyrics)
    assert [line.text for line in lines] == ["One line, sung", "Two", "Three"]
    assert lines[0].words == ("one", "line", "sung")
    assert s.plain_lyrics(lyrics) == "One line, sung\nTwo\n\nThree"


def test_words_pair_up_across_a_skipped_and_an_extra_word() -> None:
    pairs = s.match_words(["walk", "down", "the", "river"], ["walking", "down", "a", "the", "rivers"])
    assert pairs == {0: 0, 1: 1, 2: 3, 3: 4}  # alike enough ("walk", "walking"); "a" is extra
    assert s.match_words(["sun"], ["moon"]) == {}


def test_the_warp_finds_how_the_render_is_shifted_against_the_score() -> None:
    gaps = [0.5, 0.25, 0.75, 0.5, 1.0, 0.25, 0.25, 1.5]  # a sung rhythm, not a grid
    onsets = [sum(gaps[: k % 8]) + 4.0 * (k // 8) for k in range(64)]
    times = [t - 1.7 + 0.02 * ((k % 5) - 2) for k, t in enumerate(onsets[5:50])]
    a, b = s.fit_warp(times, onsets)
    assert abs(a - 1.0) <= 0.002 and abs(b + 1.7) <= 0.05
    # a steady grid fits a beat later as well as here: the smallest shift wins
    grid = [0.5 * k for k in range(60)]
    assert s.fit_warp([t + 0.04 for t in grid[4:40]], grid) == (1.0, 0.04)


def test_without_a_score_the_heard_times_are_corrected_for_whisper() -> None:
    sung = [("walking", 2.0), ("down", 2.5), ("the", 3.0), ("river", 3.5), ("side", 4.0)]
    sung += [("singing", 8.0), ("songs", 8.5), ("of", 9.0), ("yesterday", 9.5)]
    timed = s.time_lyrics(LYRICS, whisper_like(sung), duration=20.0)
    assert timed.timing == "measured" and timed.matched == 1.0
    first, second = timed.lines
    # Whisper started "singing" where "side" ended (4.25 s): the line's first word is capped, then 0.3 s on
    assert abs(first.units[1].start - 2.55) < 0.01  # down: Whisper's 2.25 (where "walking" ended) + 0.3
    assert 7.5 <= second.start <= 8.2
    assert second.start >= first.end  # cues never overlap
    assert [u.cut for u in second.units] == [7, 13, 16, 26]  # a word each: "singing", "singing songs" ...


def test_a_line_nobody_sang_is_left_out_when_there_is_no_room() -> None:
    lyrics = "[Verse]\nfirst line here\nnever heard at all\nthird line here"
    words = heard([("first", 1.0, 1.3), ("line", 1.3, 1.6), ("here", 1.6, 2.0)])
    words += heard([("third", 2.2, 2.5), ("line", 2.5, 2.8), ("here", 2.8, 3.1)])
    timed = s.time_lyrics(lyrics, words, duration=10.0)
    assert [line.text for line in timed.lines] == ["first line here", "third line here"]
    assert timed.untimed == ("never heard at all",)


def test_with_a_score_the_syllables_sit_on_their_notes() -> None:
    score = canonical.from_abc(SCORE)
    layout = lyric_layout.layout(score, LYRICS)
    notes = s.score_notes(score, layout, s.sung_lines(LYRICS))
    (first_key, first), (_, second) = sorted(notes.items())
    assert first_key == (0, 0) and first.words[0] == 2.0  # after the intro bar: 4 beats at 120 BPM
    # the render sings 1.5 s earlier than its score; Whisper's starts 0.3 s early, as measured
    shift = -1.5
    sung = [(w, first.words[k] + shift) for k, w in enumerate(["walking", "down", "the", "river", "side"])]
    sung += [(w, second.words[k] + shift) for k, w in enumerate(["singing", "songs", "of", "yesterday"])]
    words = heard([(w, t - s.LEAD_S, t + 0.2) for w, t in sung])
    timed = s.time_lyrics(LYRICS, words, duration=20.0, score=score, layout=layout)
    line = timed.lines[0]
    assert abs(line.start - (2.0 + shift)) < 0.06
    # "walking" has two notes: its second syllable keeps the score's rhythm (an eighth later)
    assert [round(u.start - line.start, 2) for u in line.units[:3]] == [0.0, 0.25, 0.5]
    assert [line.text[: u.cut] for u in line.units[:3]] == ["wal", "walking", "walking down"]
    notes_srt = timed.notes_srt()
    assert "\nwal\n" in notes_srt and "\nwalking down the river side\n" in notes_srt
    assert timed.lines_srt().count(" --> ") == 2
    # the record keeps the times for the Plenio Player: each syllable with its note's place in the score
    timing = timed.to_timing("Take 1")
    assert timing["take"] == "Take 1" and timing["timing"] == timed.timing
    # (the warp is fitted to the heard starts, which come LEAD_S early)
    assert timing["warp"] is not None and abs(timing["warp"][1] - (shift - s.LEAD_S)) < 0.06
    first_unit = timing["lines"][0]["units"][0]
    assert first_unit[:2] == [round(line.units[0].start, 3), 3] and first_unit[2] == 2.0
    assert [entry["text"] for entry in timing["lines"]] == [line.text for line in timed.lines]


def test_without_lyrics_the_words_as_heard_and_no_inventions() -> None:
    words = heard(
        [("Hold", 1.0, 1.3), ("on", 1.3, 1.6), ("to", 1.6, 1.8), ("the", 1.8, 2.0), ("light", 2.0, 2.6)]
    )
    words += heard(
        [("Thank", 30.0, 30.2), ("you", 30.2, 30.4), ("for", 30.4, 30.5), ("watching!", 30.5, 31.0)], 1
    )
    timed = s.time_heard(words, duration=40.0)
    assert timed.timing == "heard"
    assert [line.text for line in timed.lines] == ["Hold on to the light"]
    assert s.time_heard(heard([("la", 1.0, 1.2)]), duration=5.0).lines == ()


def test_what_was_sung_is_laid_out_like_the_lyrics_where_the_take_sings_them() -> None:
    """Owner's request 2026-10-23: the lyrics that were wanted and the ones the take sings, both to follow. A
    heard word that pairs with a lyrics word is written as the lyrics write it and keeps its line; words the
    lyrics do not have make lines of their own; the sections keep their tags."""
    lyrics = (
        "[Verse]\nWalking down the river side,\nsinging songs of yesterday\n\n"
        "[Chorus]\nHold on, hold on\nto the light we made"
    )
    words = heard(
        [("walking", 1.0, 1.4), ("down", 1.4, 1.7), ("the", 1.7, 1.8), ("riverside", 1.8, 2.6)]
        + [("singing", 3.0, 3.4), ("songs", 3.4, 3.8), ("of", 3.8, 3.9), ("yesterday", 3.9, 4.8)]
        # the take makes a line up between verse and chorus
        + [("oh", 7.0, 7.3), ("baby", 7.3, 7.8), ("baby", 7.8, 8.3)]
        + [("hold", 10.0, 10.3), ("on", 10.3, 10.6), ("hold", 10.6, 10.9), ("on", 10.9, 11.2)]
    )
    sung = s.time_sung(lyrics, words, duration=20.0, timing=s.ALIGNED)
    assert sung is not None and sung.subtitles.timing == "sung"
    assert [line.text for line in sung.subtitles.lines] == [
        "Walking down the riverside",
        "singing songs of yesterday",
        "oh baby baby",
        "Hold on, hold on",
    ]
    assert sung.text == (
        "[Verse]\nWalking down the riverside\nsinging songs of yesterday\noh baby baby\n\n[Chorus]\nHold on, hold on"
    )
    # 'riverside' is heard where the lyrics have 'river side': it pairs with 'river' and is written as heard
    assert sung.extra_words == 3 and sung.not_sung == ("to the light we made",)
    assert sung.written_heard == 12 / 18
    first = sung.subtitles.lines[0]
    assert first.start == 1.0 and [u.cut for u in first.units][:2] == [7, 12]
    assert sung.sections == (
        {"tag": "Verse", "words": 9, "heard": 8},
        {"tag": "Chorus", "words": 9, "heard": 4},
    )
    assert sung.findings() == []
    record = sung.to_record()
    assert record["lines"][2]["text"] == "oh baby baby" and record["not_sung"] == ["to the light we made"]
    assert s.time_sung(lyrics, heard([("la", 1.0, 1.2)]), duration=5.0) is None


def test_a_take_that_sings_other_words_is_laid_out_by_its_pauses() -> None:
    lyrics = "[Verse]\nthe written line that nobody sings at all today\n\n[Chorus]\nla la la"
    words = heard(
        [(w, 1.0 + 0.4 * k, 1.3 + 0.4 * k) for k, w in enumerate("something else came out of it".split())]
    )
    words += heard([(w, 9.0 + 0.4 * k, 9.3 + 0.4 * k) for k, w in enumerate("and more of that here".split())])
    sung = s.time_sung(lyrics, words, duration=20.0, timing=s.ALIGNED)
    assert sung is not None
    assert [line.text for line in sung.subtitles.lines] == [
        "something else came out of it",
        "and more of that here",
    ]
    assert sung.text == "something else came out of it\n\nand more of that here"
    assert sung.written_heard == 0.0 and sung.extra_words == 11
    assert sung.findings() == [
        "[Verse] was not sung as written (0% of its words heard)",
    ]


def test_chinese_and_japanese_lyrics_are_matched_character_by_character() -> None:
    """The owner's songs in Chinese and Japanese: their lines have no spaces, so a whole phrase was one word and
    almost nothing of the lyrics was matched to what was heard. Now every character is a token - in the lyrics
    and in what was heard (Whisper hears several characters as one word)."""
    lyrics = "[Verse]\n咖啡杯沿，还留着你的唇温\n雨滴敲窗"
    line = s.sung_lines(lyrics)[0]
    assert [line.text[a:z] for a, z in line.tokens][:4] == ["咖", "啡", "杯", "沿，"]
    heard = [
        AsrWord(1.0, 2.2, "咖啡杯沿", 0.9, 0),
        AsrWord(2.4, 4.2, "还留着你的唇温", 0.9, 0),
        AsrWord(6.0, 7.6, "雨滴敲窗", 0.9, 1),
    ]
    assert [w.word for w in s.split_cjk(heard)][:3] == ["咖", "啡", "杯"]
    timed = s.time_lyrics(lyrics, heard, duration=10.0, timing=s.ALIGNED)
    assert timed.matched == 1.0 and [round(t.start, 2) for t in timed.lines] == [1.0, 6.0]
    sung = s.time_sung(lyrics, heard, duration=10.0, timing=s.ALIGNED)
    assert sung is not None and [t.text for t in sung.subtitles.lines] == [
        "咖啡杯沿，还留着你的唇温",
        "雨滴敲窗",
    ]
    assert s.join_words(["我", "爱", "you", "too"]) == "我爱you too"


def test_a_first_word_that_took_the_music_before_it_is_placed_by_its_line() -> None:
    """Qwen3-ForcedAligner lets the first word of a piece take the music before it, or puts it at the piece's
    start (an export of 2026-10-23: the first "I" from 0.0 to 12.0 s; a "This" at 45.2 s, its line from 57.9 s)."""
    lyrics = "[Verse]\nI was tracing lines\nthis old road"
    words = [AsrWord(0.0, 12.0, "I", 0.9, 0)] + heard(
        [("was", 12.1, 12.5), ("tracing", 12.6, 13.2), ("lines", 13.3, 14.0)]
    )
    words += [AsrWord(20.0, 20.3, "this", 0.9, 1)] + heard([("old", 28.0, 28.4), ("road", 28.5, 29.4)], 1)
    timed = s.time_lyrics(lyrics, words, duration=40.0, timing=s.ALIGNED)
    assert [round(line.start, 2) for line in timed.lines] == [
        round(12.1 - s.WORD_S, 2),
        round(28.0 - s.WORD_S, 2),
    ]
    sung = s.time_sung(lyrics, words, duration=40.0, timing=s.ALIGNED)
    assert sung is not None and [round(t.start, 2) for t in sung.subtitles.lines] == [11.8, 27.7]
    # a word as long as the aligner times it, and Whisper's times, are left alone
    plain = heard([("I", 11.6, 12.0), ("was", 12.1, 12.5), ("tracing", 12.6, 13.2), ("lines", 13.3, 14.0)])
    assert s.time_lyrics(lyrics, plain, duration=40.0, timing=s.ALIGNED).lines[0].start == 11.6
