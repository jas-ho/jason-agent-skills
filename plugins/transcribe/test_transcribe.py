"""Test real WAV conversion orchestration without Typer, ffmpeg or ML engines."""

import ast
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("transcribe.py")


class WavTests(unittest.TestCase):
    def test_downloaded_wav_never_overwrites_input(self):
        # Load the actual function without importing optional CLI/ML dependencies.
        tree = ast.parse(SCRIPT.read_text())
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "to_wav"
        )
        scratch = SCRIPT.parents[2] / "tmp"
        scratch.mkdir(exist_ok=True)
        # Retained in ignored scratch for inspection.
        directory = tempfile.mkdtemp(prefix="setup-scan-", dir=scratch)
        tmp = Path(directory)
        media = tmp / "interview.wav"
        media.write_bytes(b"original media")
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            source = Path(cmd[cmd.index("-i") + 1])
            output = Path(cmd[-1])
            self.assertNotEqual(source.resolve(), output.resolve())
            self.assertTrue(output.parent.is_dir())
            output.write_bytes(b"converted audio")
            return subprocess.CompletedProcess(cmd, 0)

        namespace = {
            "Path": Path,
            "tempfile": tempfile,
            "_VERBOSE": False,
            "is_probeable_media": lambda path: True,
            "has_audio_stream": lambda path: True,
            "log": lambda message: None,
            "_run": run,
            "die": self.fail,
        }
        exec(  # noqa: S102 - execute only the repository's to_wav function under test
            compile(ast.Module(body=[function], type_ignores=[]), str(SCRIPT), "exec"),
            namespace,
        )
        wav = namespace["to_wav"](media, tmp, "interview")
        self.assertEqual(media.read_bytes(), b"original media")
        self.assertEqual(wav.read_bytes(), b"converted audio")
        self.assertEqual(wav.name, "interview.wav")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
