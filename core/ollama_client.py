import json
import urllib.request
import urllib.error
from typing import Any, Dict, Generator, List

from database import get_setting


class OllamaClientError(RuntimeError):
    """Raised when a non-streaming Ollama request cannot be trusted."""


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

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        schema: Dict[str, Any],
        *,
        options: Dict[str, Any] | None = None,
        timeout: float = 180,
        keep_alive: str = "10m",
    ) -> Dict[str, Any]:
        """Return a locally validated structured response from Ollama.

        This path deliberately does not share the streaming error-as-text
        behavior used by the interactive chat. Callers either receive trusted
        JSON plus usage metadata or an exception.
        """

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": options or {},
            "keep_alive": keep_alive,
        }
        req = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaClientError(
                f"Ollama HTTP {exc.code}: {detail[:500] or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OllamaClientError(f"Falha ao conectar ao Ollama: {exc.reason}") from exc
        except TimeoutError as exc:
            raise OllamaClientError(
                f"Ollama excedeu o timeout de {timeout:g}s"
            ) from exc
        except Exception as exc:
            raise OllamaClientError(f"Falha na chamada Ollama: {exc}") from exc

        try:
            envelope = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OllamaClientError("Ollama retornou envelope JSON inválido") from exc

        if envelope.get("error"):
            raise OllamaClientError(str(envelope["error"]))

        content = (envelope.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaClientError("Ollama retornou conteúdo estruturado vazio")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaClientError("Ollama retornou conteúdo que não é JSON válido") from exc

        self._validate_json_schema(parsed, schema)
        usage_keys = (
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
            "done_reason",
        )
        return {
            "data": parsed,
            "usage": {key: envelope.get(key) for key in usage_keys if key in envelope},
        }

    @classmethod
    def _validate_json_schema(
        cls,
        value: Any,
        schema: Dict[str, Any],
        *,
        path: str = "$",
    ) -> None:
        """Validate the JSON Schema subset used by transcript improvement."""

        expected = schema.get("type")
        if expected == "object":
            if not isinstance(value, dict):
                raise OllamaClientError(f"{path} deve ser objeto")
            for key in schema.get("required", []):
                if key not in value:
                    raise OllamaClientError(f"{path}.{key} é obrigatório")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                extras = set(value) - set(properties)
                if extras:
                    raise OllamaClientError(
                        f"{path} contém campos não permitidos: {sorted(extras)}"
                    )
            for key, item in value.items():
                child = properties.get(key)
                if child:
                    cls._validate_json_schema(item, child, path=f"{path}.{key}")
            return

        if expected == "array":
            if not isinstance(value, list):
                raise OllamaClientError(f"{path} deve ser array")
            item_schema = schema.get("items")
            if item_schema:
                for index, item in enumerate(value):
                    cls._validate_json_schema(item, item_schema, path=f"{path}[{index}]")
            return

        type_map = {
            "string": str,
            "boolean": bool,
            "integer": int,
            "number": (int, float),
        }
        py_type = type_map.get(expected)
        if py_type is not None and (
            not isinstance(value, py_type)
            or expected in {"integer", "number"} and isinstance(value, bool)
        ):
            raise OllamaClientError(f"{path} não corresponde ao tipo {expected}")

        if "enum" in schema and value not in schema["enum"]:
            raise OllamaClientError(f"{path} não pertence ao enum permitido")
