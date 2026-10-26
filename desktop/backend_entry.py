"""PyInstaller entry point; preserve internal subprocess Python command forms."""

import runpy
import sys


def main():
    args = sys.argv[1:]
    if args[:1] == ["-m"] and len(args) >= 2 and args[1].startswith("hutch."):
        sys.argv = [args[1], *args[2:]]
        runpy.run_module(args[1], run_name="__main__", alter_sys=True)
    elif args[:1] == ["-c"] and len(args) >= 2:
        # Hutch's sandboxed Python/document tools use sys.executable -c.
        # This branch is an interpreter entry point, not a desktop IPC API.
        sys.argv = ["-c", *args[2:]]
        exec(compile(args[1], "<string>", "exec"), {"__name__": "__main__"})
    else:
        from hutch.desktop import main as desktop_main
        return desktop_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
