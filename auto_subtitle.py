import os
import subprocess
import argparse

def extract_subtitles_from_mkv(file_path):
    cmd = ["mkvmerge", "-i", file_path]
    output = subprocess.check_output(cmd, universal_newlines=True)

    # Split the output by lines
    lines = output.split("\n")

    for line in lines:
        if "subtitles" in line:
            # Parse the track ID
            track_id = line.split(":")[0].split(" ")[2]
            subtitle_file = f"{os.path.splitext(file_path)[0]}_track{track_id}.srt"
            cmd = ["mkvextract", "tracks", file_path, f"{track_id}:{subtitle_file}"]
            subprocess.run(cmd)

def main(directory_path):
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".mkv"):
                extract_subtitles_from_mkv(os.path.join(root, file))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract subtitles from MKV files in a specified directory.")
    parser.add_argument("directory", help="Path to the directory containing MKV files")
    args = parser.parse_args()
    main(args.directory)
