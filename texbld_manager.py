#!/usr/bin/env python3

from pathlib import Path
import sys
import os
import urllib.request
import subprocess
from dataclasses import dataclass
import hashlib
import sqlite3

class Logger:
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"

    @classmethod
    def color(cls, code, text) -> str:
        return code + text + "\033[0m"

    @classmethod
    def error(cls, text):
        sys.stdout.write(cls.color(cls.RED, "Error:") + " " + text + "\n")
        if __name__ == "__main__":
            sys.exit(1)

    @classmethod
    def progress(cls, text):
        sys.stdout.write(cls.color(cls.YELLOW, "Progress") + " " + text + " ")

    @classmethod
    def success(cls):
        sys.stdout.write(cls.color(cls.GREEN, "Done") + "\n")


def check_version():
    from platform import python_version_tuple
    Logger.progress("Checking python version...")
    MAJOR, MINOR, _ = python_version_tuple()
    if int(MAJOR) != 3 or int(MINOR) < 9:
        Logger.error("Incompatible Python version (must be ^3.9)")
    else:
        Logger.success()


def execute(cmd: list):
    res = subprocess.run(cmd)
    if res.returncode != 0:
        Logger.error(f"Subprocess {cmd} exited with status {res.returncode}")


class DB:

    def __init__(self, root: Path | None=None):
        if root is None:
            connection = sqlite3.connect(":memory:")
        else:
            connection = sqlite3.connect(root / "texbld.db")
        self.cursor = connection.cursor()
        self.initialize_db()

    # cleanup
    def close(self):
        self.cursor.connection.commit()
        self.cursor.connection.close()

    def __enter__(self) -> 'DB':
        return self

    def __exit__(self):
        self.close()

    def __del__(self):
        self.close()
    
    def initialize_db(self):
        self.cursor.executescript(
            """
            begin;
            CREATE TABLE IF NOT EXISTS pkgs (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                used_at DATETIME,
                current INTEGER DEFAULT 0,
                version VARCHAR(255) NOT NULL
            );
            commit;
            """
        )

    def add_nightly(self):
        self.cursor.execute("INSERT INTO pkgs(version) VALUES('nightly');")

    def add_stable(self, version: str):
        self.cursor.execute("INSERT INTO pkgs(version) VALUES(?);", (version,))

    def get_by_id(self, identifier: int):
        return self.cursor.execute("""
            SELECT * from pkgs WHERE id=?;
        """, (identifier,)).fetchone()

    def get_nightlies(self):
        return self.cursor.execute("""
            SELECT * FROM pkgs WHERE version='nightly' ORDER BY
            created_at DESC, id DESC LIMIT 10;
        """).fetchall()

    def get_stables(self):
        return self.cursor.execute("""
            SELECT * from pkgs WHERE version != 'nightly' ORDER BY created_at
            DESC, id DESC
            LIMIT 10;
        """).fetchall()

    def remove_by_id(self, identifier: str):
        self.cursor.execute("DELETE FROM pkgs WHERE id=?;", (identifier,))

    def switch(self, identifier: int):
        if not self.get_by_id(identifier):
            Logger.error(f"TeXbld package with id {identifier} not found.")
        else:
            self.cursor.execute("""
                UPDATE pkgs
                    SET current=0
                WHERE id != ?
            """, (identifier,))
            self.cursor.execute("""
                UPDATE pkgs
                    SET used_at=datetime(), current=1
                WHERE id=?
            """, (identifier,))

    def rollback(self):
        result = self.cursor.execute("""
            SELECT id,version FROM pkgs
                WHERE used_at IS NOT NULL AND current=0
                ORDER BY current DESC, used_at DESC, id DESC LIMIT 1;
        """).fetchone()
        if result:
            identifier,version = result
            Logger.progress(f"Switching to texbld {identifier}-{version}...")
            self.switch(identifier)
            Logger.success()
        else:
            Logger.error("Nothing to rollback to. Consider switching")

    def history(self):
        return self.cursor.execute("""
            SELECT * FROM pkgs
                WHERE used_at IS NOT NULL
                ORDER BY current DESC, used_at DESC, id DESC LIMIT 20;
        """).fetchall()


class Manager:

    def __init__(self, root: Path):
        self.root = root
        self.db = DB(self.root)
        os.makedirs(self.root, exist_ok=True)

    def virtualenv_path(self):
        return self.root / "virtualenv.pyz"

    def install_venv(self):
        if not self.virtualenv_path().exists():
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
            virtualenv_bootstrap_url = (
                f"https://bootstrap.pypa.io/virtualenv/{python_version}/virtualenv.pyz"
            )
            self.virtualenv_path().write_bytes(
                urllib.request.urlopen(virtualenv_bootstrap_url).read()
            )

    # download from github releases
    def install_nightly(self):
        pass

    # use pypi
    def install_stable(self, version: str):
        pass


if __name__ == "__main__":
    check_version()
