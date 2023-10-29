import subprocess
import argparse
from itertools import zip_longest, batched
from tqdm import tqdm
from pathlib import Path
import shutil
from archytas.agent import Message, Agent as ArchyAgent, Role
from typing import Generator
from bidict import bidict
import openai

from crossfiledialog import open_file, open_multiple

import pdb

from db import TranslationDB


translation_db = TranslationDB()


language_codes = bidict({
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
})

language = "Chinese (Simplified)"
language_code = language_codes[language]

model = 'gpt-4'


def main(file:Path|None, language:str):
    #have the user select the video(s) to process
    if file is None:
        prev_file = Path('_prev_file.txt')
        if prev_file.exists():
           start_dir = Path(prev_file.read_text()).parent
        else:
            start_dir = Path.cwd()
        file = Path(open_file('Select Video File', start_dir=str(start_dir), filter='*.mkv'))
        assert file.exists(), "No video file selected."
        prev_file.write_text(str(file))
    
    #create a temp directory
    tmpfile = Path.cwd()/'temp'/"temp.mkv"
    if not tmpfile.parent.exists():
        tmpfile.parent.mkdir()
    
    #copy the file to a temp directory
    shutil.copy(file, tmpfile)

    # pull subtitles as files into the temp directory
    extract_subtitles_from_mkv(tmpfile)

    #have the user select the subtitle file(s) to translate
    subtitle_files = open_multiple('Select Subtitle(s) to Translate', start_dir=str(tmpfile.parent), filter='*.srt')
    assert len(subtitle_files) > 0, "No subtitle files selected."
    subtitle_files = [Path(f) for f in subtitle_files]

    # delete all .srt files that were not selected
    for f in tmpfile.parent.glob('*.srt'):
        if f not in subtitle_files:
            f.unlink()

    # translate the subtitle files and merge subtitles back into the mkv
    for subtitle_file in subtitle_files:
        translate_subtitles(subtitle_file)
    merge_subtitles_into_mkv(tmpfile)

    #move the file to the output directory
    shutil.move(tmpfile, Path('output')/file.name)
    print(f"Finished processing output/{file.name}")

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
            # '--track-name', f'0:{language} {i}', # looks better if just called "Track N"
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
    agent35 = Agent(model='gpt-3.5-turbo')#, spinner=None)
    if len(text) > 1000:
        text = text[:1000] + '...\n<rest of text truncated>'
    result = agent35.oneshot_sync(prompt='You are a helpful assistant', query=f'Here is a .srt file:\n{text}\nAre these subtitles English? Please answer "yes" or "no" without any other comments.')
    result = result.lower()
    if 'yes' in result and 'no' not in result:
        return True
    elif 'no' in result and 'yes' not in result:
        return False
    else:
        raise Exception(f'GPT-3.5 returned an unexpected response: "{result}"')


#TODO: need to cache results to disk as they come in
def translate_subtitles(subtitle_file:Path):
    text = subtitle_file.read_text()

    # remove the BOM if it is present, and remove empty frames
    if text.startswith('\ufeff'):
        text = text[1:]
    text = '\n\n'.join([frame for frame in text.split('\n\n') if frame.strip() != ''])
    

    #check if the text is already in the database of translations
    if (translation := translation_db.retrieve(text)) is not None:
        print(f"Skipping {subtitle_file.name} because it is already translated.")
        subtitle_file.write_text(translation)
        return

    # if not is_english(text):
    #     print(f"Skipping {subtitle_file} because it is not in English.")
    #     return

    translator = Agent(model=model)#, spinner=None)

    #split the text into translation units
    frames = text.split("\n\n")
    translations = []
    window_size = 20

    batch_idxs = [*batched(range(len(frames)), window_size)]

    with tqdm(total=text.count('\n'), desc=f'translating {subtitle_file.name}', leave=False) as pbar, open('llm_log.txt', 'w') as log:
        for prev_window, window in zip([[], *batch_idxs], batch_idxs):
            
            #get the current subtitles window and translated previous window (if any)
            subtitles_window = '\n\n'.join([frames[i] for i in window])
            prev_translations_window = '\n\n'.join([translations[i] for i in prev_window])
            
            #set up the prompt and query
            prompt=f'You are a {language} translator'
            if prev_window:
                query=f'Here is a previous portion of a .srt file you are translating from English to {language}:\n{prev_translations_window}\n\nCan you translate this portion of the .srt file into {language}? Output only the translation without any other comments, and follow the formatting exactly:\n{subtitles_window}'
            else:
                query=f'Can you translate this portion of a .srt file into {language}? Output only the translation without any other comments, and follow the formatting exactly:\n{subtitles_window}'
            
            # stream result so that we can have a rough progress bar
            result_gen = translator.oneshot_streaming(prompt=prompt, query=query)
            tokens = []
            for token in result_gen:
                log.write(token); log.flush()
                tokens.append(token)
                if (newlines := token.count('\n')) > 0:        
                    pbar.update(newlines)
            result = ''.join(tokens)

            # save translations
            translations.extend(result.split('\n\n'))

    # separate components of each frame for the original and translated subtitles
    idxs, timestamps, subtitles = zip_longest(*[frame.split("\n", 2) for frame in frames])
    llm_idxs, llm_timestamps, translations = zip_longest(*[frame.split("\n", 2) for frame in translations])

    #check if the llm idxs and timestamps match the original idxs and timestamps
    #TODO: draw these with colored diffs
    if idxs != llm_idxs:
        print(f"The LLM idxs do not match the original idxs.")
        for i, (idx, llm_idx) in enumerate(zip(idxs, llm_idxs)):
            if idx != llm_idx:
                print(f"idx {i} does not match: {idx} != {llm_idx}")
        input("Press enter to continue.")
    if timestamps != llm_timestamps:
        print(f"The LLM timestamps do not match the original timestamps.")
        for i, (timestamp, llm_timestamp) in enumerate(zip(timestamps, llm_timestamps)):
            if timestamp != llm_timestamp:
                print(f"timestamp {i} does not match: {timestamp} != {llm_timestamp}")
        input("Press enter to continue.")

    #merge the translations back into the subtitle file
    out_chunks = []
    for i, (idx, timestamp, subtitle, translation) in enumerate(zip(idxs, timestamps, subtitles, translations)):
        if translation is None:
            translation = subtitle #if no translation was provided, just use the original subtitle
        out_chunks.append(f"{idx}\n{timestamp}\n{translation}")
    out_text = "\n\n".join(out_chunks)
    subtitle_file.write_text(out_text)

    #save the translation to the database
    translation_db.insert(text, out_text)



class Agent:
    def __init__(self, model:str):
        self.model = model
        self.agent = ArchyAgent(model=model)

    def oneshot_sync(self, prompt:str, query:str) -> str:
        return self.agent.oneshot_sync(prompt=prompt, query=query)

    def oneshot_streaming(self, prompt:str, query:str) -> Generator[str, None, None]:
        gen = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                Message(role=Role.system, content=prompt),
                Message(role=Role.user, content=query)
            ],
            stream=True
        )
        for chunk in gen:
            try:
                yield chunk["choices"][0]["delta"]['content']
            except:
                pass





if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract subtitles from MKV files in a specified directory.")
    parser.add_argument("--file", '-f', help="Path to the .mkv file to add a translation", default=None)
    parser.add_argument("--language", '-l', help="Language code of language to translate to", default="zh-CN")
    args = parser.parse_args()
    main(args.file and Path(args.file), args.language)