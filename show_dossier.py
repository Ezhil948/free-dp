import os
import sys
import argparse
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def find_latest_dossier():
    """Finds the most recent final_dossier.md in runs/ or workspace root."""
    runs_dir = "runs"
    if os.path.isdir(runs_dir):
        subdirs = [os.path.join(runs_dir, d) for d in os.listdir(runs_dir) if os.path.isdir(os.path.join(runs_dir, d))]
        subdirs.sort(key=os.path.getmtime, reverse=True)
        for s in subdirs:
            p = os.path.join(s, "final_dossier.md")
            if os.path.isfile(p):
                return p
    if os.path.isfile("final_dossier.md"):
        return "final_dossier.md"
    return None

def main():
    parser = argparse.ArgumentParser(description="Display and inspect the generated Research Dossier")
    parser.add_argument("--path", type=str, default="", help="Path to final_dossier.md (default: latest)")
    parser.add_argument("--full", action="store_true", help="Print the entire dossier verbatim to terminal")
    args = parser.parse_args()

    target = args.path if args.path else find_latest_dossier()
    if not target or not os.path.isfile(target):
        print("No dossier found yet. Run 'python run_council.py --prompt \"...\"' first.")
        sys.exit(1)

    with open(target, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    size_kb = len(content.encode("utf-8")) / 1024.0
    lines = content.splitlines()

    print("\n" + "=" * 70)
    print("                MULTI-AGENT RESEARCH DOSSIER DISPLAY")
    print("=" * 70)
    print(f"• Location:   {os.path.abspath(target)}")
    print(f"• Size:       {len(content):,} characters ({size_kb:.1f} KB) across {len(lines)} lines")
    print(f"• Associated: council_room.json (Phase 1-6 room audit state)")
    print(f"• Members:    cm_room_cm1.json .. cm_room_cm4.json (Room 2 scrape & worker data)")
    print("=" * 70 + "\n")

    if args.full:
        print(content)
        return

    # Print a structured outline and excerpts of each section
    sections = content.split("## ")
    print(sections[0].strip())
    print("\n" + "-" * 70)

    for s in sections[1:]:
        lines_s = s.strip().splitlines()
        header = lines_s[0]
        body = "\n".join(lines_s[1:8])
        print(f"\n[SECTION] ## {header}")
        print(body)
        if len(lines_s) > 8:
            print(f"... ({len(lines_s) - 8} more lines in dossier file)")

    print("\n" + "=" * 70)
    print(f"To read full verbatim dossier: open '{target}' or run 'python show_dossier.py --full'")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
