#!/usr/bin/env python3

from pathlib import Path
import sys
import os
import urllib.request
import subprocess
import shutil
import sqlite3
import stat
from argparse import ArgumentParser

STABLE_VERSIONS = [
    "0.3.0",
    "0.2.1",
    "0.1.2"
]


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
        sys.stderr.write(cls.color(cls.RED, "Error:") + " " + text + "\n")
        if __name__ == "__main__":
            sys.exit(1)

    @classmethod
    def progress(cls, text):
        sys.stderr.write(cls.color(cls.YELLOW, "Progress") + " " + text + " ")

    @classmethod
    def success(cls):
        sys.stderr.write(cls.color(cls.GREEN, "Done") + "\n")


def check_version():
    from platform import python_version_tuple
    MAJOR, MINOR, _ = python_version_tuple()
    if int(MAJOR) != 3 or int(MINOR) < 9:
        Logger.error("Incompatible Python version (must be ^3.9)")


def execute(*cmd: str | Path):
    res = subprocess.run(list(cmd))
    if res.returncode != 0:
        Logger.error(f"Subprocess {cmd} exited with status {res.returncode}")


class DB:

    def __init__(self, root: Path | None = None):
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

    def add_nightly(self) -> int:
        self.cursor.execute("INSERT INTO pkgs(version) VALUES('nightly');")
        self.cursor.connection.commit()
        return self.cursor.lastrowid or 0

    def add_stable(self, version: str = STABLE_VERSIONS[0]) -> int:
        self.cursor.execute("INSERT INTO pkgs(version) VALUES(?);", (version,))
        self.cursor.connection.commit()
        return self.cursor.lastrowid or 0

    def get_by_id(self, identifier: int):
        return self.cursor.execute("""
            SELECT * from pkgs WHERE id=?;
        """, (identifier,)).fetchone()

    def list_nightlies(self):
        return self.cursor.execute("""
            SELECT * FROM pkgs WHERE version='nightly' ORDER BY
            used_at DESC, created_at DESC, id DESC
            LIMIT 10;
        """).fetchall()

    def list_stables(self):
        return self.cursor.execute("""
            SELECT * from pkgs WHERE version != 'nightly' ORDER BY 
            used_at DESC, created_at DESC, id DESC
            LIMIT 10;
        """).fetchall()

    def remove_by_id(self, identifier: int):
        if not self.get_by_id(identifier):
            Logger.error(f"TeXbld package with id {identifier} not found.")
        self.cursor.execute("DELETE FROM pkgs WHERE id=?;", (identifier,))
        self.cursor.connection.commit()

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
            self.cursor.connection.commit()

    def rollback(self) -> int:
        result = self.cursor.execute("""
            SELECT id,version FROM pkgs
                WHERE used_at IS NOT NULL AND current=0
                ORDER BY current DESC, used_at DESC, id DESC LIMIT 1;
        """).fetchone()
        if result:
            identifier, version = result
            self.switch(identifier)
            return identifier
        else:
            Logger.error("Nothing to rollback to. Consider switching.")
            # unreachable
            return -1

    def history(self):
        return self.cursor.execute("""
            SELECT * FROM pkgs
                WHERE used_at IS NOT NULL
                ORDER BY current DESC, used_at DESC, id DESC LIMIT 20;
        """).fetchall()


class ShellScriptWriter:

    def __init__(self, store: 'Store', identifier: int):
        _, _, _, _, version = store.db.get_by_id(identifier)
        self.nightly = (version == 'nightly')
        self.path = store.package_path(identifier)

    def script(self):
        if self.nightly:
            return f"#!/bin/sh\n{sys.executable} {self.path / 'texbld.pyz'}"
        else:
            return f"#!/bin/sh\n{self.path / 'venv' / 'bin' / 'texbld'}"

    def write_script(self, path: Path):
        os.makedirs(path.parent, exist_ok=True)
        with open(path, "w") as w:
            w.write(self.script())
        path.chmod(path.stat().st_mode | stat.S_IEXEC)


