# Auto Subtitle
Automatically translate subtitles to a specified language using GPT4.

## Setup
```bash
sudo apt install mkvtoolnix
conda create -n subtitle python=3.12
conda activate subtitle
pip install -r requirements.txt
```

## Usage
1. Start the program
    ```bash
    python auto_subtitle.py
    ```
1. follow the dialogs/prompts for:
    1. selecting a language
    1. selecting a video file
    1. selecting one or more subtitle files

Then the program should start the translation. When done translating, the subtitles will be merged into a copy of the video file saved at `output/<video_name>.mkv`.

## Notes
- `llm_log.txt` contains the current in progress translation
- if `llm_log.txt` has partial content that matches the current translation (checked by comparing timestamps), then the program will pick up from where it left off
- completed translations are cached in the sqlite database file `translations.db`