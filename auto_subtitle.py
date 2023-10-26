import subprocess
import argparse
from tqdm import tqdm
from pathlib import Path
import shutil
from archytas.agent import Agent, Message
import asyncio

import pdb


language_codes = {
    "English": "en",
    "Chinese": "zh",
    "Chinese (Simplified)": "zh-CN",
    "Chinese (Traditional)": "zh-TW",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Japanese": "ja",
    "Korean": "ko",
    "Portuguese": "pt",
    "Russian": "ru",
    "Spanish": "es",
    "Turkish": "tr",
}

language = "Chinese (Simplified)"
language_code = language_codes[language]

def main(indir:Path, outdir:Path):
    #create a temp directory
    tmpfile = Path.cwd()/'temp'/"temp.mkv"
    if not tmpfile.parent.exists():
        tmpfile.parent.mkdir()
    
    for file in tqdm(sorted(indir.glob(f"*.mkv"))):
        #copy the file to a temp directory
        shutil.copy(file, tmpfile)

        extract_subtitles_from_mkv(tmpfile)
        for subtitle_file in tmpfile.parent.glob(f"*.srt"):
            translate_subtitles(subtitle_file)

        #merge subtitles back into the mkv
        merge_subtitles_into_mkv(tmpfile)

        #move the file back to the original directory
        pdb.set_trace()
        # shutil.move(tmpfile, outdir/file.name)

        #delete the temp directory contents
        for f in tmpfile.parent.glob('*'):
            f.unlink()

def merge_subtitles_into_mkv(file:Path):
    # get the new subtitle files for the language
    new_subtitle_files = file.parent.glob(f"*.srt")

    # merge the new subtitle files into the mkv
    for i, subtitle_file in enumerate(new_subtitle_files):
        shutil.move(file, file.parent/f"old.mkv")
        result = subprocess.run([
            "mkvmerge", "-o", str(file), str(file.parent/'old.mkv'), 
            '--language', f'0:{language_code}',
            # '--track-name', f'0:{language} {i}', 
            str(subtitle_file)
        ], capture_output=True)
        if result.returncode != 0:
            raise Exception(f"Failed to merge subtitles into {file}.\nStdout: {result.stdout}.\nStderr: {result.stderr}")



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
            

def is_english(text:str):
    agent35 = SynchronousAgent(model='gpt-3.5-turbo', spinner=None)
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
    if not is_english(text):
        print(f"Skipping {subtitle_file} because it is not in English.")
        return

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
    parser.add_argument("--indir", '-i', help="Path to the directory containing .mkv files")
    parser.add_argument("--outdir", '-o', help="Path to the directory where the processed .mkv files will be saved", default='output')
    args = parser.parse_args()
    main(Path(args.indir), Path(args.outdir))
