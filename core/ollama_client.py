import json
import urllib.request
import urllib.error
from typing import List, Dict, Generator, Any

from database import get_setting


class OllamaClient:
    def __init__(self, url=None, model=None):
        self.url = url or get_setting("ollama_url") or "http://localhost:11434"
        self.model = model or get_setting("ollama_model") or "llama3"
        
        if self.url.endswith("/"):
            self.url = self.url[:-1]

    def check_connection(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def chat(self, messages: List[Dict[str, str]], stream=True) -> Generator[str, None, None]:
        url = f"{self.url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req) as response:
                if stream:
                    for line in response:
                        if line:
                            decoded = line.decode("utf-8")
                            try:
                                json_obj = json.loads(decoded)
                                if "message" in json_obj and "content" in json_obj["message"]:
                                    yield json_obj["message"]["content"]
                            except json.JSONDecodeError:
                                pass
                else:
                    # Non-streaming not implemented here as we prefer streaming
                    pass
        except Exception as e:
            yield f"\n[Erro de conexao com Ollama: {str(e)}]"

    def list_models(self) -> List[str]:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=2) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return [model["name"] for model in data.get("models", [])]
        except Exception:
            pass
        return []
