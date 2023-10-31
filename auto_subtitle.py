import subprocess
import argparse
from itertools import zip_longest, batched
from tqdm import tqdm
from pathlib import Path
import shutil
from crossfiledialog import open_file, open_multiple


from db import TranslationDB
from agent import Agent

import pdb

translation_db = TranslationDB()


language_codes = {
    "English": "en",
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


model = 'gpt-4'
translator = Agent(model=model)


def main(file:Path|None, language:str|None):
    if language is None:
        language = select_option_via_file_dialog("Select a Language", list(language_codes.keys()))
        if language is None:
            raise Exception("Error: No language selected.")
        # pdb.set_trace()
    
    language_code = language_codes[language]

    #have the user select the video(s) to process
    if file is None:
        prev_file = Path('_prev_file.txt')
        if prev_file.exists():
           start_dir = Path(prev_file.read_text()).parent
        else:
            start_dir = Path.cwd()
        file = Path(open_file('Select Video File', start_dir=str(start_dir.absolute()), filter='*.mkv'))
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
        translate_subtitles(subtitle_file, language, translator)
    merge_subtitles_into_mkv(tmpfile, language_code)

    #move the file to the output directory
    shutil.move(tmpfile, Path('output')/file.name)
    print(f"Finished processing output/{file.name}")

    #delete the temp directory contents
    for f in tmpfile.parent.glob('**/*'):
        if f.is_file():
            f.unlink()


def select_option_via_file_dialog(title:str, options: list[str]) -> str|None:
    # Create a temporary directory
    temp_path = Path('temp') / 'languages'
    if not temp_path.exists():
        temp_path.mkdir(parents=True)
        
    # Create empty files for each option in the temp directory
    for option in options:
        (temp_path / f"{option}").touch()
    
    # Display the open_file dialog
    selection_path = open_file(title, start_dir=str(temp_path.absolute()))
    
    # If the user cancels the file dialog, selection_path will be None.
    if not selection_path:
        return None

    # Extract the selected option from the path
    selected_option = Path(selection_path).stem

    # delete the temp directory contents
    for f in temp_path.glob('*'):
        f.unlink()
    
    # Return the selected option
    return selected_option


def merge_subtitles_into_mkv(file:Path, language_code:str):
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
            



#TODO: need to cache results to disk as they come in
def translate_subtitles(subtitle_file:Path, language:str, translator:Agent):
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


    #split the text into translation units
    frames = text.split("\n\n")
    translations = []
    window_size = 20

    batch_idxs = [*batched(range(len(frames)), window_size)]

    # check for any partial translations to restart the process with
    if Path('llm_log.txt').exists():
        log_text = Path('llm_log.txt').read_text()                                      # read the log
        partial = log_text.split('\n\n')[:-1]                                           # split into frames (truncate the last frame since it may be incomplete)
        llm_idxs, llm_timestamps, llm_subtitles = [*zip_longest(*[frame.split("\n", 2) for frame in partial])]   # separate components of each frame
        assert all(None not in f for f in zip(llm_idxs, llm_timestamps, llm_subtitles)), "Error with the saved translation. Some frames are missing pieces. Please check llm_log.txt."
        assert all(matches:=[int(l)==i for l,i in zip(llm_idxs, range(1,len(llm_idxs)+1))]), f"Error with the saved idxs ({[*enumerate(matches)]}). Please check llm_log.txt."

        #compare the timestamps to the original timestamps to see if the translation is a match
        _, timestamps, _ = zip_longest(*[frame.split("\n", 2) for frame in frames])

        matches = [l == t for l,t in zip(llm_timestamps, timestamps)]
        match_score = sum(matches)/len(matches)
        if match_score < 0.25:
            print(f'Detected a low match score ({match_score}). Deleting the saved translation and starting over.')
            choice = 'n'
        elif match_score < 0.9:
            print(f"Warning: the translation file in progress does not match the original subtitle file very well. Match score: {match_score}")
            choice = input("Would you like to use the saved translation anyway? (y/n)")
        else:
            # use previous in-progress translation
            choice = 'y'

        if choice == 'y':
            print('Starting from previous partial translation')
            translations = partial
            batch_idxs = [*batched(range(len(translations), len(frames)), window_size)]
            Path('llm_log.txt').write_text('\n\n'.join(translations) + '\n\n')
        else:
            print('Ignoring previous partial translation')

    with tqdm(total=text.count('\n'), desc=f'translating {subtitle_file.name}', leave=False, miniters=1) as pbar, open('llm_log.txt', 'w' if len(translations) == 0 else 'a') as log:
        
        #if restarting an in-progress translation, set the initial progress bar position
        if len(translations) > 0: pbar.update('\n\n'.join(translations).count('\n'))
        
        #iterate through the translation windows
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
            log.write('\n\n'); log.flush()
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
                print(f"idx {i} does not match: '{idx}' != '{llm_idx}'")
        input("Press enter to continue.")
    if timestamps != llm_timestamps:
        print(f"The LLM timestamps do not match the original timestamps.")
        for i, (timestamp, llm_timestamp) in enumerate(zip(timestamps, llm_timestamps)):
            if timestamp != llm_timestamp:
                print(f"timestamp {i} does not match: '{timestamp}' != '{llm_timestamp}'")
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






if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract subtitles from MKV files in a specified directory.")
    parser.add_argument("--file", '-f', help="Path to the .mkv file to add a translation", default=None)
    parser.add_argument("--language", '-l', help="Language code of language to translate to", default=None)
    args = parser.parse_args()
    main(args.file and Path(args.file), args.language)