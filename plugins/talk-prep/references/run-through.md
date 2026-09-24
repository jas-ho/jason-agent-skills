# Timed run-through

The single most valuable prep step in both 2026 talks, and both times it came too late. Do the first run as soon as plain slides exist (T-5 days), and a second after the cuts.

## Recording

- **Record with Voice Memos or QuickTime,** or the lapel mic on the phone.
- **Don't use Granola for timing:** its transcripts have no per-line timestamps.
- **Say section or slide titles aloud at transitions,** so the transcript can be navigated.
- **Say to-dos aloud during the run** ("to do: fix this sentence"). They get picked up verbatim, and are the best input for the cleanup pass.
- **Stop before Q&A practice,** or say "end of talk".

## Transcribe and analyse

```bash
transcribe --format srt <recording>
```

This runs locally (parakeet) and gives sentence-level timestamps. From the .srt:

1. **Time per section and per slide,** against the budget. Match the speech to slides via the notes and the spoken transitions.
2. **The longest slides,** with what was said there, meaning where the story ran long.
3. **Spoken to-dos, with timestamps.**
4. **Delivery slips:** wrong words, unsourced claims. Check them against the sources before flagging them; Jason's newer knowledge may be right.
5. **Speaking pace:** total words divided by minutes. Use it for this talk's budget. Change the 115 wpm prior in SKILL.md only from representative recordings of Jason in English, not from one unusual run.

## Revision plan

- **A table of cuts** per slide: current time → target, each change labelled **slide**, **notes** or **delivery**.
- **Cut the story first.** Protect the section that carries the talk's main outcome, and develop its arguments and examples if they're thin. Don't just protect its minutes.
- **Keep a buffer for tech problems and interaction** of about 3-5 minutes in a 35-minute slot, plus a short skip route (which slides to drop live if running over).
- **Put the timing cues in the speaker notes** ("One minute. One line per trick.").
- **After the plan, additions are zero-sum:** every new card or bullet names the cut that pays for it.
- **Record the real talk too,** and run the same analysis afterwards for the debrief.
