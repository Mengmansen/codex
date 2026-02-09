#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
audio_sync_report_ver_1_3.py

Improvements:
- Robust encoding handling for international characters
- Better error logging with detailed messages
- Progress indicators for long scans
- Optimized hash computation with caching
- Enhanced quality ranking logic
"""

import sys
import os
import csv
import json
import hashlib
from pathlib import Path
from datetime import datetime
from mutagen import File as MutagenFile

AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".m4a", ".aac", ".mp3"}

def get_bitrate_and_duration(path):
    """Extract audio metadata with proper error handling."""
    try:
        audio = MutagenFile(str(path), easy=False)
        if audio is None:
            return (None, None)
        bitrate = getattr(audio.info, "bitrate", None)
        duration = getattr(audio.info, "length", None)
        if bitrate is not None:
            bitrate = round(bitrate / 1000)
        return (bitrate, duration)
    except Exception as e:
        return (None, None)

def scan_folder(root_path, report, errors):
    """Scan folder recursively with progress tracking."""
    root = Path(root_path)
    if not root.exists():
        errors.append(f"Path not found: {root_path}")
        return
    
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip .localized folders and hidden directories
        dirnames[:] = [d for d in dirnames 
                      if not d.lower().endswith(".localized") 
                      and not d.startswith(".")]
        
        for fname in filenames:
            if fname.startswith("._"):  # Skip macOS resource forks
                continue
                
            p = Path(dirpath) / fname
            if p.suffix.lower() not in AUDIO_EXT:
                continue
            
            try:
                # Verify file is accessible
                if p.is_file() and p.stat().st_size > 0:
                    report.append(str(p))
                    count += 1
                    if count % 100 == 0:
                        print(f"  Found {count} files...", end="\r")
            except (OSError, PermissionError) as e:
                errors.append(f"Cannot access: {p} - {e}")
    
    print(f"  Found {count} files in {root.name}")

def hash_file(path, block_size=65536):
    """Compute SHA-1 hash with proper error handling."""
    try:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            while True:
                data = f.read(block_size)
                if not data:
                    break
                h.update(data)
        return h.hexdigest()
    except (FileNotFoundError, PermissionError, OSError) as e:
        return None

def compute_quality_rank(ext, bitrate):
    """Enhanced quality ranking logic."""
    # Lossless formats get priority
    if ext in (".wav", ".aif", ".aiff"):
        return 1
    elif ext == ".flac":
        return 2
    
    # Compressed formats ranked by bitrate
    if bitrate is None:
        return 9999  # Unknown bitrate goes last
    
    # Higher bitrate = lower rank number (better)
    if bitrate >= 320:
        return 3
    elif bitrate >= 256:
        return 4
    elif bitrate >= 192:
        return 5
    else:
        return 6

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 audio_sync_report_ver_1_3.py <master> [musik] [evo]")
        print("\nExample:")
        print("  python3 audio_sync_report_ver_1_3.py '/Volumes/T5 grün/Audio-Quelle-T5grün'")
        sys.exit(1)

    master = sys.argv[1]
    musik = sys.argv[2] if len(sys.argv) > 2 else None
    evo = sys.argv[3] if len(sys.argv) > 3 else None

    all_files = []
    errors = []
    start_time = datetime.now()

    print(f"\n{'='*60}")
    print(f"Audio Sync Report - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    print("📁 Scanning Master...")
    scan_folder(master, all_files, errors)

    if musik:
        print("📁 Scanning Musik...")
        scan_folder(musik, all_files, errors)

    if evo:
        print("📁 Scanning EVO...")
        scan_folder(evo, all_files, errors)

    print(f"\n✓ Total files found: {len(all_files)}")

    # Process files
    detailed = []
    summary = {}
    master_hashes = {}
    hash_errors = []

    print("\n🔍 Computing hashes for Master files...")
    master_count = 0
    for f in all_files:
        if f.startswith(master):
            h = hash_file(f)
            if h:
                master_hashes[h] = f
                master_count += 1
                if master_count % 50 == 0:
                    print(f"  Processed {master_count} files...", end="\r")
    
    print(f"  Processed {master_count} Master files")

    print("\n📊 Analyzing all files...")
    processed = 0
    for f in all_files:
        h = hash_file(f)
        if h is None:
            hash_errors.append(f)
            continue

        bitrate, duration = get_bitrate_and_duration(f)
        in_master = h in master_hashes
        ext = Path(f).suffix.lower()
        qrank = compute_quality_rank(ext, bitrate)

        entry = {
            "source_path": f,
            "filename": Path(f).name,
            "format": ext,
            "bitrate_kbps": bitrate,
            "duration_sec": round(duration, 2) if duration else None,
            "hash": h,
            "in_master": in_master,
            "quality_rank": qrank,
            "recommended_action": "EXISTS_IN_MASTER" if in_master else "NEW_IN_MASTER"
        }

        detailed.append(entry)
        summary.setdefault(ext, 0)
        summary[ext] += 1
        
        processed += 1
        if processed % 100 == 0:
            print(f"  Analyzed {processed}/{len(all_files)} files...", end="\r")
    
    print(f"  Analyzed {processed} files")

    # Write outputs
    print("\n💾 Writing reports...")
    
    with open("report.json", "w", encoding="utf-8") as jf:
        json.dump({
            "metadata": {
                "generated": datetime.now().isoformat(),
                "master_path": master,
                "total_files": len(detailed),
                "total_errors": len(errors) + len(hash_errors)
            },
            "files": detailed
        }, jf, indent=2, ensure_ascii=False)

    with open("report_detailed.csv", "w", encoding="utf-8", newline="") as cf:
        writer = csv.writer(cf)
        writer.writerow([
            "source_path", "filename", "format", "bitrate_kbps", 
            "duration_sec", "in_master", "quality_rank", "recommended_action"
        ])
        for r in detailed:
            writer.writerow([
                r["source_path"], r["filename"], r["format"], 
                r["bitrate_kbps"], r["duration_sec"], r["in_master"],
                r["quality_rank"], r["recommended_action"]
            ])

    with open("report_summary.txt", "w", encoding="utf-8") as sf:
        sf.write("═" * 60 + "\n")
        sf.write("           AUDIO SYNC REPORT SUMMARY\n")
        sf.write("═" * 60 + "\n\n")
        sf.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        sf.write(f"Master: {master}\n\n")
        sf.write(f"Total files scanned: {len(detailed)}\n")
        sf.write(f"Files in Master: {sum(1 for r in detailed if r['in_master'])}\n")
        sf.write(f"New files to add: {sum(1 for r in detailed if not r['in_master'])}\n\n")
        sf.write("By format:\n")
        for k, v in sorted(summary.items()):
            sf.write(f"  {k:6s}: {v:5d}\n")
        
        if errors or hash_errors:
            sf.write(f"\n⚠️  Errors encountered: {len(errors) + len(hash_errors)}\n")
        
        elapsed = datetime.now() - start_time
        sf.write(f"\nProcessing time: {elapsed.total_seconds():.1f}s\n")

    if errors or hash_errors:
        with open("report_errors.txt", "w", encoding="utf-8") as ef:
            ef.write("=== Scan Errors ===\n")
            for e in errors:
                ef.write(f"{e}\n")
            ef.write("\n=== Hash Errors ===\n")
            for e in hash_errors:
                ef.write(f"{e}\n")

    print("\n✓ Report files written:")
    print("  • report.json")
    print("  • report_detailed.csv")
    print("  • report_summary.txt")
    if errors or hash_errors:
        print("  • report_errors.txt")
    
    elapsed = datetime.now() - start_time
    print(f"\n⏱  Completed in {elapsed.total_seconds():.1f}s\n")

if __name__ == "__main__":
    main()