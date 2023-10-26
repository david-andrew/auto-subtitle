import subprocess
import argparse
from tqdm import tqdm
from pathlib import Path
from archytas.agent import Agent, Message
import asyncio

import pdb


def main(directory_path):
    for file in tqdm(Path(directory_path).glob(f"*.mkv")):
        extract_subtitles_from_mkv(file)
        for subtitle_file in file.parent.glob(f"{file.stem}_track*.srt"):
            translate_subtitles(subtitle_file)

def extract_subtitles_from_mkv(file:Path):
    # determine which tracks are subtitles
    output = subprocess.check_output(["mkvmerge", "-i", str(file)], universal_newlines=True)
    lines = output.split("\n")

    # extract the subtitles
    for line in lines:
        if "subtitles" in line:
            # Parse the track ID
            track_id = line.split(":")[0].split(" ")[2]
            subtitle_file = Path(file.parent, f"{file.stem}_track{track_id}.srt")
            result = subprocess.run(["mkvextract", "tracks", str(file), f"{track_id}:{subtitle_file}"], capture_output=True)
            if result.returncode != 0:
                raise Exception(f"Failed to extract subtitles from {file}.\nStdout: {result.stdout}.\nStderr: {result.stderr}")

def check_is_english(text:str):
    agent35 = SynchronousAgent(model='gpt-3.5-turbo')
    if len(text) > 1000:
        text = text[:1000] + '...\n<rest of text truncated>'
    result = agent35.oneshot(prompt='You are a helpful assistant', query=f'Here is a .srt file:\n{text}\nAre these subtitles English? Please answer "yes" or "no" without any other comments.')
    result = result.lower()
    if 'yes' in result and 'no' not in result:
        return True
    elif 'no' in result and 'yes' not in result:
        return False
    else:
        raise Exception(f'GPT-3.5 returned an unexpected response: "{result}"')


def translate_subtitles(subtitle_file:Path):
    text = subtitle_file.read_text()
    if check_is_english(text):
        print(f'{subtitle_file} is in English.')
    else:
        print(f'{subtitle_file} is not in English.')

    #check if is english with gpt3.5
    #if it is, translate to mandarin
    # pdb.set_trace()
    ...


#make all the archytas agent methods synchronous
class SynchronousAgent:
    def __init__(self, **kwargs):
        self.agent = Agent(**kwargs) 

    #convert all async methods to sync methods
    def all_messages(self) -> list[Message]:
        return asyncio.run(self.agent.all_messages())
    
    def query(self, message: str) -> str:
        return asyncio.run(self.agent.query(message))
    
    def observe(self, observation: str) -> str:
        return asyncio.run(self.agent.observe(observation))
    
    def error(self, error: str, drop_error: bool = True) -> str:
        return asyncio.run(self.agent.error(error, drop_error))
    
    def execute(self) -> str:
        return asyncio.run(self.agent.execute())
    
    def oneshot(self, prompt: str, query: str) -> str:
        return asyncio.run(self.agent.oneshot(prompt, query))











if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract subtitles from MKV files in a specified directory.")
    parser.add_argument("directory", help="Path to the directory containing MKV files")
    args = parser.parse_args()
    main(args.directory)