class Store:

    def __init__(self, root: Path):
        self.root = root
        os.makedirs(self.root, exist_ok=True)
        self.db = DB(self.root)

    def texbld_script(self):
        path = self.root / "bin" / "texbld"
        return path

    def package_path(self, identifier: int):
        return (self.root / "store" / str(identifier)).absolute()

    def valid_package_identifier(self, identifier: int):
        return (self.package_path(identifier)).is_dir()

    def invalid_identifier(self, identifier: int):
        Logger.error(
            f"{self.package_path(identifier)} is invalid. Either roll back or switch.")

    def prepare_stable(self, version=STABLE_VERSIONS[0]) -> Path:
        directory = self.package_path(self.db.add_stable(version))
        os.makedirs(directory, exist_ok=True)
        return directory

    def prepare_nightly(self) -> Path:
        directory = self.package_path(self.db.add_nightly())
        os.makedirs(directory, exist_ok=True)
        return directory

    def remove(self, identifier: int):
        self.db.remove_by_id(identifier)
        shutil.rmtree(self.package_path(identifier))

    def rollback(self):
        identifier = self.db.rollback()
        self.switch(identifier)

    def history(self):
        return self.db.history()

    def switch(self, identifier: int):
        if not self.valid_package_identifier(identifier):
            self.invalid_identifier(identifier)
        Logger.progress(f"Switching TeXbld to {identifier}...")
        self.db.switch(identifier)
        ShellScriptWriter(self, identifier).write_script(self.texbld_script())
        Logger.success()

    # installation methods

    def virtualenv_path(self):
        return self.root / "virtualenv.pyz"

    def install_virtualenv(self):
        if not self.virtualenv_path().exists():
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
            virtualenv_bootstrap_url = (
                f"https://bootstrap.pypa.io/virtualenv/{python_version}/virtualenv.pyz"
            )
            Logger.progress(f"Creating a virtual environment with {virtualenv_bootstrap_url}...")
            self.virtualenv_path().write_bytes(
                urllib.request.urlopen(virtualenv_bootstrap_url).read()
            )
            Logger.success()

    # download from github releases
    def install_nightly(self):
        path = self.prepare_nightly()
        nightly_url = (
            f"https://github.com/texbld/texbld/releases/download/nightly/texbld.pyz"
        )
        (path / "texbld.pyz").write_bytes(
            urllib.request.urlopen(nightly_url).read()
        )

    # use pypi
    def install_stable(self, version: str = STABLE_VERSIONS[0]):
        if version not in STABLE_VERSIONS:
            Logger.error(
                f"{version} is not in the list of recommended stable versions: {STABLE_VERSIONS}")
        self.install_virtualenv()
        path = self.prepare_stable(version)
        execute(sys.executable, self.virtualenv_path(), path / "venv")
        execute(path / "venv" / "bin" / "pip", "install", f"texbld=={version}")

class Manager:
    root = Path(__file__).parent / "tests" / "texbld"
    #store = Store(Path.home() / ".texbld")
    store = Store(Path(__file__).parent / "tests" / "texbld")

    @classmethod
    def initialize_argparse(cls, parser: ArgumentParser):
        parser.__init__(prog="texbld_manager", description="The official TeXbld version manager")
        parser.set_defaults(func=lambda _: parser.print_help())
        subparser = parser.add_subparsers()

        install = subparser.add_parser("install", description="install a new TeXbld build", aliases=['i'])
        install.set_defaults(func=cls.install)
        install.add_argument("version")

        switch = subparser.add_parser("switch", description="switch to another TeXbld build", aliases=['s'])
        switch.set_defaults(func=cls.switch)
        switch.add_argument("identifier", type=int)

        remove = subparser.add_parser("remove", description="remove an existing TeXbld build", aliases=['rm'])
        remove.set_defaults(func=cls.remove)
        remove.add_argument("identifier", type=int)

        subparser.add_parser("list", description='List TeXbld builds', aliases=['ls']).set_defaults(func=lambda _: (cls.list_nightlies(_), cls.list_stables(_)))
        subparser.add_parser("rollback", description='Rollback a TeXbld build', aliases=['rb']).set_defaults(func=cls.rollback)
        subparser.add_parser("history", description='Rollback a TeXbld build', aliases=['h']).set_defaults(func=cls.history)

    @classmethod
    def install(cls, args):
        version = args.version
        if version.lower() == "nightly":
            cls.store.install_nightly()
        else:
            cls.store.install_stable(version)

    @classmethod
    def remove(cls, args):
        identifier = args.identifier
        cls.store.remove(identifier)

    @classmethod
    def switch(cls, args):
        identifier = args.identifier
        cls.store.switch(identifier)

    @classmethod
    def rollback(cls, _):
        cls.store.rollback()

    @classmethod
    def list_nightlies(cls, _):
        query_result = cls.store.db.list_nightlies()
        if query_result:
            print("Nightly TeXbld builds")
            print("-"*20)
            for result in query_result:
                id,created_at,_,current,_ = result
                print(f"{'*' if current else ''} {id} : {created_at}")
            print()

    @classmethod
    def list_stables(cls, _):
        query_result = cls.store.db.list_stables()
        if query_result:
            print("Stable TeXbld builds")
            print("-"*20)
            for result in query_result:
                id,created_at,_,current,version = result
                print(f"{'*' if current else ''} {id} : {version}-{created_at}")
            print()

    @classmethod
    def history(cls, _):
        print("TeXbld History")
        print("-"*20)
        for result in cls.store.db.history():
            id,created_at,used_at,current,version = result
            print(f"{'*' if current else ''} {id} : {version}-{created_at} : Last used {used_at}")
        print()

if __name__ == "__main__":
    check_version()
    parser = ArgumentParser()
    Manager.initialize_argparse(parser)
    args = parser.parse_args()
    args.func(args)
