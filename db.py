import sqlite3

class TranslationDB:
    def __init__(self, db_file:str = 'translations.db'):
        self.db_file = db_file
        self.conn = sqlite3.connect(self.db_file)
        c = self.conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS translations 
        (input_text TEXT PRIMARY KEY, translated_text TEXT)
        ''')
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.conn.close()
    
    def insert(self, src_text:str, translation:str) -> None:
        c = self.conn.cursor()
        c.execute("INSERT OR REPLACE INTO translations (input_text, translated_text) VALUES (?, ?)", 
                  (src_text, translation))
        self.conn.commit()

    def retrieve(self, src_text:str) -> str | None:
        c = self.conn.cursor()
        c.execute("SELECT translated_text FROM translations WHERE input_text=?", (src_text,))
        result = c.fetchone()
        return result[0] if result else None
    
    def fetch_all(self) -> dict[str, str]:
        c = self.conn.cursor()
        c.execute("SELECT input_text, translated_text FROM translations")
        entries = c.fetchall()
        return {src_text: translation for src_text, translation in entries}
    
    def clear_all(self) -> None:
        c = self.conn.cursor()
        c.execute("DELETE FROM translations")
        self.conn.commit()



        

if __name__ == '__main__':
    import pdb
    with TranslationDB() as db:
        pdb.set_trace()