# Questo è un file di test, utile per verificare le disponibilità  dell'API key di Anthropic.

from dotenv import load_dotenv 
load_dotenv()
from anthropic import Anthropic

c=Anthropic()
r=c.messages.create(model='claude-sonnet-4-5',max_tokens=20,messages=[{'role':'user','content':'ciao'}])
print(r.content[0].text)