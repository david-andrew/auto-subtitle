from archytas.agent import Message, Agent as ArchyAgent, Role
import openai
from typing import Generator



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
