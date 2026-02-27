"""
infrastructure/persistence/json_storage.py

Simple JSON file persistence for Stage 1 discovery output.

Designed around two static methods that every caller in the project uses:

    JSONStorage.save(data, filepath)   →  write dict → JSON file
    JSONStorage.load(filepath)         →  read JSON file → dict

Both methods accept pathlib.Path or plain str for filepath.

Design decisions
----------------
- atomic-ish writes: data is written to a .tmp file first, then renamed
  so a crash mid-write never leaves a corrupt JSON on disk.
- always UTF-8 + ensure_ascii=False so Portuguese characters (ã, ç, é…)
  are stored as real unicode, not backslash-u escaped sequences.
- indent=2 keeps files human-readable and git-diffable.
- load() returns an empty dict (not None, not an exception) when the
  file is missing — callers check keys, not None guards.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Union

logger = logging.getLogger(__name__)

# Type alias — save/load both accept Path or str
FilePath = Union[Path, str]


class JSONStorage:
    """
    Static utility class for reading and writing JSON discovery files.

    All methods are @staticmethod — no instantiation required.

    Usage
    -----
        JSONStorage.save(result.to_dict(), "data/discovery/processo_links.json")
        data = JSONStorage.load("data/discovery/processo_links.json")
    """

    @staticmethod
    def save(data: Dict[str, Any], filepath: FilePath) -> bool:
        """
        Persist a dictionary to a JSON file.

        Creates parent directories automatically if they don't exist.
        Uses an atomic write pattern (write .tmp → rename) to prevent
        corrupt files if the process is interrupted mid-write.

        Args:
            data:     Dictionary to serialise. Must be JSON-serialisable.
            filepath: Destination path (Path or str).

        Returns:
            True  if the file was written successfully.
            False if serialisation or I/O failed (error is logged).
        """
        path = Path(filepath)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write to a temp file first, then rename — prevents partial writes
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Atomic rename (on the same filesystem this is one syscall)
            tmp_path.replace(path)

            logger.debug(f"💾 Saved: {path} ({path.stat().st_size:,} bytes)")
            return True

        except (TypeError, ValueError) as e:
            logger.error(f"✗ JSON serialisation failed for {path}: {e}")
            return False
        except OSError as e:
            logger.error(f"✗ I/O error writing {path}: {e}")
            return False

    @staticmethod
    def load(filepath: FilePath) -> Dict[str, Any]:
        """
        Load a JSON file and return its contents as a dictionary.

        Args:
            filepath: Source path (Path or str).

        Returns:
            Parsed dictionary if the file exists and is valid JSON.
            Empty dict {} if the file is missing or unreadable
            (error is logged — callers should check for expected keys).
        """
        path = Path(filepath)

        if not path.exists():
            logger.warning(f"⚠ File not found: {path}")
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.debug(f"📂 Loaded: {path} ({path.stat().st_size:,} bytes)")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"✗ Invalid JSON in {path}: {e}")
            return {}
        except OSError as e:
            logger.error(f"✗ I/O error reading {path}: {e}")
            return {}

    @staticmethod
    def exists(filepath: FilePath) -> bool:
        """
        Check whether a JSON file exists on disk.

        Thin wrapper around Path.exists() — provided so callers don't
        need to import pathlib just to do a pre-save existence check.

        Args:
            filepath: Path to check (Path or str).

        Returns:
            True if the file exists.
        """
        return Path(filepath).exists()

    @staticmethod
    def append_to_list(
        filepath: FilePath,
        key: str,
        new_items: list,
    ) -> bool:
        """
        Load an existing JSON file, append items to a top-level list key,
        and save the result back atomically.

        Useful for incrementally growing a list (e.g. errors) without
        loading the entire file on every append.

        Args:
            filepath:  Path to the JSON file (Path or str).
            key:       Top-level key whose value must be a list.
            new_items: Items to append.

        Returns:
            True if saved successfully.
        """
        data = JSONStorage.load(filepath)

        if key not in data:
            data[key] = []

        if not isinstance(data[key], list):
            logger.error(
                f"✗ append_to_list: key '{key}' is not a list in {filepath}"
            )
            return False

        data[key].extend(new_items)
        return JSONStorage.save(data, filepath)